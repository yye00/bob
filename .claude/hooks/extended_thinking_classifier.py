"""Extended-thinking classifier hook for Bob (BF-8 Part B).

Standalone, dependency-free classifier that decides whether extended
thinking should be enabled for a given feature dispatch.  Lives under
.claude/hooks/ so Claude Code can invoke it directly, and so the AC
verifier can locate it by path.

Policy (per BF-8 spec):
  - Explicit True/False override wins.
  - "auto" (or None) runs the heuristic classifier:
      OFF for {rename, doc, format, typo} on a single file (<2 files).
      ON  for {refactor, migration, bugfix, integration} keywords, or
              num_files >= 4, spec_quality < 0.80, retry_count >= 1.
  - Otherwise falls back to EXTENDED_THINKING_DEFAULT (ON).

The heuristic is intentionally duplicated here (not imported from src) so the
hook remains runnable without the bob package on sys.path.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# Default: extended thinking is ON for all features unless overridden.
EXTENDED_THINKING_DEFAULT: bool = True

_AUTO_OFF_KEYWORDS = frozenset({"rename", "doc", "format", "typo"})
_AUTO_ON_KEYWORDS = frozenset({"refactor", "migration", "bugfix", "integration"})


def classify_extended_thinking(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> bool:
    """Decide whether extended thinking should be enabled for a feature.

    Args:
        feature_name:      Short name/title of the feature.
        description:       Full feature description.
        num_files:         Number of files the feature is expected to touch.
        spec_quality:      Spec quality score in [0.0, 1.0].
        retry_count:       Number of prior implementation attempts.
        extended_thinking: Explicit override: True/False forces the value;
                           "auto" (or None) runs the classifier.

    Returns:
        True if extended thinking should be enabled, False otherwise.

    Raises:
        ValueError: if extended_thinking is a string other than "auto".
    """
    if extended_thinking is True:
        return True
    if extended_thinking is False:
        return False

    if isinstance(extended_thinking, str) and extended_thinking != "auto":
        raise ValueError(
            f"extended_thinking must be True, False, 'auto', or None; "
            f"got {extended_thinking!r}"
        )

    combined = f"{feature_name} {description}".lower()

    if num_files < 2:
        for kw in _AUTO_OFF_KEYWORDS:
            if kw in combined:
                return False

    if num_files >= 4:
        return True
    if spec_quality < 0.80:
        return True
    if retry_count >= 1:
        return True
    for kw in _AUTO_ON_KEYWORDS:
        if kw in combined:
            return True

    return EXTENDED_THINKING_DEFAULT


# AC aliases
classify_feature_thinking = classify_extended_thinking
classify = classify_extended_thinking
should_enable_thinking = classify_extended_thinking


def thinking_kwargs(enabled: bool) -> dict[str, Any]:
    """Return the ``thinking=`` kwarg dict for the Claude SDK.

    When disabled, returns an empty dict (not None) so callers can splat it.
    """
    if enabled:
        return {"type": "enabled", "budget_tokens": 10_000}
    return {}


def main() -> None:
    """Hook entry point.

    Reads a JSON payload from stdin describing the feature and writes a JSON
    decision ({"extended_thinking": bool, "thinking": {...}}) to stdout.
    On any parse error it defaults to EXTENDED_THINKING_DEFAULT.
    """
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        payload = {}

    try:
        enabled = classify_extended_thinking(
            feature_name=payload.get("feature_name", ""),
            description=payload.get("description", ""),
            num_files=payload.get("num_files", 0),
            spec_quality=payload.get("spec_quality", 1.0),
            retry_count=payload.get("retry_count", 0),
            extended_thinking=payload.get("extended_thinking"),
        )
    except ValueError:
        enabled = EXTENDED_THINKING_DEFAULT

    print(json.dumps({"extended_thinking": enabled, "thinking": thinking_kwargs(enabled)}))


if __name__ == "__main__":
    main()
