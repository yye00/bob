"""BF-7 — CodeT patch-mode + reviewable diff-plan artifact.

CodeR-style patch-mode for brownfield. Greenfield bob writes whole files;
brownfield must EDIT them. Each implementer subagent emits a reviewable
diff-plan artifact before applying edits, so the verifier (and optionally
a human via [[feedback-no-signoff]] exception path) can sanity-check scope.

Protocol enforced by this module:

  1. emit_diff_plan — write .bob/features/<id>/diff_plan.yaml before edits.
  2. apply_diff_plan — backup originals, apply hunks, return modified paths.
  3. rollback_changes — restore pre-edit blobs on AC failure.
  4. check_scope_guard — coordinator pre-dispatch guard; refuse if any touch
     path falls outside the localization allowlist.

This module re-exports the core patch-planner functions and exposes the
canonical entry point ``bf_7_codet_patch_mode_reviewable_diff_plan_artifact``
which returns a structured summary of the protocol.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.brownfield.patch_planner import (
    apply_diff_plan,
    check_scope_guard,
    emit_diff_plan,
    rollback_changes,
)

__all__ = [
    "bf_7_codet_patch_mode_reviewable_diff_plan_artifact",
    "emit_diff_plan",
    "apply_diff_plan",
    "rollback_changes",
    "check_scope_guard",
]


def bf_7_codet_patch_mode_reviewable_diff_plan_artifact(
    *,
    feature_id: str = "",
    touches: list[dict[str, Any]] | None = None,
    localization_allowlist: list[str] | None = None,
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Return a structured summary of the BF-7 patch-mode protocol.

    When called without arguments (e.g., for AC verification), returns a
    static summary of the protocol with all five protocol steps described.

    When called with feature_id / touches / localization_allowlist, also
    validates scope (if allowlist given), emits the diff_plan.yaml artifact,
    and returns the path to it.

    Args:
        feature_id:             Feature UUID (optional).
        touches:                List of touch dicts, each with 'path' and 'hunks'
                                (optional; required for plan emission).
        localization_allowlist: Allowed file paths for scope guard (optional).
        workspace:              Repo root; defaults to current directory.

    Returns:
        dict with keys:
            protocol_steps      — list[str] of the 5-step patch-mode protocol
            supports_rollback   — True (invariant: orig blobs always kept)
            requires_diff_plan  — True (invariant: diff_plan emitted before edits)
            plan_path           — str path of emitted diff_plan.yaml (if touches given)
            scope_guard_active  — bool (True if allowlist was provided and checked)
            module_path         — str canonical module for the patch planner

    Raises:
        ValueError: If touches is provided but localization_allowlist is given
                    and a touch path falls outside it.
        ValueError: If touches is provided but contains invalid hunk ops.
    """
    if not touches and touches is not None and len(touches) == 0:
        raise ValueError(
            "BF-7 boundary case: touches list is empty — nothing to patch"
        )

    ws = Path(workspace).resolve() if workspace is not None else Path.cwd().resolve()

    # Scope guard (pre-dispatch)
    scope_guard_active = localization_allowlist is not None
    if touches is not None and scope_guard_active:
        check_scope_guard(touches, localization_allowlist or [])

    # Emit diff plan if feature_id and touches are provided
    plan_path_str = ""
    if feature_id and touches is not None:
        plan_path = emit_diff_plan(feature_id, touches, workspace=ws)
        plan_path_str = str(plan_path)

    protocol_steps = [
        "Implementer emits .bob/features/<id>/diff_plan.yaml before any edits "
        "(emit_diff_plan); verifier and optionally human sanity-check scope.",
        "apply_diff_plan: backup originals to .bob/features/<id>/orig/<path>, "
        "then apply each hunk sequentially (replace / insert / delete).",
        "Rollback: rollback_changes restores pre-edit orig blobs so any AC failure "
        "triggers automatic revert without manual intervention.",
        "Coordinator scope guard: check_scope_guard refuses dispatch if any touch "
        "path falls outside the feature's localization allowlist.",
        "apply_diff_plan rejects the entire plan if any hunk fails to apply cleanly "
        "(FileNotFoundError for missing targets; invalid ops raise ValueError).",
    ]

    return {
        "protocol_steps": protocol_steps,
        "supports_rollback": True,
        "requires_diff_plan": True,
        "plan_path": plan_path_str,
        "scope_guard_active": scope_guard_active,
        "module_path": "bob.brownfield.patch_planner",
    }
