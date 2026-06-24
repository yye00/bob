"""Auto-repair of smelly ACs with semantic-equivalence verification.

Per-smell, the linter emits a suggested_rewrite. A semantic-equivalence check
feeds the original + rewrite to a separate LLM judge; if it cannot infer they
impose the same observable constraint, the rewrite is rejected.
ERROR-severity rewrites that pass equivalence are auto-applied.
Per-feature opt-out via auto_repair=False.

This module exposes the canonical public API mandated by the acceptance criteria.
The underlying implementation lives in ``auto_repair`` (src/auto_repair.py).

Public API::

    from auto_repair_ac import semantic_equivalence_check, apply_error_severity_rewrites

    is_equiv, rationale = semantic_equivalence_check(original, rewrite)

    result = apply_error_severity_rewrites(
        feature_id="feat-001",
        findings=[...],
        original_acs=["The system should process requests."],
    )
    result["repaired_acs"]     # list of (possibly repaired) ACs
    result["repairs_applied"]  # list of repair dicts
"""

from __future__ import annotations

from auto_repair import (
    apply_error_severity_rewrites,
    semantic_equivalence_check,
)

__all__ = [
    "semantic_equivalence_check",
    "apply_error_severity_rewrites",
]
