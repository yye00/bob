"""Spec linter — pre-spawn quality gate (F-4466afdf).

Before spawning any sub-agent, run this linter over the feature's acceptance
criteria to catch common specification problems:

1. **Ambiguous criteria** — no measurable outcome (TBD/TODO placeholders,
   vague English without a testable verb or prefix like "File exists:" /
   "pytest:" / "python:").

2. **Missing edge cases** — only happy-path criteria with no failure-path
   coverage (warned when the entire criterion list lacks any pytest: or
   python: criterion that could exercise error paths).

3. **Redundant criteria** — exact (case-insensitive) duplicate criteria in
   the same list.

4. **Banned operations in python: criteria** — any ``python: <expression>``
   criterion whose expression contains a banned module import or dangerous
   call (the same allowlist enforced by ``enhanced_verification``). These
   always produce a hard-fail because running the spec would be unsafe.

Severity:
- ``ERROR`` → hard fail: spawn is blocked.
- ``WARNING`` → spawn proceeds; warnings are filed to
  ``reviews/findings.yaml`` when ``file_warnings=True``.

Public API::

    from bob.spec_linter_pre_spawn_quality_gate import (
        LintIssue,
        LintResult,
        LintSeverity,
        lint_acceptance_criteria,
        lint_feature_spec,
        file_warnings_to_registry,
    )

    result = lint_feature_spec(
        name=feature.name,
        description=feature.description,
        acceptance_criteria=feature.acceptance_criteria,
        file_warnings=True,
    )
    if result.hard_fail:
        raise RuntimeError(f"Spec quality gate blocked spawn: {result.errors}")
"""

from __future__ import annotations

import ast
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from bob.ears import EARSClauseKind, extract_ears_clauses

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity enum
# ---------------------------------------------------------------------------

class LintSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Issue and Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LintIssue:
    """One lint finding for a single acceptance criterion."""

    criterion: str
    reason: str
    severity: LintSeverity
    category: str


@dataclass
class LintResult:
    """Aggregate result of linting an acceptance-criteria list."""

    issues: list[LintIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == LintSeverity.ERROR]

    @property
    def warnings(self) -> list[LintIssue]:
        return [i for i in self.issues if i.severity == LintSeverity.WARNING]

    @property
    def hard_fail(self) -> bool:
        return any(i.severity == LintSeverity.ERROR for i in self.issues)

    @property
    def passed(self) -> bool:
        return not self.hard_fail


# ---------------------------------------------------------------------------
# Banned-operation detection (reuses enhanced_verification allowlist logic)
# ---------------------------------------------------------------------------

# Banned top-level modules in python: criteria (mirrors enhanced_verification).
_BANNED_MODULES: frozenset[str] = frozenset({
    "subprocess", "socket", "urllib", "http", "requests", "ftplib",
    "telnetlib", "smtplib", "shutil", "ctypes", "multiprocessing", "pty",
    "pickle", "marshal", "os", "pathlib", "tempfile", "glob",
    "importlib", "runpy", "pkgutil", "builtins",
})

# Banned bare call names.
_BANNED_CALL_NAMES: frozenset[str] = frozenset({
    "eval", "exec", "compile", "__import__", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "open",
})

# Banned attribute accesses (trailing attr name).
_BANNED_ATTRIBUTES: frozenset[str] = frozenset({
    "system", "popen", "spawnl", "spawnle", "spawnv", "spawnve",
    "execv", "execve", "execvp", "execvpe", "remove", "unlink",
    "rmdir", "removedirs", "rmtree", "environ", "putenv", "chmod",
    "chown", "kill", "killpg", "fork", "forkpty",
    "__class__", "__bases__", "__subclasses__", "__mro__", "mro",
    "__dict__", "__globals__", "__builtins__", "__init_subclass__",
    "__getattribute__", "__getattr__",
})


def _check_banned_operation(expression: str) -> str | None:
    """Return the first banned operation name found in *expression*, or None.

    Performs an AST scan identical in logic to
    ``enhanced_verification._expression_uses_banned_operation``.
    Returns ``None`` on syntax error (the runtime will catch that separately).
    """
    try:
        tree = ast.parse(expression, mode="exec")
    except SyntaxError:
        return None  # syntax error handled elsewhere

    def _banned_module(name: str) -> str | None:
        if not name:
            return None
        head = name.split(".", 1)[0]
        return head if head in _BANNED_MODULES else None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bad = _banned_module(alias.name)
                if bad:
                    return f"import {bad}"

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            bad = _banned_module(module)
            if bad:
                return f"from {bad} import ..."

        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _BANNED_CALL_NAMES:
                return func.id
            if isinstance(func, ast.Attribute):
                if func.attr in _BANNED_ATTRIBUTES:
                    return f".{func.attr}(...)"
                if func.attr in _BANNED_CALL_NAMES:
                    return f".{func.attr}(...)"

        elif isinstance(node, ast.Attribute):
            if node.attr in _BANNED_ATTRIBUTES:
                return f".{node.attr}"

        elif isinstance(node, ast.Name):
            if node.id in _BANNED_CALL_NAMES:
                return node.id

    return None


# ---------------------------------------------------------------------------
# Criterion form classification helpers
# ---------------------------------------------------------------------------

# Recognised criterion prefixes that indicate a measurable, testable outcome.
_MEASURABLE_PREFIXES: tuple[str, ...] = (
    "file exists:",
    "pytest:",
    "python:",
    "assert ",
    "check:",
    "verify:",
    "returns ",
    "raises ",
)

# Placeholder tokens that signal an unfinished criterion.
_PLACEHOLDER_TOKENS: frozenset[str] = frozenset({
    "tbd", "todo", "fixme", "xxx", "placeholder",
    "fill in later", "to be determined", "to be decided",
})

_PYTHON_CRITERION_PREFIX = "python:"


def _is_measurable(criterion: str) -> bool:
    """Return True if the criterion has a recognisable measurable form."""
    lower = criterion.strip().lower()
    return any(lower.startswith(p) for p in _MEASURABLE_PREFIXES)


def _is_placeholder(criterion: str) -> bool:
    """Return True if the criterion text is a known placeholder."""
    lower = criterion.strip().lower()
    return lower in _PLACEHOLDER_TOKENS or any(tok in lower for tok in _PLACEHOLDER_TOKENS)


def _has_assertion_in_python_expr(expression: str) -> bool:
    """Return True if the python expression contains an assert or comparison."""
    try:
        tree = ast.parse(expression, mode="exec")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assert, ast.Compare)):
            return True
    return False


# ---------------------------------------------------------------------------
# Core linting logic
# ---------------------------------------------------------------------------

def lint_acceptance_criteria(criteria: list[str]) -> LintResult:
    """Lint a list of acceptance-criterion strings.

    Checks for:
    - Empty / placeholder criteria (ambiguous, WARNING)
    - Non-measurable English-only criteria (ambiguous, WARNING)
    - Banned operations in ``python:`` criteria (banned_operation, ERROR)
    - Syntax errors in ``python:`` expressions (ambiguous, WARNING)
    - Exact duplicate criteria (redundant, WARNING)
    - All criteria being file-existence checks with no executable test
      path (missing_edge_case, WARNING)

    Returns a :class:`LintResult` with all collected issues.
    """
    issues: list[LintIssue] = []
    seen: dict[str, int] = {}  # normalised_criterion -> first_index

    has_executable_criterion = False  # any pytest: or python: criterion

    for criterion in criteria:
        stripped = criterion.strip()
        normalised = stripped.lower()

        # ---- empty criterion ----
        if not stripped:
            issues.append(LintIssue(
                criterion=stripped,
                reason="Criterion is empty; no measurable outcome can be verified.",
                severity=LintSeverity.WARNING,
                category="empty",
            ))
            continue

        # ---- redundancy check ----
        if normalised in seen:
            issues.append(LintIssue(
                criterion=stripped,
                reason=(
                    f"Duplicate of criterion #{seen[normalised] + 1}; "
                    "remove one to avoid misleading pass counts."
                ),
                severity=LintSeverity.WARNING,
                category="redundant",
            ))
        else:
            seen[normalised] = len(seen)

        # ---- placeholder / ambiguous check ----
        if _is_placeholder(stripped):
            issues.append(LintIssue(
                criterion=stripped,
                reason=(
                    f"Criterion appears to be a placeholder ({stripped!r}). "
                    "Replace with a concrete, measurable criterion."
                ),
                severity=LintSeverity.WARNING,
                category="ambiguous",
            ))
            continue

        if not _is_measurable(stripped):
            issues.append(LintIssue(
                criterion=stripped,
                reason=(
                    f"Criterion {stripped!r} has no recognisable measurable form. "
                    "Use a prefix like 'File exists:', 'pytest:', or 'python: assert ...'."
                ),
                severity=LintSeverity.WARNING,
                category="ambiguous",
            ))
            continue

        # ---- python: criterion checks ----
        lower = stripped.lower()
        if lower.startswith(_PYTHON_CRITERION_PREFIX):
            has_executable_criterion = True
            expression = stripped[len(_PYTHON_CRITERION_PREFIX):].strip()

            if not expression:
                issues.append(LintIssue(
                    criterion=stripped,
                    reason="python: criterion has an empty expression.",
                    severity=LintSeverity.WARNING,
                    category="ambiguous",
                ))
                continue

            # Check for banned operations (hard fail).
            banned = _check_banned_operation(expression)
            if banned is not None:
                issues.append(LintIssue(
                    criterion=stripped,
                    reason=(
                        f"python: criterion uses a banned operation ({banned!r}). "
                        "Use the 'pytest:' form for criteria that require "
                        "filesystem or shell access."
                    ),
                    severity=LintSeverity.ERROR,
                    category="banned_operation",
                ))
                continue

            # Check for syntax errors.
            try:
                ast.parse(expression, mode="exec")
            except SyntaxError as exc:
                issues.append(LintIssue(
                    criterion=stripped,
                    reason=f"python: criterion has a syntax error: {exc}",
                    severity=LintSeverity.WARNING,
                    category="ambiguous",
                ))
                continue

        elif lower.startswith("pytest:"):
            has_executable_criterion = True

    # ---- missing edge-case check ----
    # If there are criteria but none include an executable test (pytest: or
    # python:), warn that failure paths may not be exercised.
    non_empty = [c for c in criteria if c.strip()]
    if non_empty and not has_executable_criterion:
        issues.append(LintIssue(
            criterion="(all criteria)",
            reason=(
                "No executable criterion found (no 'pytest:' or 'python:' form). "
                "Consider adding a pytest criterion to cover failure paths."
            ),
            severity=LintSeverity.WARNING,
            category="missing_edge_case",
        ))

    return LintResult(issues=issues)


# ---------------------------------------------------------------------------
# Registry filing for warnings
# ---------------------------------------------------------------------------

def file_warnings_to_registry(
    issues: list[LintIssue],
    *,
    feature_name: str,
    registry_path: Path | None = None,
) -> None:
    """File warning-level issues to ``reviews/findings.yaml``.

    Uses :mod:`bob.reviews` if available; falls back to a minimal YAML
    append if the module is not importable (e.g. in isolated test runs).
    """
    warnings = [i for i in issues if i.severity == LintSeverity.WARNING]
    if not warnings:
        return

    try:
        from bob.reviews import (
            load_registry,
            save_registry,
            add_finding,
        )
        if registry_path is None:
            try:
                from bob.reviews import _registry_path
                registry_path = _registry_path()
            except (ImportError, FileNotFoundError):
                logger.warning("Could not locate reviews/findings.yaml; skipping registry filing.")
                return

        registry = load_registry(registry_path)
        for issue in warnings:
            add_finding(
                registry,
                round_prefix="R-spec-lint",
                title=f"Spec linter [{issue.category}]: {feature_name}",
                pattern=issue.category,
                files=[],
                severity="warning",
                status="open",
                tags=["spec-linter", issue.category],
                notes=f"Criterion: {issue.criterion!r}\nReason: {issue.reason}",
            )
        save_registry(registry, registry_path)
    except Exception as exc:
        logger.warning("Failed to file spec-linter warnings to registry: %s", exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def lint_feature_spec(
    *,
    name: str,
    description: str | None,
    acceptance_criteria: list[str] | str | None,
    file_warnings: bool = False,
    registry_path: Path | None = None,
) -> LintResult:
    """Lint a feature spec before spawning a sub-agent.

    Parameters
    ----------
    name:
        Feature name (used in registry filing messages).
    description:
        Feature description (currently unused but reserved for future checks).
    acceptance_criteria:
        Either a list of criterion strings, a JSON-encoded list, or ``None``.
    file_warnings:
        If ``True``, file WARNING-level issues to ``reviews/findings.yaml``.
    registry_path:
        Override for the path to ``findings.yaml``.

    Returns
    -------
    LintResult
        All issues found.  ``result.hard_fail`` is ``True`` if any ERROR-level
        issue was found; the caller should block spawn in that case.
    """
    # Extract EARS clauses from description and emit warnings when unwanted-
    # behaviour clauses exist but no acceptance criterion mentions property
    # testing (hypothesis) or the specific behaviour under test.
    ears_issues: list[LintIssue] = []
    if description:
        ears_clauses = extract_ears_clauses(description)
        unwanted_clauses = [c for c in ears_clauses if c.kind == EARSClauseKind.UNWANTED]
        if unwanted_clauses:
            # Flatten acceptance criteria for quick keyword search.
            ac_text = " ".join(
                c.lower()
                for c in (
                    acceptance_criteria
                    if isinstance(acceptance_criteria, list)
                    else [acceptance_criteria]
                    if isinstance(acceptance_criteria, str)
                    else []
                )
            )
            has_property_test_criterion = any(
                kw in ac_text
                for kw in ("hypothesis", "property", "fuzz", "shall not")
            )
            if not has_property_test_criterion:
                for clause in unwanted_clauses[:3]:  # cap to avoid flooding
                    ears_issues.append(LintIssue(
                        criterion=clause.raw,
                        reason=(
                            f"Description contains EARS unwanted-behaviour clause "
                            f"({clause.raw!r}) but no acceptance criterion covers "
                            "it with a property/fuzz test. Consider adding a "
                            "'pytest: hypothesis' criterion."
                        ),
                        severity=LintSeverity.WARNING,
                        category="missing_edge_case",
                    ))

    # Normalise acceptance_criteria to a list[str].
    criteria: list[str]
    if acceptance_criteria is None:
        result = LintResult(issues=ears_issues + [
            LintIssue(
                criterion="(none)",
                reason="Feature has no acceptance criteria defined.",
                severity=LintSeverity.WARNING,
                category="ambiguous",
            )
        ])
        if file_warnings:
            file_warnings_to_registry(result.issues, feature_name=name, registry_path=registry_path)
        return result

    if isinstance(acceptance_criteria, str):
        try:
            parsed = json.loads(acceptance_criteria)
            if isinstance(parsed, list):
                criteria = [str(c) for c in parsed]
            else:
                criteria = [acceptance_criteria]
        except (json.JSONDecodeError, ValueError):
            criteria = [acceptance_criteria]
    else:
        criteria = list(acceptance_criteria)

    if not criteria:
        result = LintResult(issues=ears_issues + [
            LintIssue(
                criterion="(empty list)",
                reason="Feature has an empty acceptance-criteria list.",
                severity=LintSeverity.WARNING,
                category="ambiguous",
            )
        ])
        if file_warnings:
            file_warnings_to_registry(result.issues, feature_name=name, registry_path=registry_path)
        return result

    result = lint_acceptance_criteria(criteria)
    result.issues[:0] = ears_issues  # prepend EARS warnings

    if file_warnings and result.warnings:
        file_warnings_to_registry(result.warnings, feature_name=name, registry_path=registry_path)

    return result
