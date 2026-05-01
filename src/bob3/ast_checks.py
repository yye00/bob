"""AST-based detection of stub functions and mock usage in source files (F122).

Uses ast.parse() and ast.walk() to analyze Python source code and detect:

1. Stub functions in src/ files:
   Error-severity (definitive stubs):
   - Functions with only 'pass' as body (after optional docstring)
   - Functions with only '...' (Ellipsis) as body (after optional docstring)
   - Functions that only 'raise NotImplementedError' (after optional docstring)

   Warning-severity (heuristic stubs — softer signals, may have false
   positives, included to catch agents that bypass the error patterns by
   writing trivial returns):
   - Functions whose entire body is a single ``return <literal>``
     (None, 0, "", [], {}, False, True)
   - Computation-named functions (compute_*, calculate_*, solve_*, find_*,
     get_*, fetch_*, parse_*) that return a literal — flagged on top of the
     plain literal-return rule with a more specific message.
   - Methods whose body is a single ``return self.<attr>`` where
     ``self.<attr>`` is never assigned anywhere else in the enclosing class.

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


# Function-name prefixes that strongly suggest the function is supposed to
# perform a computation. A function whose name starts with one of these and
# whose body is a single literal return is almost certainly an unfinished
# stub masquerading as real code.
_COMPUTATION_NAME_PREFIXES: tuple[str, ...] = (
    "compute_",
    "calculate_",
    "solve_",
    "find_",
    "get_",
    "fetch_",
    "parse_",
)

# Bare names that match the "computation" heuristic exactly (so e.g. ``def
# compute(): return 0`` is flagged just like ``def compute_x(): return 0``).
_COMPUTATION_NAME_EXACT: frozenset[str] = frozenset(
    p.rstrip("_") for p in _COMPUTATION_NAME_PREFIXES
)


@dataclass
class StubFinding:
    """A detected stub function.

    ``severity`` is ``"error"`` for the original definitive stub patterns
    (pass / ... / raise NotImplementedError) and ``"warning"`` for the
    heuristic patterns (literal returns, computation-named literal returns,
    ``return self.<attr>`` for an attribute never assigned).
    """

    filepath: str
    function_name: str
    line: int
    reason: str
    severity: str = "error"


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
    """Check if a function body is a definitive (error-severity) stub pattern.

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


# ---------------------------------------------------------------------------
# Warning-severity heuristics for trivial-return stubs
# ---------------------------------------------------------------------------
#
# These catch the bypasses that a determined agent can use to defeat the
# strict pass/ellipsis/raise-NotImplementedError patterns: writing
# ``def foo(): return 0`` or ``def parse(x): return None`` is semantically a
# stub but not an AST-pattern stub. We treat them as warnings because they
# can have legitimate uses (e.g., a getter that genuinely should return None
# until populated, a default-zero constant), but they should still surface
# during review.


_LITERAL_NAMES = {"None": None, "True": True, "False": False}


def _is_simple_literal(node: ast.expr) -> bool:
    """Return True if ``node`` is a literal value of a basic kind.

    Recognised literals:
    - ``None``, ``True``, ``False`` (ast.Constant)
    - numeric/string Constant nodes (0, 0.0, "", b"")
    - empty list/tuple/set/dict literals
    """
    if isinstance(node, ast.Constant):
        # Ellipsis is handled separately as a definitive stub.
        return node.value is not Ellipsis
    if isinstance(node, ast.List) and not node.elts:
        return True
    if isinstance(node, ast.Tuple) and not node.elts:
        return True
    if isinstance(node, ast.Set) and not node.elts:
        return True
    if isinstance(node, ast.Dict) and not node.keys:
        return True
    return False


def _literal_repr(node: ast.expr) -> str:
    """Render the literal at ``node`` as a short tag for the finding reason."""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.List):
        return "[]"
    if isinstance(node, ast.Tuple):
        return "()"
    if isinstance(node, ast.Set):
        return "set()"
    if isinstance(node, ast.Dict):
        return "{}"
    return "<literal>"


def _function_name_suggests_computation(name: str) -> bool:
    """Return True if ``name`` matches the computation-name heuristic."""
    if name in _COMPUTATION_NAME_EXACT:
        return True
    return name.startswith(_COMPUTATION_NAME_PREFIXES)


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and _is_docstring(body[0]):
        return body[1:]
    return body


def _single_return_literal(body: list[ast.stmt]) -> ast.expr | None:
    """Return the literal expression if the body is a single ``return <literal>``.

    Skips a leading docstring. Returns ``None`` when the body is something
    else (multiple statements, no return, return of a non-literal, bare
    ``return`` without a value, etc.).
    """
    effective = _strip_docstring(body)
    if len(effective) != 1:
        return None
    stmt = effective[0]
    if not isinstance(stmt, ast.Return):
        return None
    value = stmt.value
    if value is None:
        # Bare ``return`` — treat as literal None for consistency.
        return ast.Constant(value=None)
    if _is_simple_literal(value):
        return value
    return None


def _single_return_self_attr(body: list[ast.stmt]) -> str | None:
    """Return the attribute name if body is a single ``return self.<attr>``."""
    effective = _strip_docstring(body)
    if len(effective) != 1:
        return None
    stmt = effective[0]
    if not isinstance(stmt, ast.Return):
        return None
    value = stmt.value
    if not isinstance(value, ast.Attribute):
        return None
    obj = value.value
    if not (isinstance(obj, ast.Name) and obj.id == "self"):
        return None
    return value.attr


def _collect_self_assignments(class_node: ast.ClassDef) -> set[str]:
    """Return the set of ``self.<attr>`` names assigned anywhere in ``class_node``.

    Walks every method body and records attributes that appear on the LHS of
    any assignment, augmented assignment, or annotated assignment. This is the
    allowlist used to decide whether ``return self.<attr>`` is plausibly real
    code (attribute is set somewhere) vs. a stub (attribute is never set).
    """
    assigned: set[str] = set()

    def _record_target(target: ast.expr) -> None:
        if isinstance(target, ast.Attribute):
            obj = target.value
            if isinstance(obj, ast.Name) and obj.id == "self":
                assigned.add(target.attr)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                _record_target(elt)
        elif isinstance(target, ast.Starred):
            _record_target(target.value)

    for node in ast.walk(class_node):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                _record_target(tgt)
        elif isinstance(node, ast.AugAssign):
            _record_target(node.target)
        elif isinstance(node, ast.AnnAssign):
            _record_target(node.target)

    return assigned


def _check_function_body_warning(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    self_assigned_attrs: set[str] | None,
) -> str | None:
    """Check warning-severity stub heuristics for a function/method body.

    ``self_assigned_attrs`` is the set of ``self.<x>`` names assigned in the
    enclosing class (or ``None`` for free functions). It is used to decide
    whether ``return self.<attr>`` is suspicious.
    """
    body = func.body
    if not body:
        return None

    literal_node = _single_return_literal(body)
    if literal_node is not None:
        rendered = _literal_repr(literal_node)
        if _function_name_suggests_computation(func.name):
            return (
                f"Computation-named function returns only literal {rendered} "
                "(likely stub)"
            )
        return f"Body is only 'return {rendered}' (likely stub)"

    if self_assigned_attrs is not None:
        attr = _single_return_self_attr(body)
        if attr is not None and attr not in self_assigned_attrs:
            return (
                f"Body is only 'return self.{attr}' but self.{attr} is never "
                "assigned in this class (likely stub)"
            )

    return None


def detect_stub_functions(source: str, filepath: str) -> list[StubFinding]:
    """Detect stub functions in Python source code using AST analysis.

    Walks the AST looking for FunctionDef and AsyncFunctionDef nodes and
    classifies each into one of two severities:

    Error-severity (definitive stubs):
    - pass
    - ...
    - raise NotImplementedError

    Warning-severity (heuristic stubs — may have false positives):
    - body is a single ``return <literal>``
    - body is a single ``return <literal>`` and the function name suggests
      computation (compute_*, calculate_*, solve_*, find_*, get_*, fetch_*,
      parse_*) — same flag, more specific reason
    - body is a single ``return self.<attr>`` where ``self.<attr>`` is never
      assigned anywhere else in the enclosing class

    Only examines the function's own top-level body, avoiding false positives
    from nested statements like 'except Exception: pass'.

    Args:
        source: Python source code as a string.
        filepath: Path to the file (for reporting).

    Returns:
        List of StubFinding instances. Each carries a ``severity`` of
        ``"error"`` (definitive stub) or ``"warning"`` (heuristic stub).
    """
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        logger.debug("Could not parse %s, skipping stub detection", filepath)
        return []

    findings: list[StubFinding] = []

    # Map each FunctionDef/AsyncFunctionDef to its enclosing ClassDef (if any)
    # so the ``return self.<attr>`` heuristic can scope the assigned-attribute
    # set to the right class.
    func_to_class: dict[int, ast.ClassDef] = {}
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef):
            for item in cls.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_to_class[id(item)] = cls

    # Cache assigned-attribute sets per class to avoid recomputing for each
    # method.
    class_assigned_cache: dict[int, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Definitive stub patterns first — these always win at error severity.
        reason = _check_function_body(node.body)
        if reason is not None:
            findings.append(
                StubFinding(
                    filepath=filepath,
                    function_name=node.name,
                    line=node.lineno,
                    reason=reason,
                    severity="error",
                )
            )
            continue

        # Warning-severity heuristics.
        cls = func_to_class.get(id(node))
        self_assigned: set[str] | None = None
        if cls is not None:
            cached = class_assigned_cache.get(id(cls))
            if cached is None:
                cached = _collect_self_assignments(cls)
                class_assigned_cache[id(cls)] = cached
            self_assigned = cached

        warn_reason = _check_function_body_warning(node, self_assigned)
        if warn_reason is not None:
            findings.append(
                StubFinding(
                    filepath=filepath,
                    function_name=node.name,
                    line=node.lineno,
                    reason=warn_reason,
                    severity="warning",
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
        - passed: bool (True if no error-severity stubs and no mocks in src/)
        - stub_findings: list[StubFinding] — error-severity stubs only.
          Kept narrow so legacy callers gating on
          ``len(result["stub_findings"]) == 0`` retain their original
          semantics; warning-severity heuristics live in ``stub_warnings``.
        - stub_warnings: list[StubFinding] — warning-severity heuristic
          stubs (literal returns, ``return self.<unassigned>``, etc.).
          Advisory only — they do not flip ``passed``.
        - mock_findings: list[MockFinding]
        - summary: str (human-readable summary covering both severities)
    """
    all_stub_findings: list[StubFinding] = []
    all_mock_findings: list[MockFinding] = []

    for filepath, source in sorted(sources.items()):
        all_stub_findings.extend(detect_stub_functions(source, filepath))
        all_mock_findings.extend(detect_mock_usage(source, filepath))

    # Split error vs warning. Only error-severity stub findings (the original
    # definitive patterns) block verification — that preserves the existing
    # ``stub_findings`` contract for callers like superpowers' verification
    # checklist that gate on ``len(result["stub_findings"]) == 0``. The
    # warning-severity heuristics live in ``stub_warnings`` so they're
    # discoverable for review but do not silently fail legacy callers.
    error_stub_findings = [f for f in all_stub_findings if f.severity == "error"]
    warning_stub_findings = [f for f in all_stub_findings if f.severity != "error"]

    passed = len(error_stub_findings) == 0 and len(all_mock_findings) == 0

    # Build summary
    summary_parts: list[str] = []
    if error_stub_findings:
        summary_parts.append(
            f"Found {len(error_stub_findings)} stub function(s):"
        )
        for f in error_stub_findings:
            summary_parts.append(f"  {f.filepath}:{f.line} {f.function_name} - {f.reason}")
    if warning_stub_findings:
        summary_parts.append(
            f"Found {len(warning_stub_findings)} possible stub function(s) (warning):"
        )
        for f in warning_stub_findings:
            summary_parts.append(
                f"  {f.filepath}:{f.line} {f.function_name} - {f.reason}"
            )
    if all_mock_findings:
        summary_parts.append(
            f"Found {len(all_mock_findings)} mock usage(s) in src/:"
        )
        for f in all_mock_findings:
            summary_parts.append(f"  {f.filepath}:{f.line} - {f.reason}")
    if passed and not warning_stub_findings:
        summary_parts.append("No stubs or mock usage detected in source files.")

    return {
        "passed": passed,
        "stub_findings": error_stub_findings,
        "stub_warnings": warning_stub_findings,
        "mock_findings": all_mock_findings,
        "summary": "\n".join(summary_parts),
    }
