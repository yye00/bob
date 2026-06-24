"""Auto-repair of smelly ACs with semantic-equivalence verification.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

This module is the canonical ``linter.auto_repair`` entry point. The underlying
implementation lives in ``auto_repair`` (src/auto_repair.py) and is re-exported
here with the names mandated by the acceptance criteria.

Public API::

    from linter.auto_repair import verify_semantic_equivalence, apply_error_severity_rewrites

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
    apply_error_severity_rewrites,
    semantic_equivalence_check as _semantic_equivalence_check,
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


__all__ = [
    "verify_semantic_equivalence",
    "apply_error_severity_rewrites",
]
