"""f3523d60: CMake/Ninja build-verification gate — a real ``build:`` AC kind.

Problem
-------
Today bob's verifier NEVER runs a compiler. In
``enhanced_verification.py::_check_criterion`` the criterion "CMake builds
successfully" is satisfied merely by ``(workspace / "CMakeLists.txt").exists()``,
and "No compilation errors" hard-returns ``False`` because it "cannot confirm
statically". The net effect: every C++/RCCL feature can be rubber-stamped
without ever compiling a single translation unit.

Solution
--------
This module adds a real build executor mirroring
``enhanced_verification._run_pytest_criterion``:

* :func:`is_cmake_project` — detect a CMake project (``CMakeLists.txt`` present).
* :func:`run_build_criterion` — configure with
  ``cmake -S <src> -B <build> -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
  -DCMAKE_BUILD_TYPE=RelWithDebInfo`` using the ROCm toolchain
  (``CMAKE_CXX_COMPILER=hipcc``/``amdclang++``), then ``cmake --build <build>
  -j``; ``compile:`` compiles a single translation unit with ``hipcc``; and
  ``link:`` asserts the expected artifact was produced with no
  unresolved-symbol errors. The exit code AND the compiler diagnostic stream
  are parsed; a non-zero build is a hard FAIL with the first N error lines
  surfaced as the reason (exactly as pytest failures are surfaced). Command,
  exit code, and stdout/stderr are persisted as verification evidence
  artifacts.

Compile-must-succeed becomes the C++ analog of tests-collect-cleanly.

Integration
-----------
``bob.enhanced_verification._check_criterion_with_details`` routes the
``build:`` / ``compile:`` / ``link:`` AC prefixes here, and auto-arms on
:func:`is_cmake_project`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shlex
import shutil
from dataclasses import dataclass, field

# The pgroup-timeout wrapper is the ONLY sanctioned way to spawn a build so a
# runaway ``cmake``/``ninja``/``hipcc`` grandchild cannot outlive the verifier.
from bob.enhanced_verification import _run_with_pgroup_timeout

__all__ = [
    "BuildResult",
    "DEFAULT_BUILD_TIMEOUT_S",
    "ROCM_CXX_COMPILERS",
    "VALID_BUILD_KINDS",
    "UNRESOLVED_SYMBOL_MARKERS",
    "is_cmake_project",
    "resolve_cxx_compiler",
    "extract_error_lines",
    "run_build_criterion",
]

# Compiling a fat C++/HIP binary is far slower than collecting pytest; give the
# build a generous but bounded default ceiling.
DEFAULT_BUILD_TIMEOUT_S = 1800

# ROCm toolchain preference order. hipcc is the canonical HIP driver; the
# amdclang++/clang++ family is the fallback; a stock host compiler is the last
# resort so a non-ROCm host still exercises the compile path.
ROCM_CXX_COMPILERS: tuple[str, ...] = (
    "hipcc",
    "amdclang++",
    "clang++",
    "c++",
    "g++",
)

VALID_BUILD_KINDS: frozenset[str] = frozenset({"build", "compile", "link"})

# Substrings a linker emits for an unresolved / undefined symbol. Presence of
# any of these — even with a zero exit on some toolchains — is a hard link
# failure.
UNRESOLVED_SYMBOL_MARKERS: tuple[str, ...] = (
    "undefined reference",
    "undefined symbol",
    "unresolved external symbol",
    "cannot find -l",
    "ld: symbol(s) not found",
)

# How many compiler diagnostic lines to surface as the failure reason, mirroring
# the pytest tail behaviour.
_MAX_ERROR_LINES = 20

_ERROR_LINE_RE = re.compile(r"\berror\b|\bundefined\b|\bunresolved\b", re.IGNORECASE)


@dataclass
class BuildResult:
    """Outcome of a single ``build:``/``compile:``/``link:`` criterion.

    Iterable as ``(passed, details)`` so it plugs straight into the
    ``(bool, str)`` contract every criterion helper in
    :mod:`bob.enhanced_verification` returns.
    """

    passed: bool
    details: str
    kind: str = "build"
    command: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    evidence_path: str | None = None
    error_lines: list[str] = field(default_factory=list)

    def __iter__(self):
        # Enables ``passed, details = run_build_criterion(...)``.
        yield self.passed
        yield self.details

    def __bool__(self) -> bool:
        return self.passed


def is_cmake_project(workspace: str | os.PathLike | pathlib.Path) -> bool:
    """Return ``True`` when *workspace* is a CMake project.

    A CMake project is one with a top-level ``CMakeLists.txt``. Used to
    auto-arm the build gate: a ``build:`` AC on a non-CMake workspace should
    not be silently skipped, but ``is_cmake_project`` lets callers decide
    whether to arm the gate implicitly.

    Raises:
        ValueError: When *workspace* is ``None`` or not a path-like/str.
    """
    if workspace is None:
        raise ValueError("workspace must not be None")
    if not isinstance(workspace, (str, os.PathLike)):
        raise ValueError(
            f"workspace must be a str or PathLike, got {type(workspace).__name__!r}"
        )
    try:
        ws = pathlib.Path(workspace)
    except TypeError as e:  # pragma: no cover - defensive
        raise ValueError(f"invalid workspace path: {workspace!r}") from e
    return (ws / "CMakeLists.txt").is_file()


def resolve_cxx_compiler(
    preferred: str | None = None,
    *,
    which=shutil.which,
) -> str | None:
    """Resolve the C++ compiler to hand to CMake / a single-TU compile.

    Honours an explicit *preferred* compiler first, then walks
    :data:`ROCM_CXX_COMPILERS`. Returns the resolved absolute path (via
    :func:`shutil.which`) or ``None`` when no compiler is installed.
    """
    candidates: list[str] = []
    if preferred:
        candidates.append(preferred)
    candidates.extend(ROCM_CXX_COMPILERS)
    for cand in candidates:
        resolved = which(cand)
        if resolved:
            return resolved
    return None


def extract_error_lines(output: str, limit: int = _MAX_ERROR_LINES) -> list[str]:
    """Return up to *limit* diagnostic lines from a compiler/linker stream.

    Lines mentioning ``error`` / ``undefined`` / ``unresolved`` are preferred;
    if none match we fall back to the tail of the output so a failure without
    the literal word "error" (e.g. a segfaulting compiler) still surfaces
    context.
    """
    if not output:
        return []
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    matched = [ln for ln in lines if _ERROR_LINE_RE.search(ln)]
    if matched:
        return matched[:limit]
    return lines[-limit:]


def _persist_evidence(
    workspace: pathlib.Path,
    kind: str,
    command: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
) -> str | None:
    """Write the build command + streams to a verification-evidence file.

    Best-effort: an unwritable workspace degrades to ``None`` rather than
    failing the criterion.
    """
    try:
        evidence_dir = workspace / ".bob_build_evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        # Deterministic, collision-free name without relying on wall-clock.
        idx = len(list(evidence_dir.glob(f"{kind}_*.log")))
        path = evidence_dir / f"{kind}_{idx:03d}.log"
        path.write_text(
            f"command: {command}\n"
            f"exit_code: {exit_code}\n"
            f"--- stdout ---\n{stdout}\n"
            f"--- stderr ---\n{stderr}\n",
            encoding="utf-8",
        )
        return str(path)
    except OSError:
        return None


def _parse_build_expression(expression: str) -> dict[str, str]:
    """Parse the substring after the ``build:``/``compile:``/``link:`` prefix.

    Recognised ``key=value`` tokens: ``src``, ``build``, ``compiler``,
    ``artifact``, ``source``. Any bare leading token is treated as the source
    directory (``build``/``link``) or the source file (``compile``). Unknown
    tokens are ignored so free-text annotations after the args don't break
    parsing.
    """
    args: dict[str, str] = {}
    if not expression:
        return args
    try:
        tokens = shlex.split(expression)
    except ValueError:
        tokens = expression.split()
    positional: list[str] = []
    for tok in tokens:
        if "=" in tok:
            key, _, val = tok.partition("=")
            key = key.strip().lower()
            if key in {"src", "build", "compiler", "artifact", "source"}:
                args[key] = val.strip()
        else:
            positional.append(tok)
    if positional and "src" not in args and "source" not in args:
        args["_positional"] = positional[0]
    return args


def _cmake_configure_cmd(
    src: str, build: str, compiler: str
) -> list[str]:
    return [
        "cmake",
        "-S",
        src,
        "-B",
        build,
        "-G",
        "Ninja",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
        f"-DCMAKE_CXX_COMPILER={compiler}",
    ]


def run_build_criterion(
    workspace: str | os.PathLike | pathlib.Path,
    expression: str = "",
    *,
    kind: str = "build",
    timeout: int = DEFAULT_BUILD_TIMEOUT_S,
    env: dict[str, str] | None = None,
) -> BuildResult:
    """Execute a ``build:``/``compile:``/``link:`` acceptance criterion.

    Mirrors :func:`bob.enhanced_verification._run_pytest_criterion`: it never
    silently succeeds. A non-zero build/compile/link, a missing toolchain, a
    missing workspace, or a timeout all degrade to a ``BuildResult`` whose
    ``passed`` is ``False`` and whose ``details`` surface the first N compiler
    error lines — exactly as pytest failures are surfaced.

    ``expression`` is the substring after the AC prefix. It may carry
    ``key=value`` tokens (``src=``, ``build=``, ``compiler=``, ``artifact=``,
    ``source=``) or a single bare positional (source dir for ``build``/``link``,
    source file for ``compile``).

    Args:
        workspace: Project root to build in.
        expression: Parsed for build args (see above); may be empty.
        kind: One of ``"build"``, ``"compile"``, ``"link"``.
        timeout: Hard wall-clock ceiling for each subprocess.
        env: Optional environment overrides for the build.

    Returns:
        BuildResult: iterable as ``(passed, details)``.

    Raises:
        ValueError: On a non-str/None *expression*, a non-int/non-positive
            *timeout*, or an unrecognised *kind*. These are programmer errors,
            distinct from a build that legitimately fails (which returns a
            ``BuildResult`` with ``passed=False``).
    """
    # ---- input validation (error path — must raise, never silent-pass) ----
    if workspace is None:
        raise ValueError("workspace must not be None")
    if not isinstance(workspace, (str, os.PathLike)):
        raise ValueError(
            f"workspace must be a str or PathLike, got {type(workspace).__name__!r}"
        )
    if expression is None or not isinstance(expression, str):
        raise ValueError(
            f"expression must be a str, got {type(expression).__name__!r}"
        )
    if isinstance(kind, str):
        kind_norm = kind.strip().lower()
    else:
        raise ValueError(f"kind must be a str, got {type(kind).__name__!r}")
    if kind_norm not in VALID_BUILD_KINDS:
        raise ValueError(
            f"kind must be one of {sorted(VALID_BUILD_KINDS)}, got {kind!r}"
        )
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        raise ValueError(f"timeout must be an int, got {type(timeout).__name__!r}")
    if timeout <= 0:
        raise ValueError(f"timeout must be positive, got {timeout}")

    ws = pathlib.Path(workspace)

    # ---- boundary path — well-defined result, never raises past here ----
    if not ws.exists():
        return BuildResult(False, "workspace not found", kind=kind_norm)

    args = _parse_build_expression(expression.strip())
    compiler = resolve_cxx_compiler(args.get("compiler"))
    if compiler is None:
        return BuildResult(
            False,
            "no C++ compiler available (hipcc/amdclang++/clang++/c++/g++ not found)",
            kind=kind_norm,
        )

    build_env = dict(os.environ)
    if env:
        build_env.update(env)

    if kind_norm == "compile":
        return _run_single_tu_compile(ws, args, compiler, timeout, build_env)
    return _run_cmake_build(ws, args, compiler, kind_norm, timeout, build_env)


def _run_single_tu_compile(
    ws: pathlib.Path,
    args: dict[str, str],
    compiler: str,
    timeout: int,
    env: dict[str, str],
) -> BuildResult:
    source = args.get("source") or args.get("_positional")
    if not source:
        return BuildResult(
            False,
            "compile: criterion requires a source file (e.g. 'compile: src/foo.cpp')",
            kind="compile",
        )
    src_path = ws / source
    if not src_path.is_file():
        return BuildResult(
            False,
            f"compile: source file not found: {source!r}",
            kind="compile",
        )
    # ``-c`` -> single TU, no link; ``-o /dev/null`` avoids polluting the tree.
    out = "/dev/null" if os.name == "posix" else "nul"
    cmd = [compiler, "-c", source, "-o", out]
    return _dispatch_and_evaluate(ws, cmd, "compile", timeout, env, artifact=None)


def _run_cmake_build(
    ws: pathlib.Path,
    args: dict[str, str],
    compiler: str,
    kind: str,
    timeout: int,
    env: dict[str, str],
) -> BuildResult:
    if not is_cmake_project(ws):
        return BuildResult(
            False,
            f"{kind}: no CMakeLists.txt in workspace (not a CMake project)",
            kind=kind,
        )
    src = args.get("src") or args.get("source") or args.get("_positional") or "."
    build = args.get("build") or "build"
    artifact = args.get("artifact")

    configure_cmd = _cmake_configure_cmd(src, build, compiler)
    conf = _dispatch_and_evaluate(
        ws, configure_cmd, kind, timeout, env, artifact=None, stage="configure"
    )
    if not conf.passed:
        return conf

    build_cmd = ["cmake", "--build", build, "-j"]
    return _dispatch_and_evaluate(
        ws, build_cmd, kind, timeout, env, artifact=artifact, stage="build"
    )


def _dispatch_and_evaluate(
    ws: pathlib.Path,
    cmd: list[str],
    kind: str,
    timeout: int,
    env: dict[str, str],
    *,
    artifact: str | None,
    stage: str = "",
) -> BuildResult:
    command_str = " ".join(shlex.quote(c) for c in cmd)
    try:
        stdout, stderr, exit_code, timed_out = _run_with_pgroup_timeout(
            cmd, cwd=ws, timeout_s=timeout, env=env
        )
    except FileNotFoundError as e:
        return BuildResult(
            False,
            f"{kind} criterion failed to launch {cmd[0]!r}: {e}",
            kind=kind,
            command=command_str,
        )
    except Exception as e:  # pragma: no cover - defensive
        return BuildResult(
            False, f"{kind} criterion errored: {e}", kind=kind, command=command_str
        )

    evidence_path = _persist_evidence(
        ws, kind, command_str, exit_code, stdout, stderr
    )
    combined = stdout + "\n" + stderr

    if timed_out:
        return BuildResult(
            False,
            f"{kind} criterion timed out after {timeout}s: {command_str}",
            kind=kind,
            command=command_str,
            exit_code=-1,
            stdout=stdout,
            stderr=stderr,
            evidence_path=evidence_path,
        )

    error_lines = extract_error_lines(combined)

    if exit_code != 0:
        reason_tail = "\n".join(error_lines) if error_lines else combined[-600:].strip()
        stage_txt = f" ({stage})" if stage else ""
        return BuildResult(
            False,
            f"{kind} criterion failed{stage_txt} (exit={exit_code}) "
            f"[{command_str}]: {reason_tail}",
            kind=kind,
            command=command_str,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            evidence_path=evidence_path,
            error_lines=error_lines,
        )

    # A zero exit is not sufficient for link: an unresolved symbol on some
    # toolchains is reported without a non-zero code.
    lowered = combined.lower()
    for marker in UNRESOLVED_SYMBOL_MARKERS:
        if marker in lowered:
            return BuildResult(
                False,
                f"{kind} criterion produced unresolved-symbol errors "
                f"[{command_str}]: {marker!r}",
                kind=kind,
                command=command_str,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                evidence_path=evidence_path,
                error_lines=error_lines or [marker],
            )

    if artifact:
        art_path = ws / artifact
        if not art_path.exists():
            return BuildResult(
                False,
                f"{kind} criterion succeeded but expected artifact not produced: "
                f"{artifact!r}",
                kind=kind,
                command=command_str,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                evidence_path=evidence_path,
            )

    return BuildResult(
        True,
        "",
        kind=kind,
        command=command_str,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        evidence_path=evidence_path,
    )
