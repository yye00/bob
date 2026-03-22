"""AST-based detection of stub functions and mock usage in source files (F122).

Uses ast.parse() and ast.walk() to analyze Python source code and detect:

1. Stub functions in src/ files:
   - Functions with only 'pass' as body (after optional docstring)
   - Functions with only '...' (Ellipsis) as body (after optional docstring)
   - Functions that only 'raise NotImplementedError' (after optional docstring)

2. Mock usage in src/ files (mocks are only allowed in tests/):
   - 'from unittest.mock import ...'
   - 'import unittest.mock'
   - 'from mock import ...'
   - 'import mock'

CRITICAL: Avoids false positives by only examining top-level function bodies,
not nested statements like 'except Exception: pass'.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StubFinding:
    """A detected stub function."""

    filepath: str
    function_name: str
    line: int
    reason: str


@dataclass
class MockFinding:
    """A detected mock import or usage in a source file."""

    filepath: str
    line: int
    reason: str


def _is_docstring(node: ast.stmt) -> bool:
    """Check if a statement is a docstring (string expression)."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_pass(node: ast.stmt) -> bool:
    """Check if a statement is 'pass'."""
    return isinstance(node, ast.Pass)


def _is_ellipsis(node: ast.stmt) -> bool:
    """Check if a statement is '...' (Ellipsis expression)."""
    if not isinstance(node, ast.Expr):
        return False
    val = node.value
    if isinstance(val, ast.Constant) and val.value is ...:
        return True
    return False


def _is_raise_not_implemented(node: ast.stmt) -> bool:
    """Check if a statement is 'raise NotImplementedError' or 'raise NotImplementedError(...)'."""
    if not isinstance(node, ast.Raise):
        return False
    exc = node.exc
    if exc is None:
        return False
    # 'raise NotImplementedError'
    if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
        return True
    # 'raise NotImplementedError(...)'
    if isinstance(exc, ast.Call):
        func = exc.func
        if isinstance(func, ast.Name) and func.id == "NotImplementedError":
            return True
    return False


def _check_function_body(body: list[ast.stmt]) -> str | None:
    """Check if a function body is a stub pattern.

    Returns a reason string if the body is a stub, or None if it's real code.
    Skips leading docstrings when analyzing.
    """
    if not body:
        return None

    # Strip leading docstring
    effective_body = body[:]
    if effective_body and _is_docstring(effective_body[0]):
        effective_body = effective_body[1:]

    # After stripping docstring, should have exactly one statement for a stub
    if len(effective_body) != 1:
        return None

    stmt = effective_body[0]

    if _is_pass(stmt):
        return "Body is only 'pass' (stub)"
    if _is_ellipsis(stmt):
        return "Body is only Ellipsis '...' (stub)"
    if _is_raise_not_implemented(stmt):
        return "Body only raises NotImplementedError (stub)"

    return None


def detect_stub_functions(source: str, filepath: str) -> list[StubFinding]:
    """Detect stub functions in Python source code using AST analysis.

    Walks the AST looking for FunctionDef and AsyncFunctionDef nodes whose
    body (after an optional docstring) consists only of a stub pattern:
    - pass
    - ...
    - raise NotImplementedError

    Only examines the function's own top-level body, avoiding false positives
    from nested statements like 'except Exception: pass'.

    Args:
        source: Python source code as a string.
        filepath: Path to the file (for reporting).

    Returns:
        List of StubFinding instances for each detected stub function.
    """
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        logger.debug("Could not parse %s, skipping stub detection", filepath)
        return []

    findings: list[StubFinding] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        reason = _check_function_body(node.body)
        if reason is not None:
            findings.append(
                StubFinding(
                    filepath=filepath,
                    function_name=node.name,
                    line=node.lineno,
                    reason=reason,
                )
            )

    return findings


def detect_mock_usage(source: str, filepath: str) -> list[MockFinding]:
    """Detect mock imports and usage in Python source code.

    Only flags mock usage in src/ files; mock usage in tests/ is allowed.
    Detects:
    - 'from unittest.mock import ...'
    - 'import unittest.mock'
    - 'from mock import ...'
    - 'import mock'

    Args:
        source: Python source code as a string.
        filepath: Path to the file (for reporting).

    Returns:
        List of MockFinding instances for each detected mock usage.
        Returns empty list for files in tests/ directories.
    """
    # Mock usage is allowed in test files
    normalized = filepath.replace("\\", "/")
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        logger.debug("Could not parse %s, skipping mock detection", filepath)
        return []

    findings: list[MockFinding] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # 'from unittest.mock import ...'
            if module == "unittest.mock" or module.startswith("unittest.mock."):
                findings.append(
                    MockFinding(
                        filepath=filepath,
                        line=node.lineno,
                        reason=f"Import from unittest.mock: 'from {module} import ...'",
                    )
                )
            # 'from mock import ...'
            elif module == "mock" or module.startswith("mock."):
                findings.append(
                    MockFinding(
                        filepath=filepath,
                        line=node.lineno,
                        reason=f"Import from mock: 'from {module} import ...'",
                    )
                )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                # 'import unittest.mock'
                if name == "unittest.mock" or name.startswith("unittest.mock."):
                    findings.append(
                        MockFinding(
                            filepath=filepath,
                            line=node.lineno,
                            reason=f"Import of unittest.mock: 'import {name}'",
                        )
                    )
                # 'import mock'
                elif name == "mock" or name.startswith("mock."):
                    findings.append(
                        MockFinding(
                            filepath=filepath,
                            line=node.lineno,
                            reason=f"Import of mock: 'import {name}'",
                        )
                    )

    return findings


def verify_no_stubs_or_mocks(
    sources: dict[str, str],
) -> dict:
    """Run combined stub and mock detection on a set of source files.

    This is the integration point for the verification checklist.
    Checks all provided sources for stubs and mock usage.

    Args:
        sources: Mapping of filepath -> source code content.

    Returns:
        Dict with keys:
        - passed: bool (True if no stubs or mocks found in src/)
        - stub_findings: list[StubFinding]
        - mock_findings: list[MockFinding]
        - summary: str (human-readable summary)
    """
    all_stub_findings: list[StubFinding] = []
    all_mock_findings: list[MockFinding] = []

    for filepath, source in sorted(sources.items()):
        all_stub_findings.extend(detect_stub_functions(source, filepath))
        all_mock_findings.extend(detect_mock_usage(source, filepath))

    passed = len(all_stub_findings) == 0 and len(all_mock_findings) == 0

    # Build summary
    summary_parts: list[str] = []
    if all_stub_findings:
        summary_parts.append(
            f"Found {len(all_stub_findings)} stub function(s):"
        )
        for f in all_stub_findings:
            summary_parts.append(f"  {f.filepath}:{f.line} {f.function_name} - {f.reason}")
    if all_mock_findings:
        summary_parts.append(
            f"Found {len(all_mock_findings)} mock usage(s) in src/:"
        )
        for f in all_mock_findings:
            summary_parts.append(f"  {f.filepath}:{f.line} - {f.reason}")
    if passed:
        summary_parts.append("No stubs or mock usage detected in source files.")

    return {
        "passed": passed,
        "stub_findings": all_stub_findings,
        "mock_findings": all_mock_findings,
        "summary": "\n".join(summary_parts),
    }
