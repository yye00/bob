"""Subagent prompt hot-reloader — reload prompt sources on each dispatch.

Problem: when a patch lands on disk while the orchestrator is running (e.g.
superpowers.py is edited), Python's import cache means the running process
continues serving pre-patch module-level constants
(VERIFICATION_PROMPT_SECTION, SKILLS_PROMPT_SECTION, etc.) for the lifetime
of the process — often hours until the next bob version build.

Fix: call :func:`reload_prompt_sources_if_changed` once before each subagent
dispatch.  It stats the mtime of every watched prompt-source module; if any
has changed since the last reload, ``importlib.reload()`` is called so the
updated constants are picked up immediately.

Cost: one stat(2) + dict lookup per module per dispatch — negligible.
Bound: reloads only when the file actually changed.
"""

from __future__ import annotations

import bob.orchestrator.prompt_source_reloader as _reloader

__all__ = ["reload_prompt_sources_if_changed"]


def reload_prompt_sources_if_changed() -> list[str]:
    """Hot-reload all watched prompt-source modules if their on-disk source has changed.

    Call once before each subagent dispatch.  Checks the mtime of every
    watched module (currently ``bob.superpowers`` and ``bob.models``); if
    any has changed since the last check, calls ``importlib.reload()`` so the
    updated module-level constants (VERIFICATION_PROMPT_SECTION,
    SKILLS_PROMPT_SECTION, etc.) are visible to the next dispatch without
    requiring an orchestrator restart.

    Cheap: one stat(2) + dict lookup per module per call.
    Bounded: reloads only when the file actually changed.

    Returns:
        List of module names that were reloaded (empty when all are
        up-to-date or when no files have changed).
    """
    return _reloader.maybe_reload_all()
