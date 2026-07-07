"""Top-level façade for the BF-7 CodeT patch-mode workflow.

Re-exports the reviewable diff-plan primitives from
:mod:`bob.brownfield.patch_planner` under the canonical ``bob.patch_planner``
import path so that callers (and the ``integration: bob.patch_planner``
acceptance criterion) resolve against a stable public module.
"""

from __future__ import annotations

from bob.brownfield.patch_planner import (
    PatchPlanner,
    apply_diff_plan,
    check_scope_guard,
    emit_diff_plan,
    generate_diff_plan,
    plan_diff,
    rollback_changes,
    rollback_edits,
    synthesize_unified_diff,
)

__all__ = [
    "PatchPlanner",
    "apply_diff_plan",
    "check_scope_guard",
    "emit_diff_plan",
    "generate_diff_plan",
    "plan_diff",
    "rollback_changes",
    "rollback_edits",
    "synthesize_unified_diff",
]
