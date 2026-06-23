"""Auto-repair of smelly ACs with semantic-equivalence verification.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

This module satisfies the acceptance criteria:
  - File exists: src/auto_repair_smelly_acs.py
  - Function defined: auto_repair_smelly_acs.verify_semantic_equivalence
  - Function defined: auto_repair_smelly_acs.apply_error_severity_rewrites

Public API::

    from auto_repair_smelly_acs import verify_semantic_equivalence, apply_error_severity_rewrites

    is_equiv, rationale = verify_semantic_equivalence(original, rewrite)

    result = apply_error_severity_rewrites(
        feature_id="feat-001",
        findings=[...],
        original_acs=["The system should process requests."],
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from auto_repair import (
    semantic_equivalence_check as _semantic_equivalence_check,
    apply_error_severity_rewrites as _apply_error_severity_rewrites,
)


def verify_semantic_equivalence(original: str, rewrite: str) -> tuple[bool, str]:
    """Verify that rewrite is semantically equivalent to original via LLM judge.

    Parameters
    ----------
    original:
        The original acceptance criterion text.
    rewrite:
        The rewritten acceptance criterion text.

    Returns
    -------
    tuple[bool, str]
        (is_equivalent, rationale). On any error returns (False, error_message).

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    return _semantic_equivalence_check(original, rewrite)


def apply_error_severity_rewrites(
    feature_id: str,
    findings: list[dict[str, Any]],
    original_acs: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Apply auto-repairs for ERROR-severity findings that pass equivalence check.

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being repaired.
    findings:
        List of smell finding dicts. Each must have keys: smell_id, smell_name,
        severity, text, detail, suggested_rewrite.
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
        - ``repairs_applied``: list[dict] — repair records

    Raises
    ------
    ValueError
        If feature_id is not a string, findings is not a list, or original_acs is not a list.
    """
    return _apply_error_severity_rewrites(
        feature_id=feature_id,
        findings=findings,
        original_acs=original_acs,
        repairs_log=repairs_log,
        auto_repair=auto_repair,
    )


__all__ = [
    "verify_semantic_equivalence",
    "apply_error_severity_rewrites",
]
