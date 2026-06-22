"""Semantic-equivalence verifier for smelly AC auto-repair.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence auto-apply.
Per-feature opt-out via auto_repair=False.

Public API::

    from bob3.semantic_equivalence_verifier import (
        verify_semantic_equivalence,
        auto_repair_ac,
    )

    is_equiv, rationale = verify_semantic_equivalence(original, rewrite)

    result = auto_repair_ac(
        feature_id="feat-001",
        findings=[...],
        original_acs=["The system should process requests."],
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts

Integration with bob3.linter::

    from bob3.linter import detect_smells
    from bob3.semantic_equivalence_verifier import auto_repair_ac

    findings = detect_smells(ac_text)
    result = auto_repair_ac(
        feature_id=feature_id,
        findings=findings,
        original_acs=[ac_text],
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.linter_ac_repair import (
    auto_repair_ac as _auto_repair_ac,
    semantic_equivalence_check as _semantic_equivalence_check,
)

__all__ = [
    "verify_semantic_equivalence",
    "auto_repair_ac",
]


def verify_semantic_equivalence(
    original: str,
    rewrite: str,
) -> tuple[bool, str]:
    """Verify that rewrite is semantically equivalent to original via LLM judge.

    Feeds original + rewrite to a separate LLM judge. If the judge cannot infer
    they impose the same observable constraint, returns (False, rationale).

    Parameters
    ----------
    original:
        The original acceptance criterion text.
    rewrite:
        The rewritten acceptance criterion text.

    Returns
    -------
    tuple[bool, str]
        (is_equivalent, rationale). On any LLM error returns (False, error_message).

    Raises
    ------
    ValueError
        If either argument is not a string.
    """
    return _semantic_equivalence_check(original, rewrite)


def auto_repair_ac(
    feature_id: str,
    findings: list[Any],
    original_acs: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Apply auto-repairs for ERROR-severity findings that pass equivalence check.

    Integrates with bob3.linter: pass SmellFinding objects produced by
    ``bob3.linter.detect_smells`` as the ``findings`` parameter.

    For each ERROR-severity finding with a suggested_rewrite, feeds the original
    and rewrite to an LLM judge. Only rewrites confirmed as semantically
    equivalent are applied. Per-feature opt-out via auto_repair=False.

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being repaired.
    findings:
        List of smell finding dicts or SmellFinding objects. Each must have:
        smell_id, smell_name, severity, text, detail, suggested_rewrite.
    original_acs:
        The original list of acceptance criteria strings.
    repairs_log:
        Path to append repair records. Defaults to ``repairs.log`` in workspace root.
    auto_repair:
        When False, detection runs but no rewrites are applied (per-feature opt-out).

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
    return _auto_repair_ac(
        feature_id=feature_id,
        findings=findings,
        original_acs=original_acs,
        repairs_log=repairs_log,
        auto_repair=auto_repair,
    )
