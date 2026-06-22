"""Test-implementation coupling detector for Bob3 (feature 884b9e46).

Detects suspicious structural coupling between test files and implementation
files using AST analysis. Flags three categories of coupling:

1. ``internal_import`` — a test file uses relative imports or imports a
   private/internal sub-module (name starting with ``_``) from the package
   under test.
2. ``shared_helper`` — a non-trivial helper function has the same normalized
   AST structure in both a test file and a source file.
3. ``identical_constant`` — a module-level constant (uppercase name bound to
   a literal value) appears with the same name *and* value in both a test file
   and a source file.

All three patterns indicate that the test and implementation share code that
should be private to one side, which makes it trivially easy to "pass" tests
by copy-pasting rather than implementing correctly.

Public API
----------
- ``detect_internal_imports(workspace)`` → list[CouplingFinding]
- ``detect_shared_helpers(workspace)`` → list[CouplingFinding]
- ``detect_identical_constants(workspace)`` → list[CouplingFinding]
- ``check_test_impl_coupling(workspace)`` → CouplingResult
"""

from __future__ import annotations

import ast
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum number of "meaningful operations" (calls, attribute accesses, binary
# operators) inside a function body to consider it for shared-helper detection.
# This filters out trivial functions like ``noop()`` or ``return x`` (0–1 ops)
# while still flagging functions with real logic such as
# ``return text.strip().lower()`` (2+ ops).
# ---------------------------------------------------------------------------
_MIN_HELPER_OPS = 2

# ---------------------------------------------------------------------------
# Constant names that are well-known pytest/test infrastructure; these are
# legitimately defined in test files and should NOT be flagged even when
# they happen to also appear in a source file.
# ---------------------------------------------------------------------------
_EXCLUDED_CONSTANT_NAMES: frozenset[str] = frozenset(
    {
        "pytestmark",
        "pytest_plugins",
        "PYTEST_DONT_REWRITE",
        "__version__",
        "__all__",
        "__author__",
    }
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CouplingFinding:
    """A detected coupling between a test file and an implementation file.

    Attributes:
        kind:      One of ``"internal_import"``, ``"shared_helper"``,
                   ``"identical_constant"``.
        test_file: Path to the test file (relative to workspace).
        impl_file: Path to the implementation file (relative to workspace),
                   or ``""`` when the finding concerns only the test file.
        detail:    Human-readable explanation of the finding.
    """

    kind: str
    test_file: str
    impl_file: str
    detail: str


@dataclass
class CouplingResult:
    """Aggregated result of a full test-implementation coupling scan.

    Attributes:
        is_flagged: True when any coupling was detected.
        findings:   List of all individual coupling findings.
        summary:    Human-readable summary of the scan result.
    """

    is_flagged: bool
    findings: list[CouplingFinding] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Internal helpers — file discovery
# ---------------------------------------------------------------------------


def _collect_test_files(workspace: Path) -> list[Path]:
    """Return all .py files under tests/ that are reachable from workspace."""
    tests_root = workspace / "tests"
    if not tests_root.exists():
        return []
    return sorted(tests_root.rglob("*.py"))


def _collect_src_files(workspace: Path) -> list[Path]:
    """Return all .py files under src/ that are reachable from workspace."""
    src_root = workspace / "src"
    if not src_root.exists():
        return []
    return sorted(src_root.rglob("*.py"))


def _safe_parse(path: Path) -> ast.Module | None:
    """Parse a Python file and return its AST, or None on error."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        logger.debug("test_coupling_detector: could not parse %s", path)
        return None


def _rel(path: Path, workspace: Path) -> str:
    """Return path relative to workspace as a POSIX string."""
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# 1. Internal import detection
# ---------------------------------------------------------------------------


def _is_internal_import(module_name: str, level: int) -> bool:
    """Return True when an import looks like an internal/private reference.

    Rules:
    - Any relative import (level > 0) from a test file is suspicious — tests
      should use absolute public API imports.
    - Absolute imports where any dotted segment starts with ``_`` are private
      modules and should not be imported from test files.
    """
    if level > 0:
        return True
    if not module_name:
        return False
    parts = module_name.split(".")
    return any(part.startswith("_") for part in parts)


def detect_internal_imports(*, workspace: Path) -> list[CouplingFinding]:
    """Detect test files that import internal or private implementation modules.

    Scans every test file under ``workspace/tests/`` and flags:
    - Relative imports (``from . import X``, ``from .. import Y``)
    - Absolute imports of private/internal modules (any ``_``-prefixed segment)

    Returns a list of :class:`CouplingFinding` with kind ``"internal_import"``.
    """
    findings: list[CouplingFinding] = []

    for test_file in _collect_test_files(workspace):
        tree = _safe_parse(test_file)
        if tree is None:
            continue

        rel_test = _rel(test_file, workspace)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = node.level  # 0 = absolute, >0 = relative
                if _is_internal_import(module, level):
                    if level > 0:
                        detail = (
                            f"{rel_test}:{node.lineno}: relative import "
                            f"'from {'.' * level}{module} import …' — "
                            "test files must use absolute public-API imports"
                        )
                    else:
                        detail = (
                            f"{rel_test}:{node.lineno}: import of private module "
                            f"'{module}' — modules with '_' segments are internal"
                        )
                    findings.append(
                        CouplingFinding(
                            kind="internal_import",
                            test_file=rel_test,
                            impl_file="",
                            detail=detail,
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# 2. Shared helper detection
# ---------------------------------------------------------------------------


def _normalize_function(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return a normalized string representing the structural shape of a function.

    Normalization strips identifier names (replaced by positional placeholders)
    and replaces literal constants with ``CONST``, so two functions with
    identical logic but different variable names hash to the same value.
    """
    tokens: list[str] = []

    def _visit(node: ast.AST) -> None:
        if isinstance(node, (ast.Name, ast.arg)):
            tokens.append("NAME")
        elif isinstance(node, ast.Attribute):
            tokens.append("ATTR")
            _visit(node.value)
            return
        elif isinstance(node, ast.Constant):
            tokens.append("CONST")
        elif isinstance(node, ast.alias):
            tokens.append("ALIAS")
        else:
            tokens.append(type(node).__name__)
        for child in ast.iter_child_nodes(node):
            _visit(child)

    # Normalize the function body only (skip the name and decorators).
    for stmt in func.body:
        _visit(stmt)

    return hashlib.sha256(" ".join(tokens).encode()).hexdigest()


def _count_operations(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count meaningful AST operations inside a function body.

    Counts ast.Call, ast.Attribute, ast.BinOp, and ast.UnaryOp nodes so that
    trivial functions (``pass``, ``return x``) score 0–1 and functions with
    real logic score >= 2.
    """
    return sum(
        1
        for node in ast.walk(func)
        if isinstance(node, (ast.Call, ast.Attribute, ast.BinOp, ast.UnaryOp))
    )


def _collect_function_fingerprints(
    tree: ast.Module,
    rel_path: str,
) -> dict[str, str]:
    """Collect fingerprints of all non-trivial top-level functions in tree.

    Returns a ``{function_name: fingerprint_hex}`` mapping.  Only functions
    with at least ``_MIN_HELPER_OPS`` meaningful operations are included,
    filtering out trivial stubs like ``pass`` or single ``return`` expressions.
    """
    fps: dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _count_operations(node) < _MIN_HELPER_OPS:
            continue
        fps[node.name] = _normalize_function(node)

    return fps


def detect_shared_helpers(*, workspace: Path) -> list[CouplingFinding]:
    """Detect helper functions with identical structure in both test and impl files.

    A helper is flagged when its normalized AST fingerprint matches between any
    test file and any source file.  This catches copy-pasted helpers even when
    they have been renamed.

    Returns a list of :class:`CouplingFinding` with kind ``"shared_helper"``.
    """
    # Build fingerprint → [(rel_path, func_name)] index for src/ files.
    src_fp_index: dict[str, list[tuple[str, str]]] = {}

    for src_file in _collect_src_files(workspace):
        tree = _safe_parse(src_file)
        if tree is None:
            continue
        rel_src = _rel(src_file, workspace)
        for name, fp in _collect_function_fingerprints(tree, rel_src).items():
            src_fp_index.setdefault(fp, []).append((rel_src, name))

    findings: list[CouplingFinding] = []

    for test_file in _collect_test_files(workspace):
        tree = _safe_parse(test_file)
        if tree is None:
            continue
        rel_test = _rel(test_file, workspace)
        for test_name, fp in _collect_function_fingerprints(tree, rel_test).items():
            if fp in src_fp_index:
                for rel_src, src_name in src_fp_index[fp]:
                    detail = (
                        f"Function '{test_name}' in {rel_test} has the same "
                        f"normalized AST structure as '{src_name}' in {rel_src}"
                    )
                    findings.append(
                        CouplingFinding(
                            kind="shared_helper",
                            test_file=rel_test,
                            impl_file=rel_src,
                            detail=detail,
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# 3. Identical constant detection
# ---------------------------------------------------------------------------


def _collect_module_constants(tree: ast.Module) -> dict[str, object]:
    """Collect top-level ``NAME = <literal>`` assignments from a module AST.

    Only uppercase names bound to simple literals (int, float, str, bytes,
    bool, None) are collected.  Compound values (lists, dicts, etc.) are
    excluded to avoid false positives on structural fixtures.

    Returns a ``{name: value}`` mapping.
    """
    constants: dict[str, object] = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        # Only simple ``NAME = expr`` assignments (single target).
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        # Only ALL_CAPS names (module-level constants by convention).
        if not name.isupper():
            continue
        # Only simple literal values.
        value_node = node.value
        if not isinstance(value_node, ast.Constant):
            continue
        value = value_node.value
        if not isinstance(value, (int, float, str, bytes, bool, type(None))):
            continue
        constants[name] = value

    return constants


def detect_identical_constants(*, workspace: Path) -> list[CouplingFinding]:
    """Detect module-level constants with the same name and value in test and impl.

    A constant is flagged when it appears in both a test file and a source file
    with exactly the same name and the same literal value.  This pattern
    indicates the constant was copy-pasted rather than imported from a shared
    location, which can mask errors when the implementation changes.

    Returns a list of :class:`CouplingFinding` with kind ``"identical_constant"``.
    """
    # Build {name: {value: [rel_src_path]}} index for src/ constants.
    src_constants: dict[str, dict[object, list[str]]] = {}

    for src_file in _collect_src_files(workspace):
        tree = _safe_parse(src_file)
        if tree is None:
            continue
        rel_src = _rel(src_file, workspace)
        for name, value in _collect_module_constants(tree).items():
            src_constants.setdefault(name, {}).setdefault(value, []).append(rel_src)

    findings: list[CouplingFinding] = []

    for test_file in _collect_test_files(workspace):
        if test_file.name == "conftest.py":
            continue
        tree = _safe_parse(test_file)
        if tree is None:
            continue
        rel_test = _rel(test_file, workspace)

        for name, value in _collect_module_constants(tree).items():
            if name in _EXCLUDED_CONSTANT_NAMES:
                continue
            if name not in src_constants:
                continue
            if value not in src_constants[name]:
                continue
            for rel_src in src_constants[name][value]:
                detail = (
                    f"Constant '{name} = {value!r}' defined in both "
                    f"{rel_test} and {rel_src} — import from one location"
                )
                findings.append(
                    CouplingFinding(
                        kind="identical_constant",
                        test_file=rel_test,
                        impl_file=rel_src,
                        detail=detail,
                    )
                )

    return findings


# ---------------------------------------------------------------------------
# Top-level check
# ---------------------------------------------------------------------------


def check_test_impl_coupling(*, workspace: Path) -> CouplingResult:
    """Run all three coupling checks and return an aggregated result.

    Runs :func:`detect_internal_imports`, :func:`detect_shared_helpers`, and
    :func:`detect_identical_constants` in sequence and merges all findings.

    Args:
        workspace: Root of the project to scan.

    Returns:
        A :class:`CouplingResult` with ``is_flagged=True`` when any coupling
        was detected, plus the full list of findings and a summary string.
    """
    if not workspace.exists():
        return CouplingResult(
            is_flagged=False,
            findings=[],
            summary="Workspace does not exist; no coupling scan performed",
        )

    all_findings: list[CouplingFinding] = []

    all_findings.extend(detect_internal_imports(workspace=workspace))
    all_findings.extend(detect_shared_helpers(workspace=workspace))
    all_findings.extend(detect_identical_constants(workspace=workspace))

    if not all_findings:
        return CouplingResult(
            is_flagged=False,
            findings=[],
            summary="No test-implementation coupling detected",
        )

    by_kind: dict[str, int] = {}
    for f in all_findings:
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1

    kind_summary = ", ".join(f"{v} {k}" for k, v in sorted(by_kind.items()))
    summary = f"Test-implementation coupling detected: {kind_summary}"
    detail_lines = [f.detail for f in all_findings[:10]]
    if len(all_findings) > 10:
        detail_lines.append(f"(and {len(all_findings) - 10} more)")
    summary += "\n" + "\n".join(detail_lines)

    return CouplingResult(
        is_flagged=True,
        findings=all_findings,
        summary=summary,
    )
