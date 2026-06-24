"""AC rewriter with semantic-equivalence verification for smelly acceptance criteria.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

Public API::

    from bob3.ac_rewriter import (
        apply_semantic_equivalence_check,
        auto_repair_error_severity_ac,
    )

    is_equiv, rationale = apply_semantic_equivalence_check(original, rewrite)

    result = auto_repair_error_severity_ac(
        feature_id="feat-001",
        findings=[...],
        original_acs=["The system should process requests."],
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts

Integration with bob3.linter::

    from bob3.linter import detect_smells
    from bob3.ac_rewriter import auto_repair_error_severity_ac

    findings = detect_smells(ac_text)
    result = auto_repair_error_severity_ac(
        feature_id=feature_id,
        findings=[f._asdict() if hasattr(f, '_asdict') else vars(f) for f in findings],
        original_acs=[ac_text],
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.auto_repair import (
    semantic_equivalence_check as _semantic_equivalence_check,
    apply_auto_repair as _apply_auto_repair,
)

__all__ = [
    "apply_semantic_equivalence_check",
    "auto_repair_error_severity_ac",
    # AC-required canonical names
    "semantic_equivalence_check",
    "auto_repair_ac",
]


def apply_semantic_equivalence_check(
    original: str,
    rewrite: str,
) -> tuple[bool, str]:
    """Check whether rewrite is semantically equivalent to original via LLM judge.

    Feeds original + rewrite to a separate LLM judge. If the judge cannot infer
    they impose the same observable constraint, returns (False, rationale).

    Parameters
    ----------
    original:
        The original acceptance criterion text.
    rewrite:
        The proposed rewrite to verify.

    Returns
    -------
    tuple[bool, str]
        (is_equivalent, rationale). On any LLM error returns (False, error_message).

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    if not isinstance(original, str):
        raise ValueError(f"original must be a string, got {type(original).__name__}")
    if not isinstance(rewrite, str):
        raise ValueError(f"rewrite must be a string, got {type(rewrite).__name__}")

    return _semantic_equivalence_check(original, rewrite)


def auto_repair_error_severity_ac(
    feature_id: str,
    findings: list[dict[str, Any]],
    original_acs: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Apply auto-repairs for ERROR-severity findings that pass semantic equivalence.

    For each ERROR-severity smell finding with a suggested_rewrite, verifies
    semantic equivalence via LLM judge. Only rewrites that pass are applied.
    Per-feature opt-out: set auto_repair=False to detect smells without applying.

    Integrates with bob3.linter: pass SmellFinding objects produced by
    ``bob3.linter.detect_smells`` as the ``findings`` parameter.

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being repaired.
    findings:
        List of smell finding dicts. Each must have keys: smell_id, smell_name,
        severity, text, detail, suggested_rewrite.
        Also accepts namedtuple/dataclass objects with those attributes.
    original_acs:
        The original list of acceptance criteria strings.
    repairs_log:
        Path to append repair records. Defaults to ``repairs.log`` in workspace root.
    auto_repair:
        When False, no rewrites are applied (per-feature opt-out).

    Returns
    -------
    dict with keys:
        - ``repaired_acs``: list[str] — ACs with ERROR-smell repairs applied
        - ``repairs_applied``: list[dict] — repair records (original, rewrite, rationale, ...)

    Raises
    ------
    ValueError
        If feature_id is not a string, findings is not a list, or original_acs is not a list.
    """
    if not isinstance(feature_id, str):
        raise ValueError(f"feature_id must be a string, got {type(feature_id).__name__}")
    if not isinstance(findings, list):
        raise ValueError(f"findings must be a list, got {type(findings).__name__}")
    if not isinstance(original_acs, list):
        raise ValueError(f"original_acs must be a list, got {type(original_acs).__name__}")

    return _apply_auto_repair(
        feature_id=feature_id,
        findings=findings,
        original_acs=original_acs,
        repairs_log=repairs_log,
        auto_repair=auto_repair,
    )


# Canonical AC-required aliases
semantic_equivalence_check = apply_semantic_equivalence_check
auto_repair_ac = auto_repair_error_severity_ac
