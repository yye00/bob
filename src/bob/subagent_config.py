"""bob.subagent_config — subagent configuration utilities (BF-8 Part B integration).

Provides apply_extended_thinking, which wires the extended_thinking toggle
into subagent dispatch configuration.  Called by both bob.dispatcher and
bob.concurrent_dispatcher before spawning a Claude sub-agent.

Satisfies ACs:
  - Function defined: bob.subagent_config.apply_extended_thinking
  - integration: bob.dispatcher
  - integration: bob.concurrent_dispatcher
"""

from __future__ import annotations

from typing import Any

from bob.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    classify_feature_thinking,
    thinking_kwargs,
)


def apply_extended_thinking(
    config: "dict[str, Any]",
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: "bool | str | None" = None,
) -> "dict[str, Any]":
    """Inject the extended_thinking kwarg into a subagent dispatch config dict.

    Classifies the feature and mutates (or creates) the ``thinking`` key in
    *config*.  If extended thinking is enabled, sets::

        config["thinking"] = {"type": "enabled", "budget_tokens": 10_000}

    If disabled, removes the ``thinking`` key so the API uses its default
    (no extended thinking).

    Note: Changing the thinking flag MUST go via a fresh subagent because it
    invalidates the messages cache.  Callers are responsible for spawning a
    new subagent when toggling this setting mid-feature.

    Args:
        config:            Mutable dispatch config dict to update in-place.
        feature_name:      Short feature name for the classifier.
        description:       Full feature description for the classifier.
        num_files:         Number of files the feature touches.
        spec_quality:      Spec quality score in [0.0, 1.0].
        retry_count:       Number of prior implementation attempts.
        extended_thinking: Explicit override; ``None`` or ``"auto"`` runs
                           the classifier.

    Returns:
        The mutated *config* dict (same object, returned for convenience).
    """
    enabled = classify_feature_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )
    kwargs = thinking_kwargs(enabled)
    if kwargs:
        config["thinking"] = kwargs
    else:
        config.pop("thinking", None)
    return config
