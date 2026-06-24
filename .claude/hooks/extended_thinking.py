"""Extended-thinking toggle hook for Bob (BF-8 Part B).

Classifies features to decide whether extended thinking should be ON or OFF,
and exposes classify_and_apply as the primary API for the hook.

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
# Public API
# ---------------------------------------------------------------------------


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
          enabled       – bool, whether extended thinking is ON
          thinking      – dict suitable for thinking= param (or empty dict)
          changed       – bool, whether this differs from the default
          reason        – str, human-readable rationale
          fresh_subagent_required – bool, True when switching flag mid-feature
    """
    enabled = _classify(
        feature_name=feature_name,
        description=description,
        num_files=num_files,
        spec_quality=spec_quality,
        retry_count=retry_count,
        extended_thinking=extended_thinking,
    )

    thinking = _thinking_kwargs(enabled)
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
            "extended_thinking changed from default=%s to %s — fresh subagent required; "
            "messages cache invalidated. feature=%r reason=%s",
            EXTENDED_THINKING_DEFAULT,
            enabled,
            feature_name,
            reason,
        )

    return {
        "enabled": enabled,
        "thinking": thinking,
        "changed": changed,
        "reason": reason,
        "fresh_subagent_required": changed,
    }


classify = classify_and_apply  # AC alias: "Function defined: extended_thinking.classify"


def get_default() -> bool:
    """Return the bootstrap-level extended_thinking_default.

    Reads .claude/settings.json if present; falls back to EXTENDED_THINKING_DEFAULT.
    """
    settings_path = Path(".claude") / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            val = data.get("extended_thinking_default")
            if isinstance(val, bool):
                return val
        except (json.JSONDecodeError, OSError):
            pass
    return EXTENDED_THINKING_DEFAULT


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify(
    *,
    feature_name: str,
    description: str,
    num_files: int,
    spec_quality: float,
    retry_count: int,
    extended_thinking: bool | str | None,
) -> bool:
    """Core classifier — returns True (ON) or False (OFF)."""
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


def _thinking_kwargs(enabled: bool) -> dict[str, Any]:
    """Return the thinking kwarg dict for Claude SDK dispatch."""
    if enabled:
        return {"type": "enabled", "budget_tokens": 10_000}
    return {}


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
