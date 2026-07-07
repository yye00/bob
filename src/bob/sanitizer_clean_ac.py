"""bob.sanitizer_clean_ac — sanitizer-clean execution AC with instrumentation proof.

bob's GPU anti-cheat proves a kernel *launched*, but it has no memory/UB safety
gate for C++ host + HIP code. RCCL work (custom kernels, buffer registration,
XGMI ring pointer arithmetic) is exactly where undefined behaviour and
out-of-bounds writes hide.

This module implements a ``sanitizer-clean: <asan|ubsan|tsan> <command>`` AC
that:

1. Builds a dedicated instrumented configuration
   (``-fsanitize=address,undefined -fno-sanitize-recover=all`` for host).
2. **Proves** instrumentation is actually present rather than silently dropped —
   the compiled binary must link the asan/ubsan runtime (verified with
   ``nm -D`` / ``ldd``), so a sub-agent cannot game the gate by deleting the
   ``-fsanitize`` flags.
3. Runs the target under
   ``ASAN_OPTIONS=halt_on_error=1:detect_leaks=1:exitcode=1
   UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`` requiring exit 0 with an
   empty sanitizer report.
4. Runs a known-bad **tripwire** once at setup to confirm the harness genuinely
   catches an injected error (guards against a mis-wired always-green path).

``-fno-sanitize-recover=all`` ensures a reported error cannot coexist with a
success exit code.

Public API
----------
verify_sanitizer_clean(criterion, workspace, *, runner=None, prober=None)
    -> tuple[bool, str]
    Primary entry point. Parse and verify a ``sanitizer-clean:`` AC.
run_tripwire(sanitizer, workspace, *, runner=None) -> tuple[bool, str]
    Run the known-bad tripwire for a sanitizer, confirming the harness catches
    an injected error.

Supporting helpers (also exported):
    parse_sanitizer_clean_ac, build_sanitizer_env, scan_sanitizer_report,
    verify_instrumentation_present, SUPPORTED_SANITIZERS.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "SUPPORTED_SANITIZERS",
    "SANITIZER_ENV",
    "SANITIZER_RUNTIME_SYMBOLS",
    "parse_sanitizer_clean_ac",
    "build_sanitizer_env",
    "scan_sanitizer_report",
    "verify_instrumentation_present",
    "run_tripwire",
    "verify_sanitizer_clean",
]

#: Sanitizers this gate understands.
SUPPORTED_SANITIZERS: frozenset[str] = frozenset({"asan", "ubsan", "tsan"})

#: Environment variables that force a reported error to fail the run.
#: ``exitcode=1`` + ``halt_on_error=1`` mean a sanitizer report can never
#: coexist with a success exit code.
SANITIZER_ENV: dict[str, dict[str, str]] = {
    "asan": {
        "ASAN_OPTIONS": "halt_on_error=1:detect_leaks=1:exitcode=1",
        "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1",
    },
    "ubsan": {
        "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1:exitcode=1",
    },
    "tsan": {
        "TSAN_OPTIONS": "halt_on_error=1:exitcode=1",
    },
}

#: Runtime symbols / library fragments that prove a binary links the
#: sanitizer runtime.  Used by :func:`verify_instrumentation_present`.
SANITIZER_RUNTIME_SYMBOLS: dict[str, tuple[str, ...]] = {
    "asan": ("__asan_init", "__asan", "libasan", "libclang_rt.asan"),
    "ubsan": ("__ubsan_handle", "__ubsan", "libubsan", "libclang_rt.ubsan"),
    "tsan": ("__tsan_init", "__tsan", "libtsan", "libclang_rt.tsan"),
}

#: Substrings in program output that indicate a non-empty sanitizer report.
_REPORT_MARKERS: tuple[str, ...] = (
    "ERROR: AddressSanitizer",
    "ERROR: LeakSanitizer",
    "runtime error:",  # UBSan
    "SUMMARY: AddressSanitizer",
    "SUMMARY: UndefinedBehaviorSanitizer",
    "SUMMARY: ThreadSanitizer",
    "WARNING: ThreadSanitizer",
    "detected memory leaks",
    "heap-buffer-overflow",
    "stack-buffer-overflow",
    "heap-use-after-free",
    "data race",
)

# A subprocess-style callable: (cmd, env) -> object with .returncode/.stdout/.stderr
Runner = Callable[..., Any]


def _normalize_sanitizer(sanitizer: str) -> str:
    """Return the canonical lower-case sanitizer name or raise ValueError."""
    if not isinstance(sanitizer, str):
        raise ValueError(
            f"sanitizer must be a string, got {type(sanitizer).__name__}"
        )
    name = sanitizer.strip().lower()
    if not name:
        raise ValueError("sanitizer must not be empty")
    if name not in SUPPORTED_SANITIZERS:
        raise ValueError(
            f"unsupported sanitizer {sanitizer!r}; "
            f"expected one of {sorted(SUPPORTED_SANITIZERS)}"
        )
    return name


def parse_sanitizer_clean_ac(criterion: str) -> tuple[str, str] | None:
    """Parse a ``sanitizer-clean: <asan|ubsan|tsan> <command>`` AC line.

    Returns ``(sanitizer, command)`` on a match, or ``None`` when the line is
    not a ``sanitizer-clean:`` AC (caller should fall through to the next
    pattern).

    Raises
    ------
    ValueError
        If *criterion* is not a string, or the line is a ``sanitizer-clean:``
        AC but is malformed (missing sanitizer, unsupported sanitizer, or
        missing command/regex body).
    """
    if not isinstance(criterion, str):
        raise ValueError(
            f"criterion must be a string, got {type(criterion).__name__}"
        )

    stripped = criterion.strip()
    match = re.match(r"^sanitizer-clean\s*:\s*(.*)$", stripped, re.IGNORECASE)
    if match is None:
        return None

    body = match.group(1).strip()
    if not body:
        raise ValueError(
            "sanitizer-clean AC requires '<asan|ubsan|tsan> <command>'"
        )

    parts = body.split(None, 1)
    sanitizer = _normalize_sanitizer(parts[0])
    if len(parts) < 2 or not parts[1].strip():
        raise ValueError(
            "sanitizer-clean AC requires a ctest regex or command after the "
            "sanitizer name"
        )
    command = parts[1].strip()
    return sanitizer, command


def build_sanitizer_env(sanitizer: str, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return the environment for running a target under *sanitizer*.

    Merges the sanitizer-specific ``*_OPTIONS`` on top of *base_env* (or an
    empty dict). The options force ``exitcode=1`` + ``halt_on_error=1`` so a
    reported error can never coexist with a success exit code.

    Raises
    ------
    ValueError
        If *sanitizer* is unsupported or *base_env* is not a mapping.
    """
    name = _normalize_sanitizer(sanitizer)
    if base_env is None:
        env: dict[str, str] = {}
    elif isinstance(base_env, dict):
        env = dict(base_env)
    else:
        raise ValueError(
            f"base_env must be a dict or None, got {type(base_env).__name__}"
        )
    env.update(SANITIZER_ENV[name])
    return env


def scan_sanitizer_report(output: str | None) -> bool:
    """Return True when *output* is a CLEAN report (no sanitizer errors).

    A ``None`` or empty output is clean. Any known sanitizer error/summary
    marker means the report is non-empty and the run is dirty.
    """
    if output is None:
        return True
    if not isinstance(output, str):
        raise ValueError(
            f"output must be a string or None, got {type(output).__name__}"
        )
    return not any(marker in output for marker in _REPORT_MARKERS)


def verify_instrumentation_present(
    binary: str | Path,
    sanitizer: str,
    *,
    prober: Callable[[str | Path], str] | None = None,
) -> bool:
    """Return True when *binary* provably links the *sanitizer* runtime.

    Proves instrumentation was not silently dropped: inspects the binary's
    dynamic symbols / linked libraries (via ``nm -D`` and ``ldd``, or a
    supplied *prober*) for the sanitizer runtime. A sub-agent that deletes the
    ``-fsanitize`` flags produces a binary that fails this check.

    Parameters
    ----------
    binary:
        Path to the compiled instrumented binary.
    sanitizer:
        One of ``asan``/``ubsan``/``tsan``.
    prober:
        Optional callable ``(binary) -> str`` returning the combined
        symbol/library text to scan (used for testing). Defaults to running
        ``nm -D`` and ``ldd`` on the binary.

    Raises
    ------
    ValueError
        If *sanitizer* is unsupported or *binary* is empty.
    """
    name = _normalize_sanitizer(sanitizer)
    if binary is None or (isinstance(binary, str) and not binary.strip()):
        raise ValueError("binary path must not be empty")

    if prober is None:
        text = _default_symbol_probe(binary)
    else:
        text = prober(binary)

    if not text:
        return False
    markers = SANITIZER_RUNTIME_SYMBOLS[name]
    return any(marker in text for marker in markers)


def _default_symbol_probe(binary: str | Path) -> str:
    """Concatenate ``nm -D`` and ``ldd`` output for *binary* (best-effort)."""
    chunks: list[str] = []
    for cmd in (["nm", "-D", str(binary)], ["ldd", str(binary)]):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
        chunks.append(result.stdout or "")
        chunks.append(result.stderr or "")
    return "\n".join(chunks)


def run_tripwire(
    sanitizer: str,
    workspace: str | Path,
    *,
    runner: Runner | None = None,
) -> tuple[bool, str]:
    """Run a known-bad tripwire, confirming the harness catches an injected error.

    Compiles and runs a deliberately buggy program under *sanitizer* (a
    heap-buffer-overflow for asan, a signed-overflow for ubsan, a data race for
    tsan). The harness is considered correctly wired only when the tripwire is
    *caught* — i.e. the run exits non-zero AND its output contains a sanitizer
    report. If the tripwire passes cleanly, the harness is mis-wired
    (always-green) and this returns ``(False, reason)``.

    Parameters
    ----------
    sanitizer:
        One of ``asan``/``ubsan``/``tsan``.
    workspace:
        Project workspace (where the tripwire is built/run).
    runner:
        Optional callable ``(sanitizer, workspace, env) -> result`` where
        result exposes ``returncode`` and ``output`` (or ``stdout``). Used for
        testing; defaults to a real compile+run of the injected-bug program.

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` when the tripwire was correctly caught; ``(False,
        reason)`` when it was not (harness mis-wired or tripwire unbuildable).

    Raises
    ------
    ValueError
        If *sanitizer* is unsupported or *workspace* is empty.
    """
    name = _normalize_sanitizer(sanitizer)
    if workspace is None or (isinstance(workspace, str) and not str(workspace).strip()):
        raise ValueError("workspace must not be empty")

    env = build_sanitizer_env(name)
    if runner is None:
        runner = _default_tripwire_runner

    try:
        result = runner(name, workspace, env)
    except Exception as exc:  # noqa: BLE001 - report as a failed tripwire
        return False, f"tripwire runner raised: {exc}"

    returncode = _result_returncode(result)
    output = _result_output(result)

    # Caught means: non-zero exit AND a sanitizer report present.
    if returncode == 0:
        return False, (
            "tripwire exited 0 — harness is mis-wired (always-green); an "
            "injected sanitizer error was not caught"
        )
    if scan_sanitizer_report(output):
        return False, (
            "tripwire exited non-zero but produced no sanitizer report — "
            "harness cannot confirm it catches injected errors"
        )
    return True, ""


def verify_sanitizer_clean(
    criterion: str,
    workspace: str | Path,
    *,
    runner: Runner | None = None,
    prober: Callable[[str | Path], str] | None = None,
    tripwire_runner: Runner | None = None,
    skip_tripwire: bool = False,
) -> tuple[bool, str]:
    """Verify a ``sanitizer-clean: <asan|ubsan|tsan> <command>`` AC.

    Steps:

    1. Parse the AC (returns ``None`` -> not our AC).
    2. Run the tripwire to prove the harness catches injected errors
       (unless *skip_tripwire*).
    3. Build the instrumented target and run *command* under the sanitizer env.
    4. Prove instrumentation is present (binary links the sanitizer runtime).
    5. Require exit 0 with an empty sanitizer report.

    Parameters
    ----------
    criterion:
        The AC line.
    workspace:
        Project workspace root.
    runner:
        Optional ``(command, workspace, env) -> result`` callable for the main
        target run (result exposes ``returncode``, ``output``/``stdout``, and
        optionally ``binary``). Used for testing.
    prober:
        Optional symbol/library prober passed to
        :func:`verify_instrumentation_present`.
    tripwire_runner:
        Optional runner forwarded to :func:`run_tripwire`.
    skip_tripwire:
        When True, skip the tripwire self-test (e.g. already run once at setup).

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` when the target ran sanitizer-clean with proven
        instrumentation; ``(False, reason)`` on any failure. Returns
        ``(False, reason)`` (never ``None``) so callers get a well-defined
        result.

    Raises
    ------
    ValueError
        If *criterion* is not a ``sanitizer-clean:`` AC and is malformed, or if
        *workspace* is empty. A non-``sanitizer-clean:`` line raises ValueError
        (this handler is only invoked for its own AC kind).
    """
    if workspace is None or (isinstance(workspace, str) and not str(workspace).strip()):
        raise ValueError("workspace must not be empty")

    parsed = parse_sanitizer_clean_ac(criterion)
    if parsed is None:
        raise ValueError(
            f"not a sanitizer-clean AC: {criterion!r}"
        )
    sanitizer, command = parsed

    # 2. Prove the harness genuinely catches injected errors.
    if not skip_tripwire:
        ok, reason = run_tripwire(
            sanitizer, workspace, runner=tripwire_runner
        )
        if not ok:
            return False, f"tripwire self-test failed: {reason}"

    # 3. Build + run the instrumented target.
    env = build_sanitizer_env(sanitizer)
    if runner is None:
        runner = _default_target_runner

    try:
        result = runner(command, workspace, env)
    except Exception as exc:  # noqa: BLE001
        return False, f"target runner raised: {exc}"

    # 4. Prove instrumentation is present.
    binary = _result_binary(result)
    if binary is not None:
        try:
            instrumented = verify_instrumentation_present(
                binary, sanitizer, prober=prober
            )
        except ValueError as exc:
            return False, f"instrumentation check error: {exc}"
        if not instrumented:
            return False, (
                f"instrumentation not present in {binary}: binary does not "
                f"link the {sanitizer} runtime (were -fsanitize flags dropped?)"
            )

    # 5. Require exit 0 with an empty sanitizer report.
    returncode = _result_returncode(result)
    output = _result_output(result)
    if returncode != 0:
        return False, (
            f"target exited {returncode} under {sanitizer} "
            f"(a sanitizer error cannot coexist with success)"
        )
    if not scan_sanitizer_report(output):
        return False, f"non-empty {sanitizer} report detected in target output"

    return True, ""


# --------------------------------------------------------------------------- #
# result accessors — tolerate both objects (CompletedProcess-like) and dicts
# --------------------------------------------------------------------------- #
def _result_returncode(result: Any) -> int:
    if result is None:
        return 1
    if isinstance(result, dict):
        return int(result.get("returncode", 1))
    return int(getattr(result, "returncode", 1))


def _result_output(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        return str(
            result.get("output")
            or result.get("stdout")
            or ""
        ) + str(result.get("stderr") or "")
    out = getattr(result, "output", None)
    if out is not None:
        return str(out)
    return str(getattr(result, "stdout", "") or "") + str(
        getattr(result, "stderr", "") or ""
    )


def _result_binary(result: Any) -> str | Path | None:
    if result is None:
        return None
    if isinstance(result, dict):
        return result.get("binary")
    return getattr(result, "binary", None)


def _default_target_runner(
    command: str, workspace: str | Path, env: dict[str, str]
) -> subprocess.CompletedProcess:
    """Run *command* under the sanitizer *env* in *workspace* (best-effort)."""
    import os

    full_env = {**os.environ, **env}
    return subprocess.run(
        command,
        shell=True,
        cwd=str(workspace),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )


_TRIPWIRE_SOURCE = {
    "asan": (
        "#include <cstdlib>\n"
        "int main(){char*p=(char*)malloc(1);p[7]='x';int r=p[7];free(p);"
        "return r;}\n"
    ),
    "ubsan": (
        "#include <climits>\n"
        "int main(){int x=INT_MAX;x+=1;return x;}\n"
    ),
    "tsan": (
        "#include <thread>\n"
        "int g=0;void f(){for(int i=0;i<100000;i++)g++;}\n"
        "int main(){std::thread a(f),b(f);a.join();b.join();return g==0;}\n"
    ),
}

_TRIPWIRE_FLAGS = {
    "asan": "-fsanitize=address,undefined -fno-sanitize-recover=all",
    "ubsan": "-fsanitize=undefined -fno-sanitize-recover=all",
    "tsan": "-fsanitize=thread",
}


def _default_tripwire_runner(
    sanitizer: str, workspace: str | Path, env: dict[str, str]
) -> subprocess.CompletedProcess:
    """Compile + run the injected-bug tripwire for *sanitizer* (best-effort)."""
    import os
    import tempfile

    src = _TRIPWIRE_SOURCE[sanitizer]
    flags = _TRIPWIRE_FLAGS[sanitizer]
    with tempfile.TemporaryDirectory(dir=str(workspace)) as tmp:
        src_path = Path(tmp) / "tripwire.cpp"
        bin_path = Path(tmp) / "tripwire.bin"
        src_path.write_text(src)
        compile_cmd = f"c++ {flags} -O0 -g {src_path} -o {bin_path}"
        comp = subprocess.run(
            compile_cmd,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if comp.returncode != 0:
            return subprocess.CompletedProcess(
                compile_cmd, 0, stdout="", stderr=comp.stderr
            )
        full_env = {**os.environ, **env}
        return subprocess.run(
            [str(bin_path)],
            cwd=str(workspace),
            env=full_env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
