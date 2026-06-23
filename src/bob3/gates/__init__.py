"""bob3.gates — Gate functions for feature lifecycle enforcement.

Public API:
    :func:`is_completion_persisted`   — check if a feature has a persisted completion stamp
    :func:`prevent_status_downgrade`  — block demotion of previously-completed features
"""

from bob3.sticky_completed_gate import is_completion_persisted, prevent_status_downgrade

__all__ = ["is_completion_persisted", "prevent_status_downgrade"]
