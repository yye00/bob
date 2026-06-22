"""bob3.dispatcher — dispatch-layer integration for exponential backoff after reaper-reset.

Satisfies AC: Function defined: bob3.dispatcher.check_reap_backoff
Satisfies AC: Function defined: subagent_dispatch.apply_thinking_config
Satisfies AC: integration: bob3.dispatcher

This module is the canonical integration point between the bob3 dispatch loop
and the exponential backoff enforcement logic in bob3.reaper.  Before
dispatching a feature that has been reaped, the dispatch loop calls
check_reap_backoff to determine whether dispatch should be refused.

BF-8 integration: apply_thinking_config wires extended_thinking classification
into the subagent dispatch call, building the thinking kwarg dict that is passed
to the Claude API when spawning a feature sub-agent.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from bob3.reaper import should_refuse_redispatch, update_reap_tracking

if TYPE_CHECKING:
    from bob3.models import Feature

logger = logging.getLogger(__name__)


def check_reap_backoff(
    feature: "Feature",
    now: datetime | None = None,
) -> bool:
    """Check exponential backoff for a recently reaped feature before dispatch.

    Returns True if dispatch should be REFUSED (feature is within its backoff
    window or has been escalated to needs_human after >= 3 reaps). Returns
    False if dispatch may proceed.

    The dispatch loop should call this before dispatching any feature that has
    a non-zero reap_count, and skip dispatch if True is returned.

    Args:
        feature: The Feature model instance to check. Must not be None and must
            have an 'id' attribute.
        now: Reference time for the backoff check (defaults to UTC now).

    Returns:
        True if dispatch should be refused; False if dispatch may proceed.

    Raises:
        ValueError: If feature is None or lacks an 'id' attribute.
    """
    if feature is None:
        raise ValueError("feature must not be None")
    if not hasattr(feature, "id"):
        raise ValueError(
            f"feature must be a Feature-like object with an 'id' attribute, got {type(feature).__name__}"
        )
    refused = should_refuse_redispatch(feature, now=now)
    if refused:
        logger.debug(
            "DISPATCHER: refusing dispatch of feature %s — exponential backoff active",
            feature.id[:8] if isinstance(feature.id, str) and len(feature.id) >= 8 else feature.id,
        )
    return refused


def apply_thinking_config(
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: "bool | str | None" = None,
) -> dict[str, Any]:
    """Build the thinking kwarg dict for subagent dispatch (BF-8 Part B integration).

    Classifies the feature and returns a dict suitable for passing as
    ``thinking=`` to the Claude SDK when spawning a sub-agent.  Changing the
    thinking flag always requires a fresh subagent (invalidates messages cache).

    Args:
        feature_name:      Short name/title of the feature.
        description:       Full feature description.
        num_files:         Number of files expected to be modified.
        spec_quality:      Spec quality score in [0.0, 1.0].
        retry_count:       Number of prior implementation attempts.
        extended_thinking: Explicit override: True/False forces; "auto"/None runs
                           the classifier.

    Returns:
        A dict with ``type`` and ``budget_tokens`` keys when extended thinking is
        ON, or an empty dict when it is OFF.
    """
    from bob3.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
        classify_feature_thinking,
        thinking_kwargs,
    )

    enabled = classify_feature_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )
    if enabled:
        logger.debug("DISPATCHER: extended thinking ON for feature %r", feature_name)
    else:
        logger.debug("DISPATCHER: extended thinking OFF for feature %r", feature_name)
    return thinking_kwargs(enabled)


__all__ = [
    "check_reap_backoff",
    "update_reap_tracking",
    "apply_thinking_config",
]
