"""Extended-thinking classifier hook for Bob (BF-8 Part B).

Standalone hook script that classifies features to decide whether extended
thinking should be ON or OFF.  Called by the Claude Code hook system; also
importable directly as a module.

Extended thinking is ON by default (bootstrap-level default).  Per-feature
override is supported via a YAML field:
  extended_thinking: true | false | "auto"

'auto' invokes the classifier:
  - OFF for {rename, doc, format, typo, single-file <30 LOC}
  - ON  for {refactor, migration, bugfix, integration,
             multi-file >=4, spec_quality<0.80, retry>=1}

Changing the thinking flag MUST go via a fresh subagent (invalidates the
messages cache; this fact is logged when classify_and_apply is called).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXTENDED_THINKING_DEFAULT: bool = True

_AUTO_OFF_KEYWORDS = frozenset({"rename", "doc", "format", "typo"})
_AUTO_ON_KEYWORDS = frozenset({"refactor", "migration", "bugfix", "integration"})


# ---------------------------------------------------------------------------
# Public API — satisfies AC: "Function defined: extended_thinking_classifier.should_enable_thinking"
# ---------------------------------------------------------------------------


def should_enable_thinking(
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
                           'auto' (or None) runs the classifier.

    Returns:
        True if extended thinking should be enabled, False otherwise.
    """
    if extended_thinking is True:
        return True
    if extended_thinking is False:
        return False

    if isinstance(extended_thinking, str) and extended_thinking != "auto":
        raise ValueError(
            f"extended_thinking must be True, False, 'auto', or None; got {extended_thinking!r}"
        )

    combined = f"{feature_name} {description}".lower()

    # Single-file + trivial keyword → OFF
    if num_files < 2:
        for kw in _AUTO_OFF_KEYWORDS:
            if kw in combined:
                return False

    # Complex triggers → ON
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


# Alias for convenience
classify_extended_thinking = should_enable_thinking


def thinking_kwargs(enabled: bool) -> dict[str, Any]:
    """Return the thinking kwarg dict for ClaudeCodeOptions / query()."""
    if enabled:
        return {"type": "enabled", "budget_tokens": 10_000}
    return {}


def classify_and_apply(
    *,
    feature_name: str = "",
    description: str = "",
    num_files: int = 0,
    spec_quality: float = 1.0,
    retry_count: int = 0,
    extended_thinking: bool | str | None = None,
) -> dict[str, Any]:
    """Classify a feature and return the thinking configuration to apply.

    Returns:
        A dict with keys: enabled, thinking, changed, reason, fresh_subagent_required
    """
    enabled = should_enable_thinking(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )

    thinking = thinking_kwargs(enabled)
    changed = enabled != EXTENDED_THINKING_DEFAULT
    reason = _build_reason(
        enabled=enabled,
        feature_name=feature_name,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )

    if changed:
        logger.info(
            "extended_thinking changed from default=%s to %s — fresh subagent required. feature=%r",
            EXTENDED_THINKING_DEFAULT,
            enabled,
            feature_name,
        )

    return {
        "enabled": enabled,
        "thinking": thinking,
        "changed": changed,
        "reason": reason,
        "fresh_subagent_required": changed,
    }


def _build_reason(
    *,
    enabled: bool,
    feature_name: str,
    num_files: int,
    spec_quality: float,
    retry_count: int,
    extended_thinking: bool | str | None,
) -> str:
    if extended_thinking is True:
        return "explicit override: extended_thinking=True"
    if extended_thinking is False:
        return "explicit override: extended_thinking=False"
    combined = feature_name.lower()
    if num_files >= 4:
        return f"multi-file feature ({num_files} files >= 4)"
    if spec_quality < 0.80:
        return f"low spec quality ({spec_quality:.2f} < 0.80)"
    if retry_count >= 1:
        return f"retry attempt #{retry_count}"
    for kw in _AUTO_ON_KEYWORDS:
        if kw in combined:
            return f"ON keyword match: '{kw}'"
    if num_files < 2:
        for kw in _AUTO_OFF_KEYWORDS:
            if kw in combined:
                return f"OFF keyword match: '{kw}' (single-file trivial task)"
    return f"default extended_thinking={EXTENDED_THINKING_DEFAULT}"


def main() -> None:
    """Hook entry point — reads JSON from stdin, writes classification to stdout."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print(json.dumps({"decision": "continue"}))
            return
        payload = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        print(json.dumps({"decision": "continue"}))
        return

    feature_name = payload.get("feature_name", "")
    description = payload.get("description", "")
    num_files = payload.get("num_files", 0)
    spec_quality = payload.get("spec_quality", 1.0)
    retry_count = payload.get("retry_count", 0)
    extended_thinking = payload.get("extended_thinking")

    try:
        result = classify_and_apply(
            feature_name=feature_name,
            description=description,
            num_files=num_files,
            spec_quality=spec_quality,
            retry_count=retry_count,
            extended_thinking=extended_thinking,
        )
    except ValueError as exc:
        print(json.dumps({"decision": "continue", "error": str(exc)}))
        return

    print(json.dumps(result))


if __name__ == "__main__":
    main()
