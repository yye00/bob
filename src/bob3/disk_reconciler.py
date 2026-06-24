"""Public facade for disk-state reconciliation (F-R7-598).

Re-exports the orchestrator's disk_reconciler functions and adds
``promote_if_acs_satisfied`` — the AC-required entry point for checking
whether an executing feature's ACs are already satisfied on disk and
promoting it to 'completed' rather than flipping it to 'failed'.
"""

from __future__ import annotations

from bob3.orchestrator.disk_reconciler import (
    evaluate_ac_against_disk,
    reconcile_from_disk,
    handle_missing_workspace,
    never_raises_on_missing_workspace,
    promote_to_completed,
    handle_failing_integration_ac,
    check_executing_feature_acs,
    NOT_RECONCILED,
)


def promote_if_acs_satisfied(
    project_id: str,
    feature_id: str,
    feature_name: str,
    acceptance_criteria_json: str,
) -> bool:
    """Check whether an 'executing' feature satisfies all its ACs on disk.

    Called by _final_exit_sweep (F-R7-598) before flipping an orphan-executing
    feature to 'failed'. If all ACs pass, atomically promotes the feature to
    'completed' via promote_to_completed and returns True. Returns False if any
    AC fails or if the AC list cannot be parsed.

    Parameters
    ----------
    project_id:
        The project UUID.
    feature_id:
        UUID of the feature to check and possibly promote.
    feature_name:
        Human-readable feature name for log messages.
    acceptance_criteria_json:
        JSON-encoded list of AC strings (from feature.acceptance_criteria).

    Returns
    -------
    bool
        True if all ACs passed and the feature was promoted to 'completed'.
        False if any AC failed or the AC JSON could not be parsed.
    """
    return check_executing_feature_acs(
        project_id=project_id,
        feature_id=feature_id,
        feature_name=feature_name,
        acceptance_criteria_json=acceptance_criteria_json,
    )


__all__ = [
    "evaluate_ac_against_disk",
    "reconcile_from_disk",
    "handle_missing_workspace",
    "never_raises_on_missing_workspace",
    "promote_to_completed",
    "handle_failing_integration_ac",
    "check_executing_feature_acs",
    "promote_if_acs_satisfied",
    "NOT_RECONCILED",
]
