"""Public subagent reaper for bob3 — feature terminal-state process cleanup.

Re-exports the canonical implementation from bob3.orchestrator.subagent_reaper
so that code can import from the top-level ``bob3`` namespace without depending
on the internal orchestrator package layout.

Public functions
----------------
find_subagent_pid_for_feature(feature_id)
    Return PIDs of live claude subagents tagged with the given feature id.

reap_subagent_for_feature(feature_id)
    Send SIGTERM then SIGKILL (15s grace) to each matching PID.
    Emits audit sentinel ``subagent_reaped_on_terminal=<feature_id>``.

reap_subagent_on_terminal_state(feature_id)
    Reap claude subagent on feature terminal-state transition.
    Validates input (raises ValueError for non-str), returns [] for empty
    feature_id, otherwise delegates to reap_subagent_for_feature.

sweep_orphan_subagents()
    Backstop sweep: reap subagents for features in terminal states > 5 min.
    Returns list of (feature_id, pid) pairs reaped.

reap_orphan_subagents_backstop()
    Alias for sweep_orphan_subagents — AC-required name for the backstop sweep.
"""

from __future__ import annotations

import bob3.orchestrator.subagent_reaper as _orch_reaper

from bob3.orchestrator.subagent_reaper import (
    find_subagent_pid_for_feature,
    reap_subagent_for_feature,
)


def sweep_orphan_subagents() -> list[tuple[str, int]]:
    """Backstop sweep: reap subagents for features in terminal states > 5min.

    Delegates to ``bob3.orchestrator.subagent_reaper.sweep_orphan_subagents``
    via a dynamic module lookup so that tests can patch the underlying
    implementation without holding a stale direct reference.

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.
    """
    return _orch_reaper.sweep_orphan_subagents()


def reap_subagent_on_terminal_state(feature_id: str) -> list[int]:
    """Reap claude subagent process on feature terminal-state transition.

    Named entry point for the run_loop completion handler. Applies to all
    terminal transitions: completed, needs_human, regression, failed.

    Boundary behaviour
    ------------------
    - Empty string feature_id: returns [] (no process can match an empty id).
    - None or non-string feature_id: raises ValueError.

    Parameters
    ----------
    feature_id:
        UUID string of the feature that has entered a terminal state.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty list when no matching subagent was found.

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"reap_subagent_on_terminal_state: feature_id must be a str, "
            f"got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        return []
    return reap_subagent_for_feature(feature_id)


def reap_orphan_subagents_backstop() -> list[tuple[str, int]]:
    """Backstop sweep alias — AC-required entry point for orphan subagent reaping.

    Delegates to sweep_orphan_subagents. Catches handler-bypass paths (e.g.
    SIGKILL'd orchestrator restart mid-completion) where the completion handler
    never ran.

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.
    """
    return sweep_orphan_subagents()


def reap_orphan_subagents() -> list[tuple[str, int]]:
    """Backstop sweep — AC-required name for the orphan subagent reaper.

    Alias for sweep_orphan_subagents / reap_orphan_subagents_backstop.
    Reaps subagents whose tagged feature is in a terminal state for >5 minutes.

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.
    """
    return sweep_orphan_subagents()


def reap_on_terminal_transition(feature_id: str) -> list[int]:
    """Reap claude subagent on feature terminal-state transition.

    AC-required entry point (Function defined: bob3.subagent_reaper.reap_on_terminal_transition).
    Delegates to reap_subagent_on_terminal_state.

    Parameters
    ----------
    feature_id:
        UUID string of the feature that has entered a terminal state.

    Returns
    -------
    list[int]
        PIDs confirmed dead.  Empty list when no matching subagent was found.

    Raises
    ------
    ValueError
        When feature_id is None or not a string.
    """
    return reap_subagent_on_terminal_state(feature_id)


def reap_stale_orphans() -> list[tuple[str, int]]:
    """Backstop sweep — AC-required entry point for stale orphan subagent reaping.

    AC-required entry point (Function defined: bob3.subagent_reaper.reap_stale_orphans).
    Reaps subagents whose tagged feature is in a terminal state for >5 minutes.
    Delegates to sweep_orphan_subagents.

    Returns
    -------
    list[tuple[str, int]]
        List of (feature_id, pid) pairs that were reaped.
    """
    return sweep_orphan_subagents()


__all__ = [
    "find_subagent_pid_for_feature",
    "reap_on_terminal_transition",
    "reap_orphan_subagents",
    "reap_orphan_subagents_backstop",
    "reap_stale_orphans",
    "reap_subagent_for_feature",
    "reap_subagent_on_terminal_state",
    "sweep_orphan_subagents",
]
