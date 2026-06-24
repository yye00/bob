"""bob75.orchestrator — gate-blocked feature re-synthesis functions.

Exposes the three canonical entry-points for mid-run AC re-synthesis:

  score_gate_loop        — re-exported from bob.spec_synthesizer; runs the
                           retry loop that regenerates ACs until composite >= threshold.
  synthesize_for_feature — re-exported from bob.spec_synthesizer; the async
                           synthesizer that calls out to the LLM sub-agent.
  mark_resynthesized     — in-process idempotency guard; records that a given
                           feature_id has already been re-synthesized so it is
                           NOT re-dispatched again (prevents the livelock).

Root cause closed by this module
---------------------------------
When a feature fails the spec_quality gate (composite < 0.85) it stays
'pending'. The old loop re-dispatched it to test-writer/CodeT which rebuild
code — but spec_quality is a function of the acceptance criteria, not the
code.  Rebuilding code can never raise the score.  The fix: when the
promotion sweep finds a gate-blocked feature, call score_gate_loop +
synthesize_for_feature to regenerate its ACs, then re-score.  Bounded to
ONE attempt per feature per process via mark_resynthesized so a feature
that still can't clear 0.85 is left blocked without infinite re-spinning.
"""

from __future__ import annotations

import logging

from bob.spec_synthesizer import (
    score_gate_loop,  # noqa: F401 — re-exported
    synthesize_for_feature,  # noqa: F401 — re-exported
)

logger = logging.getLogger(__name__)

# In-memory set: feature_ids that have already had one re-synthesis attempt
# this process.  Cleared only by resetting the process.
_resynthesized_ids: set[str] = set()


def mark_resynthesized(feature_id: str) -> None:
    """Record that feature_id has been re-synthesized once this process.

    After calling this, the orchestrator's promotion sweep must NOT attempt
    another re-synthesis for feature_id — if the ACs still fail the gate
    after one attempt, the feature is left blocked (needs_human), never
    re-looped.

    Args:
        feature_id: Non-empty string identifier for the feature.

    Raises:
        ValueError: If feature_id is not a non-empty string.
        TypeError: If feature_id is not a string at all.
    """
    if not isinstance(feature_id, str):
        raise TypeError(
            f"feature_id must be a str, got {type(feature_id).__name__!r}"
        )
    if not feature_id:
        raise ValueError("feature_id must be non-empty")
    _resynthesized_ids.add(feature_id)
    logger.debug("mark_resynthesized: recorded %s", feature_id[:8] if len(feature_id) >= 8 else feature_id)


def is_resynthesized(feature_id: str) -> bool:
    """Return True if feature_id has already been marked as re-synthesized.

    Args:
        feature_id: The feature identifier to check.

    Returns:
        True if mark_resynthesized has been called for this feature_id.
    """
    return feature_id in _resynthesized_ids


__all__ = [
    "score_gate_loop",
    "synthesize_for_feature",
    "mark_resynthesized",
    "is_resynthesized",
]
