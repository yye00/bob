"""BF-8 Part B — extended_thinking toggle module.

Provides:
  - classifier(): determine whether extended thinking should be enabled
  - EXTENDED_THINKING_DEFAULT: bootstrap-level default (True)
  - thinking_kwargs(): build Claude SDK thinking parameter dict
  - get_setting(): read bootstrap default from .claude/settings.json

This module is a thin adapter over the main BF-8 implementation, providing
the 'extended_thinking.classifier' AC-required function name.
"""

from __future__ import annotations

from bob3.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    EXTENDED_THINKING_DEFAULT,
    classify_feature_thinking,
    get_extended_thinking_setting,
    thinking_kwargs,
)


def classifier(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> bool:
    """Classify whether extended thinking should be enabled for a feature.

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


def get_setting() -> bool:
    """Return the bootstrap-level extended_thinking_default setting."""
    return get_extended_thinking_setting()


def classify_task(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> bool:
    """Alias for classifier() — satisfies AC: Function defined: extended_thinking.classify_task."""
    return classify_feature_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )


def classify_thinking_requirement(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> bool:
    """Determine whether extended thinking is required for a feature.

    This is the canonical public function for AC: Function defined:
    bob3.extended_thinking.classify_thinking_requirement.

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


def classify_thinking_need(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> bool:
    """Alias for classify_thinking_requirement — AC: extended_thinking.classify_thinking_need."""
    return classify_feature_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )


def classify_feature(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> bool:
    """Alias for classify_thinking_requirement — AC: extended_thinking.classify_feature."""
    return classify_feature_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )


__all__ = [
    "EXTENDED_THINKING_DEFAULT",
    "classifier",
    "classify_feature",
    "classify_feature_thinking",
    "classify_task",
    "classify_thinking_need",
    "classify_thinking_requirement",
    "get_extended_thinking_setting",
    "get_setting",
    "thinking_kwargs",
]
