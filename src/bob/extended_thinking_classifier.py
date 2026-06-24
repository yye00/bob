"""BF-8 Part B — extended_thinking_classifier module.

Provides the canonical classify_extended_thinking function used by the
bob.agents integration layer to decide whether extended thinking should
be enabled for a given feature dispatch.

This module is a thin adapter over the main BF-8 implementation in
bf_8_context_budget_pretooluse_hook_extended_thinking_toggle.  It exposes
the AC-required function name (classify_extended_thinking) while delegating
to the shared classify_feature_thinking implementation.
"""

from __future__ import annotations

from bob.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    EXTENDED_THINKING_DEFAULT,
    classify_feature_thinking,
    get_extended_thinking_setting,
    thinking_kwargs,
)


def classify_extended_thinking(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> bool:
    """Classify whether extended thinking should be enabled for a feature.

    This is the primary entry point for the bob.agents integration layer.

    Args:
        feature_name:      Short name/title of the feature.
        description:       Full feature description.
        num_files:         Number of files the feature is expected to touch.
        spec_quality:      Spec quality score in [0.0, 1.0].
        retry_count:       Number of prior implementation attempts.
        extended_thinking: Explicit override: True/False forces the value;
                           'auto' (or None) runs the auto-classifier.

    Returns:
        True if extended thinking should be enabled, False otherwise.
    """
    return classify_feature_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )


# AC alias: "Function defined: extended_thinking_classifier.should_enable_thinking"
should_enable_thinking = classify_extended_thinking

# AC alias: "Function defined: bob.extended_thinking_classifier.classify_thinking_mode"
classify_thinking_mode = classify_extended_thinking


__all__ = [
    "EXTENDED_THINKING_DEFAULT",
    "classify_extended_thinking",
    "classify_feature_thinking",
    "classify_thinking_mode",
    "get_extended_thinking_setting",
    "should_enable_thinking",
    "thinking_kwargs",
]
