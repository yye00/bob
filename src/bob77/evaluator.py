"""bob77.evaluator — Evaluator integration with the sticky-completed gate.

Integrates :func:`~bob77.sticky_gate.evaluate_with_sticky_completion` into
the evaluation flow so that no evaluator FAIL or regression-cascade vote may
demote a previously-completed feature whose acceptance criteria still verify
on disk.

Public API
----------
check_sticky_gate(parent_completed, target_status, acceptance_criteria, workspace)
    Apply the sticky-completed gate and return whether the demotion is blocked.
"""

from __future__ import annotations

import pathlib

from bob77.sticky_gate import evaluate_with_sticky_completion


def check_sticky_gate(
    parent_completed: bool,
    target_status: str,
    acceptance_criteria: str | list[str] | None,
    workspace: pathlib.Path | str | None = None,
) -> bool:
    """Apply the sticky-completed gate within the evaluator flow.

    Delegates to :func:`~bob77.sticky_gate.evaluate_with_sticky_completion`.
    Returns True when the demotion should be blocked, False when it may proceed.

    Args:
        parent_completed: True when the feature was completed in the parent DB.
        target_status: The status the evaluator wishes to assign.
        acceptance_criteria: Raw JSON string or list of AC strings.
        workspace: Root workspace for disk-based AC verification.

    Returns:
        True if demotion is blocked; False if it may proceed.
    """
    return evaluate_with_sticky_completion(
        parent_completed=parent_completed,
        target_status=target_status,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


__all__ = ["check_sticky_gate"]
