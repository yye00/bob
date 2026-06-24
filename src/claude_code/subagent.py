"""Claude Code subagent dispatch utilities for BF-8.

Provides dispatch_with_thinking, which wires the extended_thinking toggle
into subagent dispatch.  Callers pass feature metadata; this module
classifies whether extended thinking should be enabled and returns the
appropriate kwargs for the Claude SDK query() call.

Satisfies ACs:
  - Function defined: claude_code.subagent.dispatch_with_thinking
"""

from __future__ import annotations

import logging
from typing import Any

from bob.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    classify_feature_thinking,
    thinking_kwargs,
)

logger = logging.getLogger(__name__)


def dispatch_with_thinking(
    prompt: str,
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
    extra_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build kwargs for a subagent dispatch, incorporating the extended_thinking toggle.

    Classifies the feature and returns a dict of Claude SDK kwargs suitable
    for passing to query() or a subagent runner.  When extended thinking is
    enabled, includes ``thinking={"type": "enabled", "budget_tokens": 10_000}``.

    Important: Changing the thinking flag MUST go via a fresh subagent because
    it invalidates the messages cache.  This function always returns a fresh
    kwargs dict; callers must spawn a new subagent when toggling.

    Args:
        prompt:            The prompt string for the subagent.
        feature_name:      Short feature name for the classifier.
        description:       Full feature description for the classifier.
        num_files:         Number of files the feature touches.
        spec_quality:      Spec quality score in [0.0, 1.0].
        retry_count:       Number of prior implementation attempts.
        extended_thinking: Explicit override: True/False forces the value;
                           "auto" or None runs the auto-classifier.
        extra_kwargs:      Additional kwargs to merge into the result.

    Returns:
        A dict of kwargs for the subagent dispatch, including:
          - ``prompt``: the prompt string
          - ``thinking``: thinking config dict (only when enabled)
    """
    enabled = classify_feature_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )

    kwargs: dict[str, Any] = {"prompt": prompt}

    think_kwargs = thinking_kwargs(enabled)
    if think_kwargs:
        kwargs["thinking"] = think_kwargs
        logger.debug(
            "dispatch_with_thinking: extended_thinking=ON for feature=%r", feature_name
        )
    else:
        logger.debug(
            "dispatch_with_thinking: extended_thinking=OFF for feature=%r", feature_name
        )

    if extra_kwargs:
        kwargs.update(extra_kwargs)

    return kwargs
