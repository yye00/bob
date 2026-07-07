"""Sub-agent startup-crash exemption from the retry budget (F-R7-613).

Closes the 5-generation chronic needs_human loop on the F-R7-597 feature
class: an upstream MCP/TLS transport crash kills the sub-agent mid-task, but
F-R6-300's ``mid_work_crash`` classifier charges a retry anyway because it
sees work_events > 0. Five generations exhaust 5/5 retries on infra crashes
they did not cause and flip to needs_human, blocking chain drain.

This module is the AC-named entry point. The real implementation lives in
:mod:`bob.run_loop` (the orchestrator's mid_work_crash branch) and
:mod:`bob.startup_crash_exempt`; this module re-exports the classification and
sidecar-tracking primitives under the names the acceptance criteria require:

* :func:`classify_startup_crash_exemption` — decide exempt / charge / cap_reached
  from an exit signature + workspace + current exemption counter.
* :func:`track_exempt_count` — read (and optionally increment) the per-feature
  lifetime exemption sidecar count.

Design note (from the feature spec): do NOT add a persisted-artifact gate to
the exemption path. In this chain the bob ``src`` tree IS the build target and
concurrent sibling features modify it during the crashed feature's window, so
an mtime-based artifact count is always > 0 and would wrongly suppress every
exemption. The transport signature alone is sufficient evidence of an infra
crash the feature did not cause; the lifetime cap bounds abuse.
"""

from __future__ import annotations

import os
from typing import Any

from bob.run_loop import (
    classify_subagent_startup_crash,
    handle_subagent_startup_crash_exemption,
    increment_exemption_count,
    load_exemption_sidecar,
)

__all__ = [
    "classify_startup_crash_exemption",
    "track_exempt_count",
    "handle_subagent_startup_crash_exemption",
    "load_exemption_sidecar",
    "increment_exemption_count",
]


def classify_startup_crash_exemption(
    *,
    exit_signature: str | None,
    workspace: str | os.PathLike[str] | None = None,
    exempt_counter: int = 0,
) -> dict[str, Any]:
    """Classify whether a mid_work_crash qualifies for a retry-budget exemption.

    A crash is *exempt* when its exit signature matches a transport-transient
    infra failure pattern (MCP cert chain, connection reset, read timeout,
    broken pipe, ...) and the per-feature lifetime exemption cap has not been
    reached. An exempt crash must NOT charge the retry counter — the feature is
    reset to ``ready`` for a fresh attempt.

    Delegates to :func:`bob.run_loop.classify_subagent_startup_crash`.

    Parameters
    ----------
    exit_signature:
        The stderr tail / crash signature from the failed sub-agent spawn.
        ``None`` or empty string yields a ``"charge"`` decision (no transport
        match). Never raises on ``None``.
    workspace:
        Workspace root directory. May be ``None`` or point at a non-existent
        path — both are handled as artifact_count == 0.
    exempt_counter:
        Current lifetime exemption count for this feature (0-based).

    Returns
    -------
    dict
        Keys: ``decision`` (one of ``"exempt"``, ``"charge"``,
        ``"cap_reached"``), ``backoff_seconds``, ``artifact_count``,
        ``exempt_counter_after``, ``evidence``.
    """
    return classify_subagent_startup_crash(
        exit_signature=exit_signature,
        workspace=workspace,
        exempt_counter=exempt_counter,
    )


def track_exempt_count(
    feature_id: str,
    *,
    sidecar_dir: str | os.PathLike[str] | None = None,
    increment: bool = False,
) -> int:
    """Read (and optionally increment) the per-feature lifetime exemption count.

    Because no metadata column exists for the exemption counter, it is tracked
    in a per-feature plain-text sidecar (``<feature_id>.count``). This function
    is the AC-named accessor over that sidecar.

    Parameters
    ----------
    feature_id:
        UUID string of the feature. Must be a ``str`` — passing ``None`` or a
        non-string raises :class:`ValueError` (invalid input must not silently
        succeed).
    sidecar_dir:
        Directory holding per-feature sidecar files. Defaults to the
        ``BOB_STARTUP_EXEMPT_DIR`` env var, or ``<cwd>/.bob_startup_exempt/``.
    increment:
        When ``True``, atomically increment the count by 1 and return the new
        value. When ``False`` (default), read-only: return the current count
        (0 if no sidecar exists).

    Returns
    -------
    int
        The current count (``increment=False``) or the new count after
        incrementing (``increment=True``). Always >= 0.

    Raises
    ------
    ValueError
        When ``feature_id`` is ``None`` or not a ``str``.
    """
    if increment:
        return increment_exemption_count(feature_id, sidecar_dir=sidecar_dir)
    return load_exemption_sidecar(feature_id, sidecar_dir=sidecar_dir)
