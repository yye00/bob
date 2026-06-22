"""Feature reset utilities for RCA-driven auto-recovery.

F-R7-479: when the RCA sub-agent determines all failures were infra-caused,
``reset_to_ready`` transitions the feature back to ``ready`` state so that the
orchestrator can dispatch it again without human intervention.

Public API:
- ``reset_to_ready``: reset a feature to ready with refinement_attempts=0
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = ["reset_to_ready"]


def reset_to_ready(
    feature_id: str,
    db_update_fn: Callable[..., None],
    refinement_attempts: int = 0,
) -> None:
    """Reset a feature to ``ready`` state for another dispatch attempt.

    Called after an ``infra_only`` RCA verdict to clear the infra failure and
    allow the orchestrator to retry the feature. The ``refinement_attempts``
    counter is reset to 0 because the failures were infrastructure-caused, not
    indicative of a code or spec problem.

    Parameters
    ----------
    feature_id:
        UUID of the feature to reset.
    db_update_fn:
        Callable ``(feature_id, **kwargs)`` that updates the feature record.
        Matches the signature of ``bob3.db.update_feature``.
    refinement_attempts:
        Value to set for ``refinement_attempts``. Defaults to 0 (fresh budget).
        Pass a positive integer only when intentionally preserving a partial
        attempt budget (e.g. for code-emission-defect recovery).

    Raises
    ------
    ValueError
        If ``feature_id`` is empty or None, or if ``refinement_attempts < 0``.
    TypeError
        If ``feature_id`` is not a string, ``db_update_fn`` is not callable,
        or ``refinement_attempts`` is not an int.
    """
    if feature_id is None:
        raise ValueError("feature_id must not be None")
    if not isinstance(feature_id, str):
        raise TypeError(f"feature_id must be a str, got {type(feature_id).__name__}")
    if not feature_id.strip():
        raise ValueError("feature_id must not be empty")
    if not callable(db_update_fn):
        raise TypeError(f"db_update_fn must be callable, got {type(db_update_fn).__name__}")
    if not isinstance(refinement_attempts, int):
        raise TypeError(
            f"refinement_attempts must be an int, got {type(refinement_attempts).__name__}"
        )
    if refinement_attempts < 0:
        raise ValueError(f"refinement_attempts must be >= 0, got {refinement_attempts}")

    db_update_fn(feature_id, status="ready", refinement_attempts=refinement_attempts)

    logger.info(
        "feature_reset.reset_to_ready: feature %s reset to ready "
        "(refinement_attempts=%d)",
        feature_id[:8],
        refinement_attempts,
    )
