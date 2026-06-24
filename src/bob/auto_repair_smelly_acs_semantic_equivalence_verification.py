"""Auto-repair of smelly ACs with semantic-equivalence verification.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

Public entry point::

    from bob.auto_repair_smelly_acs_semantic_equivalence_verification import (
        auto_repair_smelly_acs_semantic_equivalence_verification,
    )

    result = auto_repair_smelly_acs_semantic_equivalence_verification(
        feature_id="feat-001",
        acceptance_criteria=[
            "The system should process requests.",
            "pytest: tests/test_foo.py -v",
        ],
    )
    result["repaired_acs"]      # list of (possibly repaired) ACs
    result["repairs_applied"]   # list of repair dicts
    result["smell_findings"]    # list of SmellFinding
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.ac_auto_repair import (
    apply_repairs,
    compute_auto_repair_rate,
    handle_missing_judge,
    reject_unequivalent_rewrite,
    repair_feature_acs,
    respect_opt_out,
    suggest_rewrite,
    verify_semantic_equivalence,
    EquivalenceJudgeUnavailableError,
    RewriteRejectedError,
)
from bob.spec_quality.smell_detectors import SmellFinding

__all__ = [
    "auto_repair_smelly_acs_semantic_equivalence_verification",
    "suggest_rewrite",
    "verify_semantic_equivalence",
    "apply_repairs",
    "repair_feature_acs",
    "respect_opt_out",
    "compute_auto_repair_rate",
    "handle_missing_judge",
    "reject_unequivalent_rewrite",
    "SmellFinding",
    "EquivalenceJudgeUnavailableError",
    "RewriteRejectedError",
]


def auto_repair_smelly_acs_semantic_equivalence_verification(
    feature_id: str,
    acceptance_criteria: list[str],
    auto_repair: bool = True,
    repairs_log: Path | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Detect smells in ACs, verify rewrites semantically, and auto-apply ERROR repairs.

    For each smell finding, the linter emits a suggested_rewrite. A separate
    LLM judge verifies semantic equivalence between the original and proposed
    rewrite. Only rewrites that pass the equivalence check and belong to
    ERROR-severity smells are auto-applied.

    Parameters
    ----------
    feature_id:
        Identifier for the feature whose ACs are being repaired.
    acceptance_criteria:
        List of AC strings to inspect and potentially repair.
    auto_repair:
        When False, detection and rewrite generation run but no rewrites are
        applied (per-feature opt-out).
    repairs_log:
        Path to append repair records. Defaults to ``repairs.log`` in the
        workspace root.
    known_feature_ids:
        Set of valid feature IDs in the spec (used by S17 dangling-ref check).

    Returns
    -------
    dict with keys:
        - ``repaired_acs``: list[str] — ACs with ERROR-smell repairs applied
        - ``repairs_applied``: list[dict] — repair records (original, rewrite, rationale, …)
        - ``smell_findings``: list[SmellFinding] — all detected findings
        - ``auto_repair_enabled``: bool — mirrors the ``auto_repair`` parameter

    Examples
    --------
    >>> from unittest.mock import patch
    >>> result = auto_repair_smelly_acs_semantic_equivalence_verification(
    ...     feature_id="feat-example",
    ...     acceptance_criteria=["pytest: tests/test_foo.py -v"],
    ... )
    >>> result["repaired_acs"]
    ['pytest: tests/test_foo.py -v']
    >>> result["repairs_applied"]
    []
    """
    result = repair_feature_acs(
        feature_id=feature_id,
        acceptance_criteria=acceptance_criteria,
        auto_repair=auto_repair,
        repairs_log=repairs_log,
        known_feature_ids=known_feature_ids,
    )
    result["auto_repair_enabled"] = auto_repair
    return result
