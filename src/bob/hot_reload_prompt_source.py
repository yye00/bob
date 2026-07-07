"""Hot-reload subagent prompt source on each dispatch (feature e8dbe235).

Problem: a one-line patch to superpowers.py (e.g. line 749, the scoped-pytest
mandate) applied while the orchestrator is running is invisible to the running
process. Python's import cache means the orchestrator keeps dispatching
subagents with the pre-patch module-level constants
(VERIFICATION_PROMPT_SECTION / SKILLS_PROMPT_SECTION) until the next bob
version build — often hours away. During defect-hunting loops this defeats
the dual-write protocol's "code-fix in bob(i)" half.

Fix: before each subagent dispatch, stat the mtime of the prompt-source
module; if it changed since the last check, importlib.reload it so the
patched constants land immediately. Cheap (one stat + dict lookup) and
bounded (reloads only on an actual change).

This module is a thin, dependency-light facade over
bob.orchestrator.prompt_source_reloader so callers (superpowers, dispatch
sites) can hot-reload without importing the orchestrator package directly.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Optional

# The primary prompt-source module: source of VERIFICATION_PROMPT_SECTION
# and SKILLS_PROMPT_SECTION.
DEFAULT_PROMPT_MODULE = "bob.superpowers"

# Section constants read live from the prompt-source module after a reload.
_SECTION_NAMES: tuple[str, ...] = (
    "VERIFICATION_PROMPT_SECTION",
    "SKILLS_PROMPT_SECTION",
    "TDD_PROMPT_SECTION",
    "SUBAGENT_PROMPT_SECTION",
    "SUPERPOWERS_ORIENTATION_SECTION",
)


def reload_if_changed(module_name: str = DEFAULT_PROMPT_MODULE) -> bool:
    """Reload *module_name* if its on-disk source changed since the last check.

    Delegates to :func:`bob.orchestrator.prompt_source_reloader.reload_if_stale`,
    which performs the mtime comparison and importlib.reload.

    Args:
        module_name: Dotted module name to check and optionally reload.
            Defaults to ``bob.superpowers``.

    Returns:
        True if a reload was performed, False if the module was already
        up-to-date or its source file could not be found.

    Raises:
        ValueError: If *module_name* is not a non-empty string.
    """
    if not isinstance(module_name, str):
        raise ValueError(
            f"module_name must be a str, got {type(module_name).__name__!r}"
        )
    if not module_name.strip():
        raise ValueError("module_name must be a non-empty string")

    from bob.orchestrator import prompt_source_reloader

    return prompt_source_reloader.reload_if_stale(module_name)


def get_prompt_sections(module_name: str = DEFAULT_PROMPT_MODULE) -> dict[str, str]:
    """Return the current prompt-section text, hot-reloading first if stale.

    Calls :func:`reload_if_changed` before reading so that any on-disk patch
    to the prompt-source module is reflected in the returned sections without
    an orchestrator restart.

    Args:
        module_name: Dotted module name to read sections from.
            Defaults to ``bob.superpowers``.

    Returns:
        Mapping of section-constant name → its text, for every recognised
        prompt-section constant present on the (possibly reloaded) module.

    Raises:
        ValueError: If *module_name* is not a non-empty string.
    """
    reload_if_changed(module_name)

    module: Optional[ModuleType]
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return {}

    sections: dict[str, str] = {}
    for name in _SECTION_NAMES:
        value = getattr(module, name, None)
        if isinstance(value, str):
            sections[name] = value
    return sections


__all__ = [
    "reload_if_changed",
    "get_prompt_sections",
    "DEFAULT_PROMPT_MODULE",
]
