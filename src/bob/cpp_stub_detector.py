"""C++/HIP no-stubs gate — AST-body heuristics + link-level undefined symbols.

bob's original anti-stub gate (:mod:`bob.ast_checks`, :mod:`bob.scaffolding_audit`)
only understands Python: ``_is_stub_function`` walks a Python ``ast`` for
``pass`` / ``...`` / ``raise NotImplementedError`` and for anything non-Python it
emits "Stub detection skipped (non-Python project)". That leaves a hole: a C++
implementer can ship ::

    float allreduce_bw() { /* TODO */ return 0; }
    void tune() { throw std::logic_error("not implemented"); }
    hipError_t launch() { return hipSuccess; }
    void empty() {}

and sail through ``no_stubs`` untouched.

This module closes the hole with two layers:

1. **Static** — :func:`detect_cpp_stubs` scans native sources
   (``.cpp .cc .cxx .hpp .h .hip .cu .cuh``) for trivial/empty bodies,
   "not implemented" throws, ``assert(false && "...")`` placeholders,
   pure-virtuals with no concrete override in the changed files,
   ``#error`` / ``static_assert(false)`` placeholders, ``#if 0`` blocks around
   target code, and ``TODO``/``FIXME``/``stub`` markers inside a function span.
2. **Link-level** — :func:`find_undefined_symbols` runs ``nm -uC`` (falling back
   to ``readelf -s``) over produced objects/libraries to enumerate undefined
   symbols no per-TU static check can see.

Both feed the same demote-to-NEEDS_HUMAN path the Python stub gate uses: a C++
feature passes only when its target resolves to a real, non-trivial definition
that links.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Full native extension set. The legacy `_search_for_function` missed .cu/.hip,
# exactly where RCCL kernels live — cover them explicitly here.
NATIVE_EXTENSIONS = frozenset(
    {".cpp", ".cc", ".cxx", ".hpp", ".h", ".hip", ".cu", ".cuh"}
)


@dataclass
class CppStubFinding:
    """A stub / placeholder pattern found in a native source file."""

    filepath: str
    line: int
    function: str
    reason: str
    code: str


@dataclass
class UndefinedSymbol:
    """An undefined symbol enumerated from a produced object/library."""

    artifact: str
    symbol: str


# ---------------------------------------------------------------------------
# Static heuristic layer
# ---------------------------------------------------------------------------

_NOT_IMPLEMENTED_MARKER = re.compile(
    r"not[\s_\-]*implement|unimplemented|todo|fixme|stub", re.IGNORECASE
)
_THROW_RE = re.compile(
    r"throw\s+std::(?:runtime_error|logic_error|exception)\s*\(", re.IGNORECASE
)
_ASSERT_FALSE_RE = re.compile(r"assert\s*\(\s*false\b", re.IGNORECASE)
_STATIC_ASSERT_FALSE_RE = re.compile(r"static_assert\s*\(\s*false\b", re.IGNORECASE)
_ERROR_DIRECTIVE_RE = re.compile(r"^\s*#\s*error\b")
_IF_ZERO_RE = re.compile(r"^\s*#\s*if\s+0\b")
_IFDEF_NEVER_RE = re.compile(r"^\s*#\s*ifdef\s+NEVER\b")
_MARKER_COMMENT_RE = re.compile(
    r"(?://|/\*).*(?:\bTODO\b|\bFIXME\b|\bstub\b)", re.IGNORECASE
)
_PURE_VIRTUAL_RE = re.compile(
    r"\bvirtual\b[^;{}]*\b(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*"
    r"(?:const\s*)?=\s*0\s*;"
)

# A function definition header: <ret> name(args) { ... — captures the name and
# the opening brace position. Deliberately loose; we validate via brace matching.
_FUNC_HEADER_RE = re.compile(
    r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*|noexcept\s*|override\s*"
    r"|final\s*)*\{"
)

# Trivial return bodies: return; return 0; return nullptr; return {}; return hipSuccess;
_TRIVIAL_RETURN_RE = re.compile(
    r"^return\s*"
    r"(?:0|nullptr|NULL|\{\s*\}|true|false|hipSuccess|cudaSuccess|ncclSuccess)?"
    r"\s*;$"
)


def _strip_line_comments(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments for body-triviality analysis."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", " ", text)
    return text


def _matching_brace(text: str, open_idx: int) -> int:
    """Return index of the brace matching the ``{`` at ``open_idx``, or -1."""
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _body_is_trivial(body: str) -> str | None:
    """Return a reason string if ``body`` (raw, incl. comments) is trivial."""
    raw = body
    # "not implemented" throws / asserts count regardless of other content.
    if _THROW_RE.search(raw) and _NOT_IMPLEMENTED_MARKER.search(raw):
        return "throws a 'not implemented' exception"
    if _ASSERT_FALSE_RE.search(raw) and _NOT_IMPLEMENTED_MARKER.search(raw):
        return "assert(false, ...) not-implemented placeholder"

    code = _strip_line_comments(body).strip()

    if code == "":
        return "empty function body"

    # Split into statements; keep it simple — join then split on ';'
    normalized = re.sub(r"\s+", " ", code).strip()
    # Single trivial return only.
    stmt = normalized.rstrip(";").strip()
    single = normalized
    if _TRIVIAL_RETURN_RE.match(re.sub(r"\s+", "", normalized)) or _TRIVIAL_RETURN_RE.match(
        single.replace(" ", "")
    ):
        return "trivial return-only body (no work performed)"

    # Only a bare throw of a not-implemented kind handled above; a lone throw
    # without marker is not necessarily a stub.
    return None


def _validate_sources(sources) -> None:
    if not isinstance(sources, dict):
        raise ValueError(
            f"sources must be a dict[str, str], got {type(sources).__name__}"
        )
    for key, value in sources.items():
        if not isinstance(key, str):
            raise ValueError(f"source path key must be str, got {type(key).__name__}")
        if not isinstance(value, str):
            raise ValueError(
                f"source content for {key!r} must be str, got {type(value).__name__}"
            )


def detect_cpp_stubs(sources: dict[str, str]) -> list[CppStubFinding]:
    """Detect C++/HIP stub / placeholder patterns in native source files.

    Args:
        sources: Mapping of ``filepath -> file content``. Only files with a
            native extension (``.cpp .cc .cxx .hpp .h .hip .cu .cuh``) are
            inspected; others are ignored.

    Returns:
        A list of :class:`CppStubFinding`. Empty when no stubs are found (and
        for empty/whitespace-only input).

    Raises:
        ValueError: if ``sources`` is not a ``dict[str, str]``.
    """
    _validate_sources(sources)

    findings: list[CppStubFinding] = []

    for filepath, content in sources.items():
        if Path(filepath).suffix.lower() not in NATIVE_EXTENSIONS:
            continue
        if not content or not content.strip():
            continue

        lines = content.splitlines()

        # Preprocessor placeholders (line-oriented).
        for idx, line in enumerate(lines, start=1):
            if _ERROR_DIRECTIVE_RE.match(line):
                findings.append(
                    CppStubFinding(filepath, idx, "<file>",
                                   "#error placeholder directive", line.strip())
                )
            if _STATIC_ASSERT_FALSE_RE.search(line):
                findings.append(
                    CppStubFinding(filepath, idx, "<file>",
                                   "static_assert(false) placeholder", line.strip())
                )
            if _IF_ZERO_RE.match(line) or _IFDEF_NEVER_RE.match(line):
                findings.append(
                    CppStubFinding(filepath, idx, "<file>",
                                   "disabled #if 0 / #ifdef NEVER block around code",
                                   line.strip())
                )

        # Pure-virtual declarations with no concrete override in the same file.
        for m in _PURE_VIRTUAL_RE.finditer(content):
            name = m.group("name")
            # A concrete override defines `name(...)` with a body somewhere.
            override = re.search(
                re.escape(name) + r"\s*\([^;{}]*\)\s*(?:const\s*|override\s*"
                r"|noexcept\s*|final\s*)*\{",
                content,
            )
            if not override:
                findings.append(
                    CppStubFinding(
                        filepath, _line_of(content, m.start()), name,
                        "pure-virtual with no concrete override in changed files",
                        m.group(0).strip(),
                    )
                )

        # Function-body triviality + in-span markers.
        for m in _FUNC_HEADER_RE.finditer(content):
            name = m.group("name")
            if name in ("if", "for", "while", "switch", "catch", "return"):
                continue
            open_idx = content.index("{", m.start())
            close_idx = _matching_brace(content, open_idx)
            if close_idx < 0:
                continue
            body = content[open_idx + 1 : close_idx]
            header_line = _line_of(content, m.start())

            reason = _body_is_trivial(body)
            if reason:
                findings.append(
                    CppStubFinding(filepath, header_line, name, reason,
                                   m.group(0).strip())
                )
                continue

            # Marker comments inside a non-trivial body still flag a stub.
            if _MARKER_COMMENT_RE.search(body):
                findings.append(
                    CppStubFinding(
                        filepath, header_line, name,
                        "TODO/FIXME/stub marker inside function body",
                        m.group(0).strip(),
                    )
                )

    return findings


# ---------------------------------------------------------------------------
# Link-level layer
# ---------------------------------------------------------------------------

def _nm_undefined(artifact: str) -> list[str] | None:
    """Return undefined symbol names via ``nm -uC``, or None if nm unusable."""
    if shutil.which("nm") is None:
        return None
    try:
        proc = subprocess.run(
            ["nm", "-uC", artifact],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 and not proc.stdout:
        return None
    symbols: list[str] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        # `nm -u` lines look like "                 U symbol" or "U symbol".
        if "U" in parts[:-1] or parts[0] == "U":
            symbols.append(parts[-1])
        elif len(parts) >= 2 and parts[-2] == "U":
            symbols.append(parts[-1])
    return symbols


def _readelf_undefined(artifact: str) -> list[str] | None:
    """Return undefined symbol names via ``readelf -s``, or None if unusable."""
    if shutil.which("readelf") is None:
        return None
    try:
        proc = subprocess.run(
            ["readelf", "-sW", artifact],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    symbols: list[str] = []
    for line in proc.stdout.splitlines():
        # Undefined symbols have "UND" in the Ndx column.
        if " UND " in line:
            parts = line.split()
            if parts and parts[-1] not in ("UND", ""):
                symbols.append(parts[-1])
    return symbols


def find_undefined_symbols(artifacts: list[str]) -> list[UndefinedSymbol]:
    """Enumerate undefined symbols in produced objects/libraries.

    Runs ``nm -uC`` on each artifact (falling back to ``readelf -s`` when nm is
    unavailable), catching cross-TU missing definitions that no per-TU static
    check can see.

    Args:
        artifacts: List of paths to object files / shared libraries / archives.

    Returns:
        A list of :class:`UndefinedSymbol`. Empty when there are no artifacts,
        no undefined symbols, or the toolchain is unavailable. Nonexistent
        paths are skipped.

    Raises:
        ValueError: if ``artifacts`` is not a list of strings.
    """
    if not isinstance(artifacts, list):
        raise ValueError(
            f"artifacts must be a list of str, got {type(artifacts).__name__}"
        )
    for a in artifacts:
        if not isinstance(a, str):
            raise ValueError(
                f"each artifact path must be str, got {type(a).__name__}"
            )

    results: list[UndefinedSymbol] = []
    for artifact in artifacts:
        if not Path(artifact).exists():
            continue
        symbols = _nm_undefined(artifact)
        if symbols is None:
            symbols = _readelf_undefined(artifact)
        if not symbols:
            continue
        for sym in symbols:
            results.append(UndefinedSymbol(artifact=artifact, symbol=sym))

    return results


__all__ = [
    "NATIVE_EXTENSIONS",
    "CppStubFinding",
    "UndefinedSymbol",
    "detect_cpp_stubs",
    "find_undefined_symbols",
]
