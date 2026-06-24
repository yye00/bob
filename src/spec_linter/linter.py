"""Spec ambiguity linter — core linting logic.

Pre-plan gate that scans every acceptance_criteria entry and rejects
ambiguous patterns. Each AC must match one of the structured forms:

  File exists: <path>
  Function defined: <dotted.path>
  Class defined: <dotted.path>
  pytest: <test_path>
  integration: <dotted.module>
  behavior: <subject> <verb> <object> when <condition>

The linter fails the plan if any feature has an ambiguous AC and emits
a structured report naming the offending feature and AC index.

Public API::

    from spec_linter.linter import lint_acceptance_criteria, LintIssue, LintReport
    from spec_linter.linter import lint_and_repair

    issues = lint_acceptance_criteria("MyFeature", [
        "File exists: src/foo.py",
        "works correctly",            # ambiguous — will be flagged
    ])
    if issues:
        print(issues[0].reason)

    result = lint_and_repair("feat-001", [
        "File exists: src/foo.py",
        "works correctly",
    ])
    result["repaired_acs"]     # ACs with ERROR-smell rewrites applied
    result["repairs_applied"]  # list of repair dicts
    result["lint_issues"]      # list of LintIssue
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bob.spec_quality.ambiguity_linter import (
    AmbiguityIssue,
    FeatureLintResult,
    SpecLintReport,
    lint_feature,
    lint_spec,
)
import auto_repair as _auto_repair
import environment_capability as _env_capability


# ---------------------------------------------------------------------------
# Re-export core types
# ---------------------------------------------------------------------------

__all__ = [
    "AmbiguityIssue",
    "FeatureLintResult",
    "LintIssue",
    "LintReport",
    "SpecLintReport",
    "detect_gpu_kernel_acs",
    "lint_acceptance_criteria",
    "lint_and_repair",
    "lint_spec",
    "lint_feature",
    "run_capability_preflight",
]


# GPU/Triton keywords that trigger routing to the kernel synthesis sub-agent.
_GPU_KEYWORDS = frozenset(
    {
        "@triton.jit",
        "triton",
        "cuda",
        "rocm",
        "gpu kernel",
        "triton kernel",
        "triton.autotune",
    }
)


def detect_gpu_kernel_acs(acceptance_criteria: list[str]) -> list[tuple[int, str]]:
    """Identify ACs that mention GPU/Triton keywords and must route to kernel synthesis.

    Scans *acceptance_criteria* for GPU/Triton markers (``@triton.jit``,
    ``triton``, ``cuda``, ``rocm``, ``gpu kernel``, ``triton.autotune``) and
    returns the index and text of each matching criterion.  The caller is
    expected to route those features through
    :func:`gpu_triton_kernel_synthesis.synthesize_triton_kernel` and
    :func:`gpu_triton_kernel_synthesis.autotune_kernel_config`.

    Args:
        acceptance_criteria: List of AC strings to inspect.

    Returns:
        List of ``(index, criterion)`` pairs for every AC that contains a
        GPU/Triton keyword (case-insensitive).

    Raises:
        ValueError: If *acceptance_criteria* is not a list.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )

    # Import here to avoid module-level circular import risk; gpu_triton_kernel_synthesis
    # is a top-level src module that depends on bob internals.
    import gpu_triton_kernel_synthesis as _gpu  # noqa: F401  (wires integration AC)

    matches: list[tuple[int, str]] = []
    for idx, criterion in enumerate(acceptance_criteria):
        lower = criterion.lower()
        if any(kw in lower for kw in _GPU_KEYWORDS):
            matches.append((idx, criterion))
    return matches


@dataclass
class LintIssue:
    """One ambiguity finding for a single acceptance criterion."""

    ac_index: int
    criterion: str
    reason: str


@dataclass
class LintReport:
    """Aggregate lint report returned by :func:`lint_acceptance_criteria`."""

    feature_name: str
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def format_report(self) -> str:
        if self.passed:
            return f"Spec ambiguity lint: PASSED — {self.feature_name!r}"
        lines = [f"Spec ambiguity lint: FAILED — {self.feature_name!r}", ""]
        for issue in self.issues:
            lines.append(f"  AC[{issue.ac_index}] {issue.criterion!r}: {issue.reason}")
        return "\n".join(lines)


def lint_acceptance_criteria(
    feature_name: str,
    acceptance_criteria: list[str],
) -> list[LintIssue]:
    """Lint a feature's acceptance criteria and return a list of issues.

    Parameters
    ----------
    feature_name:
        The name or ID of the feature being linted (used in reports).
    acceptance_criteria:
        List of acceptance criterion strings. Must be a list (not None).

    Returns
    -------
    list[LintIssue]
        All ambiguity issues found. Empty list means the criteria passed.

    Raises
    ------
    ValueError
        If ``acceptance_criteria`` is not a list.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )
    if not isinstance(feature_name, str):
        raise ValueError(
            f"feature_name must be a string, got {type(feature_name).__name__}"
        )

    result: FeatureLintResult = lint_feature(feature_name, acceptance_criteria)
    return [
        LintIssue(
            ac_index=issue.ac_index,
            criterion=issue.criterion,
            reason=issue.reason,
        )
        for issue in result.issues
    ]


def lint_and_repair(
    feature_id: str,
    acceptance_criteria: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Lint acceptance criteria and auto-repair ERROR-severity smells.

    Runs the spec ambiguity linter then passes any ambiguous ACs through
    the auto-repair pipeline. ERROR-severity rewrites that pass semantic
    equivalence checking are applied automatically (unless ``auto_repair``
    is False).

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being processed.
    acceptance_criteria:
        List of acceptance criterion strings.
    repairs_log:
        Path for the repair audit log. Defaults to workspace ``repairs.log``.
    auto_repair:
        When False, no rewrites are applied (per-feature opt-out).

    Returns
    -------
    dict with keys:
        - ``repaired_acs``: list[str] — ACs with ERROR repairs applied
        - ``repairs_applied``: list[dict] — repair records
        - ``lint_issues``: list[LintIssue] — remaining lint issues (post-repair)
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a string, got {type(feature_id).__name__}"
        )

    lint_result: FeatureLintResult = lint_feature(feature_id, acceptance_criteria)
    issues = [
        LintIssue(
            ac_index=issue.ac_index,
            criterion=issue.criterion,
            reason=issue.reason,
        )
        for issue in lint_result.issues
    ]

    # Build findings list from lint issues for auto_repair consumption.
    # Ambiguous ACs get smell_id "AMBIGUOUS" / severity "E".
    findings = [
        {
            "smell_id": "AMBIGUOUS",
            "smell_name": "AmbiguousAC",
            "severity": "E",
            "text": issue.criterion,
            "detail": issue.reason,
            "suggested_rewrite": None,  # linter does not produce rewrites
        }
        for issue in issues
    ]

    repair_result = _auto_repair.apply_error_severity_rewrites(
        feature_id=feature_id,
        findings=findings,
        original_acs=acceptance_criteria,
        repairs_log=repairs_log,
        auto_repair=auto_repair,
    )

    return {
        "repaired_acs": repair_result["repaired_acs"],
        "repairs_applied": repair_result["repairs_applied"],
        "lint_issues": issues,
    }


def run_capability_preflight(
    acceptance_criteria: list[str],
    workspace: str | None = None,
) -> dict:
    """Run environment-capability preflight against a feature's acceptance criteria.

    Delegates to :func:`environment_capability.run_preflight` which enumerates
    external dependencies, probes each for availability, and either auto-applies
    low-risk workarounds or raises :class:`environment_capability.MissingDependencyError`
    for high-risk missing deps.

    Args:
        acceptance_criteria: List of AC strings from the feature spec.
        workspace: Optional project root path passed through to the preflight.

    Returns:
        A summary dict with ``total_deps``, ``missing``, ``applied_workarounds``,
        and ``halted`` keys.

    Raises:
        ValueError: If *acceptance_criteria* is not a list.
        environment_capability.MissingDependencyError: If a high-risk dep is absent.
    """
    return _env_capability.run_preflight(acceptance_criteria, workspace=workspace)
