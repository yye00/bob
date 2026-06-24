"""Sub-agent startup-crash exemption module (F-R7-613).

Provides the canonical entry points for deciding whether a mid_work_crash
should be exempt from the retry budget because the sub-agent crash was caused
by an infra-level transport failure rather than a genuine work-loss event.

This module wraps the lower-level startup_crash_exempt functions and exposes
the two canonical AC-required functions:

* ``is_transport_transient``: fast predicate — returns True when the
  exit_signature matches a known transport-transient pattern.
* ``apply_startup_crash_exemption``: policy function — given a feature and
  its exit_signature, decides whether to exempt it from the retry budget,
  emits the appropriate telemetry event, and returns the decision dict.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from bob.startup_crash_exempt import (
    _TRANSPORT_TRANSIENT_PATTERNS,  # type: ignore[reportPrivateUsage]
    exit_signature_matches_transport_transient,
    classify_startup_crash,
    check_startup_crash_exemption,
)
from bob.run_loop import load_exemption_sidecar, increment_exemption_count  # type: ignore[import]

logger = logging.getLogger(__name__)

# Default sidecar directory (mirrors the orchestrator default).
_DEFAULT_SIDECAR_DIR: str = os.environ.get(
    "BOB_STARTUP_EXEMPT_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", ".bob_startup_exempt"),
)


def is_transport_transient(exit_signature: str | None) -> bool:
    """Return True when exit_signature matches a known transport-transient pattern.

    This is the canonical predicate for the startup-crash exemption check.
    It delegates to ``startup_crash_exempt.exit_signature_matches_transport_transient``.

    Parameters
    ----------
    exit_signature:
        The error message / stderr tail from the crashed sub-agent.  ``None``
        and empty string both return ``False`` (no match is possible).

    Returns
    -------
    bool
        ``True`` if the signature matches a transport-transient pattern,
        ``False`` otherwise.  Never raises.
    """
    return exit_signature_matches_transport_transient(exit_signature)


def apply_startup_crash_exemption(
    feature_id: str,
    exit_signature: str | None,
    *,
    workspace: str | None = None,
    sidecar_dir: str | None = None,
) -> dict[str, Any]:
    """Decide whether a mid_work_crash is exempt from the retry budget.

    This is the canonical orchestrator integration entry point for F-R7-613.
    It is called inside the mid_work_crash branch BEFORE incrementing the
    retry counter.

    Algorithm
    ---------
    1. Load the per-feature exemption count from the sidecar file.
    2. Call ``classify_startup_crash`` to decide: "exempt", "charge", or
       "cap_reached".
    3. If "exempt": persist the incremented counter and emit
       ``SUBAGENT_STARTUP_CRASH_EXEMPT`` telemetry.
    4. If "cap_reached": emit ``SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED``.
    5. Return a result dict the caller can act on.

    Parameters
    ----------
    feature_id:
        The UUID of the feature whose mid_work_crash is being classified.
    exit_signature:
        The exit message / error string from the crashed sub-agent.  Passed
        to the transport-transient classifier.
    workspace:
        Path to the workspace directory.  Used to count persisted artifacts
        (not used for the exemption decision itself in F-R7-613, kept for
        API consistency with the lower-level functions).
    sidecar_dir:
        Directory where per-feature exemption count files are stored.  If
        ``None``, defaults to ``BOB_STARTUP_EXEMPT_DIR`` env var or the
        built-in default next to the bob package root.

    Returns
    -------
    dict with keys:
        action          — "exempt" | "charge" | "cap_reached"
        decision        — same as action (alias for callers that use decision)
        backoff_seconds — seconds to wait before the next attempt (0 on charge)
        artifact_count  — number of .py artifacts found in workspace
        exempt_counter_after — new exemption count after this call
        error_pattern   — the matched pattern string, or None
        exit_signature_excerpt — first 200 chars of exit_signature
        evidence        — dict with classification evidence
        event           — telemetry event name emitted
    """
    if sidecar_dir is None:
        sidecar_dir = os.environ.get("BOB_STARTUP_EXEMPT_DIR", _DEFAULT_SIDECAR_DIR)

    # Load persisted exemption count.
    try:
        exempt_counter = load_exemption_sidecar(feature_id, sidecar_dir=sidecar_dir)
    except Exception:
        exempt_counter = 0

    ws = workspace or ""

    # Classify the crash.
    classification = classify_startup_crash(
        exit_signature=exit_signature,
        workspace=ws,
        exempt_counter=exempt_counter,
    )

    decision = classification["decision"]

    # Map cap_reached → cap_reached (it's the same string, but make intent clear).
    action = decision  # "exempt" | "charge" | "cap_reached"

    # Determine matched pattern string.
    error_pattern: str | None = None
    if decision in ("exempt", "cap_reached") and exit_signature:
        for pat in _TRANSPORT_TRANSIENT_PATTERNS:
            if pat.search(exit_signature):
                error_pattern = pat.pattern
                break

    # Persist updated counter on exempt.
    if decision == "exempt":
        try:
            increment_exemption_count(feature_id, sidecar_dir=sidecar_dir)
        except Exception as exc:
            logger.warning("apply_startup_crash_exemption: could not save sidecar: %s", exc)

    # Emit telemetry.
    if decision == "exempt":
        event = "SUBAGENT_STARTUP_CRASH_EXEMPT"
        logger.info(
            "%s feature_id=%s error_pattern=%s exempt_count=%s excerpt=%.200s",
            event,
            feature_id,
            error_pattern,
            classification["exempt_counter_after"],
            exit_signature or "",
        )
    elif decision == "cap_reached":
        event = "SUBAGENT_STARTUP_CRASH_EXEMPT_CAPPED"
        logger.warning(
            "%s feature_id=%s exempt_counter=%s — falling through to charge",
            event,
            feature_id,
            exempt_counter,
        )
    else:
        event = "SUBAGENT_STARTUP_CRASH_CHARGE"
        logger.debug(
            "%s feature_id=%s exit_signature=%.200s",
            event,
            feature_id,
            exit_signature or "",
        )

    return {
        "action": action,
        "decision": action,
        "backoff_seconds": classification.get("backoff_seconds", 0),
        "artifact_count": classification.get("artifact_count", 0),
        "exempt_counter_after": classification["exempt_counter_after"],
        "error_pattern": error_pattern,
        "exit_signature_excerpt": (exit_signature or "")[:200],
        "evidence": classification.get("evidence", {}),
        "event": event,
    }
