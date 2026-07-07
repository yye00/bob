"""clang-AST resolution for ``Function defined:`` / ``Class defined:`` ACs.

The generic verifier (:mod:`bob.enhanced_verification`) resolves
``Function defined:`` / ``Class defined:`` criteria on C++ projects with an
``is_cpp`` branch that does ``re.search(f"{name}\\(", content)`` over
``*.cpp``/``*.hpp``/``*.h``. That substring match:

* false-**PASSES** on call sites, comments, forward declarations, and
  unrelated overloads;
* false-**FAILS** on templated / namespaced / operator forms; and
* silently **skips** ``.cc`` / ``.cxx`` / ``.hip`` / ``.cu`` / ``.cuh``.

This module replaces that heuristic for CMake / ``compile_commands.json``
projects with a real clang-tooling probe. It runs ``clang-query`` against the
project's compile database with a matcher that requires a genuine
*definition with a non-empty body*::

    match functionDecl(hasName("ns::foo"),
                        isDefinition(),
                        hasBody(compoundStmt(unless(statementCountIs(0)))))

and, for classes::

    match cxxRecordDecl(hasName("ns::Bar"), isDefinition())

This proves the symbol is genuinely DEFINED against the real preprocessed AST
— handling namespaces, templates, macros, and overloads — the same way the
Python ``def`` / ``class`` branch does, rather than matching source text.

When clang tooling is unavailable (no ``clang-query`` on PATH, or no
``compile_commands.json``), the probe returns a PASS-with-warning result
(``available=False``, ``passed=True``, logged like the existing
``FILE_EXISTS_BASENAME_FALLBACK`` path) rather than silently degrading to the
gameable regex.

Public API
----------
search_for_function_clang(workspace, func_name, *, run_query=None) -> bool
    True if *func_name* is defined (non-empty body) per clang-query, or
    PASS-with-warning when clang tooling is unavailable.
search_for_class_clang(workspace, class_name, *, run_query=None) -> bool
    True if *class_name* is a defined ``class``/``struct`` per clang-query, or
    PASS-with-warning when clang tooling is unavailable.
ClangProbeResult
    Structured result (available / passed / reason / matched) for callers that
    need the reason string.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

logger = logging.getLogger(__name__)

CLANG_TOOLING_UNAVAILABLE = "CLANG_TOOLING_UNAVAILABLE"

# A query runner takes (clang_query_exe, build_dir, matcher) and returns the
# number of definition matches clang-query reported. Injectable for tests.
QueryRunner = Callable[[str, Path, str], int]


@dataclass
class ClangProbeResult:
    """Outcome of a clang-AST definition probe.

    Attributes:
        available: True when ``clang-query`` and a ``compile_commands.json``
            were both found and the probe actually ran.
        passed: The verdict callers should honor. True when the symbol is
            genuinely defined, OR when clang tooling was unavailable (a
            PASS-with-warning, mirroring ``FILE_EXISTS_BASENAME_FALLBACK``).
        matched: True only when clang-query reported ≥1 definition match. Always
            False when ``available`` is False.
        reason: A short machine-readable reason (e.g.
            ``CLANG_TOOLING_UNAVAILABLE:no compile_commands.json``) or ``""``.
    """

    available: bool
    passed: bool
    matched: bool
    reason: str = ""


def _validate_name(name: str, kind: str) -> str:
    if not isinstance(name, str):
        raise ValueError(f"{kind} must be a str, got {type(name).__name__!r}")
    stripped = name.strip()
    if not stripped:
        raise ValueError(f"{kind} must be a non-empty string")
    return stripped


def _validate_workspace(workspace: Union[str, Path]) -> Path:
    if workspace is None:
        raise ValueError("workspace must not be None")
    if not isinstance(workspace, (str, Path)):
        raise ValueError(
            f"workspace must be a str or Path, got {type(workspace).__name__!r}"
        )
    if not str(workspace).strip():
        raise ValueError("workspace must not be an empty path")
    return Path(workspace)


def _find_clang_query() -> Optional[str]:
    """Return the path to ``clang-query`` (any versioned variant) or None."""
    for exe in ("clang-query", "clang-query-19", "clang-query-18",
                "clang-query-17", "clang-query-16", "clang-query-15"):
        found = shutil.which(exe)
        if found:
            return found
    return None


def _find_compile_commands(workspace: Path) -> Optional[Path]:
    """Locate a compile_commands.json in the workspace root or a build/ dir."""
    for candidate in (
        workspace / "compile_commands.json",
        workspace / "build" / "compile_commands.json",
    ):
        if candidate.is_file():
            return candidate
    for match in workspace.rglob("compile_commands.json"):
        if match.is_file():
            return match
    return None


def _function_matcher(func_name: str) -> str:
    """clang-query matcher for a function/method DEFINITION with a non-empty body."""
    return (
        f'match functionDecl(hasName("{func_name}"), isDefinition(), '
        f"hasBody(compoundStmt(unless(statementCountIs(0)))))"
    )


def _class_matcher(class_name: str) -> str:
    """clang-query matcher for a class/struct DEFINITION (not a forward decl)."""
    return f'match cxxRecordDecl(hasName("{class_name}"), isDefinition())'


def _default_run_query(clang_query_exe: str, build_dir: Path, matcher: str) -> int:
    """Drive clang-query and return the number of definition matches.

    ``clang-query -p <build> -c '<matcher>'`` prints one ``Match #N:`` line per
    match plus a trailing ``N match(es).`` summary. We parse the summary count.
    Runs only when clang-query is genuinely on PATH (guarded by the caller), so
    it is not exercised in environments without clang tooling.
    """
    proc = subprocess.run(
        [clang_query_exe, "-p", str(build_dir), "-c", matcher],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"clang-query failed (exit {proc.returncode}): {proc.stderr[:500]}"
        )
    return _parse_match_count(proc.stdout)


def _parse_match_count(stdout: str) -> int:
    """Parse clang-query stdout for its ``N match(es).`` summary line."""
    count = 0
    for line in stdout.splitlines():
        line = line.strip()
        if line.endswith("match.") or line.endswith("matches."):
            head = line.split()[0]
            try:
                count = int(head)
            except (ValueError, IndexError):
                continue
    return count


def _probe(
    workspace: Union[str, Path],
    name: str,
    kind: str,
    matcher_fn: Callable[[str], str],
    run_query: Optional[QueryRunner],
) -> ClangProbeResult:
    """Shared probe for functions and classes.

    Raises:
        ValueError: on invalid *name* or *workspace* (error path).
    """
    clean_name = _validate_name(name, kind)
    ws = _validate_workspace(workspace)

    clang_query = _find_clang_query()
    if clang_query is None:
        reason = f"{CLANG_TOOLING_UNAVAILABLE}:clang-query not on PATH"
        logger.warning(
            "CLANG_AST_RESOLUTION: %s for %r %r — PASS-with-warning "
            "(not degrading to gameable regex)",
            reason, kind, clean_name,
        )
        return ClangProbeResult(
            available=False, passed=True, matched=False, reason=reason
        )

    cc_path = _find_compile_commands(ws)
    if cc_path is None:
        reason = f"{CLANG_TOOLING_UNAVAILABLE}:no compile_commands.json"
        logger.warning(
            "CLANG_AST_RESOLUTION: %s for %r %r — PASS-with-warning "
            "(not degrading to gameable regex)",
            reason, kind, clean_name,
        )
        return ClangProbeResult(
            available=False, passed=True, matched=False, reason=reason
        )

    runner = run_query if run_query is not None else _default_run_query
    build_dir = cc_path.parent
    matcher = matcher_fn(clean_name)
    try:
        match_count = runner(clang_query, build_dir, matcher)
    except Exception as exc:  # clang-query crash / parse error
        reason = f"{CLANG_TOOLING_UNAVAILABLE}:clang-query error: {exc}"
        logger.warning(
            "CLANG_AST_RESOLUTION: %s for %r %r — PASS-with-warning",
            reason, kind, clean_name,
        )
        return ClangProbeResult(
            available=False, passed=True, matched=False, reason=reason
        )

    matched = match_count > 0
    return ClangProbeResult(
        available=True,
        passed=matched,
        matched=matched,
        reason="" if matched else "no clang-AST definition found",
    )


def probe_function_definition(
    workspace: Union[str, Path],
    func_name: str,
    *,
    run_query: Optional[QueryRunner] = None,
) -> ClangProbeResult:
    """Structured clang-AST probe for a function DEFINITION.

    Args:
        workspace: Root of the C++ project (holds ``compile_commands.json``).
        func_name: The (optionally namespaced) function/method name, e.g.
            ``ns::foo`` or ``foo``.
        run_query: Optional injected query runner ``(exe, build_dir, matcher)
            -> int`` returning the match count. Defaults to driving the real
            ``clang-query`` binary.

    Returns:
        A :class:`ClangProbeResult`.

    Raises:
        ValueError: when *func_name* is not a non-empty string or *workspace*
            is None/empty.
    """
    return _probe(workspace, func_name, "function", _function_matcher, run_query)


def probe_class_definition(
    workspace: Union[str, Path],
    class_name: str,
    *,
    run_query: Optional[QueryRunner] = None,
) -> ClangProbeResult:
    """Structured clang-AST probe for a class/struct DEFINITION.

    Args:
        workspace: Root of the C++ project (holds ``compile_commands.json``).
        class_name: The (optionally namespaced) class/struct name.
        run_query: Optional injected query runner (see
            :func:`probe_function_definition`).

    Returns:
        A :class:`ClangProbeResult`.

    Raises:
        ValueError: when *class_name* is not a non-empty string or *workspace*
            is None/empty.
    """
    return _probe(workspace, class_name, "class", _class_matcher, run_query)


def search_for_function_clang(
    workspace: Union[str, Path],
    func_name: str,
    *,
    run_query: Optional[QueryRunner] = None,
) -> bool:
    """True if *func_name* is genuinely DEFINED per clang-query.

    Drop-in replacement for the ``is_cpp`` branch of
    :func:`bob.enhanced_verification._search_for_function` on CMake projects.
    Returns True when clang-query reports a definition with a non-empty body,
    or — when clang tooling is unavailable — a PASS-with-warning (True), never
    silently degrading to the gameable ``name(`` regex.

    Args:
        workspace: Root of the C++ project.
        func_name: The function/method name (may be namespaced ``ns::foo``).
        run_query: Optional injected query runner for testing.

    Returns:
        The ``.passed`` field of the probe result.

    Raises:
        ValueError: on invalid *func_name* / *workspace*.
    """
    return probe_function_definition(
        workspace, func_name, run_query=run_query
    ).passed


def search_for_class_clang(
    workspace: Union[str, Path],
    class_name: str,
    *,
    run_query: Optional[QueryRunner] = None,
) -> bool:
    """True if *class_name* is a genuinely DEFINED class/struct per clang-query.

    Drop-in replacement for the ``is_cpp`` branch of
    :func:`bob.enhanced_verification._search_for_class` on CMake projects.
    Returns True on a real definition, or PASS-with-warning (True) when clang
    tooling is unavailable — never the gameable ``class Name`` regex.

    Args:
        workspace: Root of the C++ project.
        class_name: The class/struct name (may be namespaced).
        run_query: Optional injected query runner for testing.

    Returns:
        The ``.passed`` field of the probe result.

    Raises:
        ValueError: on invalid *class_name* / *workspace*.
    """
    return probe_class_definition(
        workspace, class_name, run_query=run_query
    ).passed


__all__ = [
    "CLANG_TOOLING_UNAVAILABLE",
    "ClangProbeResult",
    "probe_class_definition",
    "probe_function_definition",
    "search_for_class_clang",
    "search_for_function_clang",
]
