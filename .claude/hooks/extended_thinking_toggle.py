"""Extended-thinking toggle hook for Bob (BF-8 Part B).

Exposes resolve_thinking_mode as the primary API for the AC-required function.
Delegates to .claude/hooks/extended_thinking.py which contains the full
classify_and_apply implementation.

Per-feature override via YAML field:
  extended_thinking: true | false | "auto"

'auto' invokes the classifier:
  - OFF for {rename, doc, format, typo, single-file <30 LOC}
  - ON  for {refactor, migration, bugfix, integration,
             multi-file >=4, spec_quality<0.80, retry>=1}

Changing the thinking flag MUST go via a fresh subagent (invalidates the
messages cache; this fact is logged when resolve_thinking_mode is called).
"""

from __future__ import annotations

from typing import Any

from extended_thinking import (  # type: ignore[import]
    EXTENDED_THINKING_DEFAULT,
    classify_and_apply,
    get_default,
)

__all__ = [
    "resolve_thinking_mode",
    "classify_and_apply",
    "get_default",
    "EXTENDED_THINKING_DEFAULT",
]


def resolve_thinking_mode(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> dict[str, Any]:
    """Resolve the extended_thinking mode for a feature dispatch.

    This is the primary AC-required entry point for the extended_thinking toggle.
    Delegates to classify_and_apply from extended_thinking.py.

    Args:
        feature_name:      Short name/title of the feature.
        description:       Full feature description.
        num_files:         Number of files the feature is expected to touch.
        spec_quality:      Spec quality score in [0.0, 1.0].
        retry_count:       Number of prior implementation attempts.
        extended_thinking: Explicit override: True/False forces the value;
                           "auto" (or None) runs the classifier.

    Returns:
        A dict with keys:
          enabled               – bool, whether extended thinking is ON
          thinking              – dict suitable for thinking= param (or {})
          changed               – bool, whether this differs from the default
          reason                – str, human-readable rationale
          fresh_subagent_required – bool, True when switching flag mid-feature
    """
    return classify_and_apply(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )
