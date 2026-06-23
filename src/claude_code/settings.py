"""Claude Code settings integration for BF-8.

Provides a settings layer that reads .claude/settings.json and exposes
the extended_thinking_default bootstrap setting, as well as helpers for
per-feature YAML field resolution.

Satisfies ACs:
  - File exists: src/claude_code/settings.py
  - integration: claude.hooks (via extended_thinking_default)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Default: extended thinking is ON for all features unless overridden.
EXTENDED_THINKING_DEFAULT: bool = True

_SETTINGS_PATH = Path(".claude") / "settings.json"


def load_settings(settings_path: str | Path | None = None) -> dict[str, Any]:
    """Load .claude/settings.json and return the parsed dict.

    Args:
        settings_path: Override for the settings file path. Defaults to
                       .claude/settings.json relative to cwd.

    Returns:
        Parsed settings dict, or empty dict if file doesn't exist / is invalid.
    """
    path = Path(settings_path) if settings_path is not None else _SETTINGS_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def get_extended_thinking_default(settings_path: str | Path | None = None) -> bool:
    """Return the bootstrap-level extended_thinking_default setting.

    Reads .claude/settings.json if present; falls back to EXTENDED_THINKING_DEFAULT.

    Args:
        settings_path: Override for the settings file path.

    Returns:
        True if extended thinking is on by default, False otherwise.
    """
    settings = load_settings(settings_path)
    val = settings.get("extended_thinking_default")
    if isinstance(val, bool):
        return val
    return EXTENDED_THINKING_DEFAULT


def resolve_extended_thinking(
    per_feature_value: bool | str | None,
    settings_path: str | Path | None = None,
) -> bool | str:
    """Resolve the effective extended_thinking value for a feature.

    Args:
        per_feature_value: The per-feature YAML field value: True, False,
                           "auto", or None (use bootstrap default).
        settings_path:     Override for the settings file path.

    Returns:
        True, False, or "auto" — the resolved extended_thinking directive.
    """
    if per_feature_value is True:
        return True
    if per_feature_value is False:
        return False
    if per_feature_value == "auto":
        return "auto"
    # None → use bootstrap default
    return get_extended_thinking_default(settings_path)
