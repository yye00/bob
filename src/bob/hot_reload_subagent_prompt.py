"""Hot-reload subagent prompt source on each dispatch (feature f417f178).

Problem: when a code-fix is applied to superpowers.py (or another prompt-source
module) while the orchestrator is running, Python's import cache means the
running process keeps serving the pre-patch module-level constants
(VERIFICATION_PROMPT_SECTION, SKILLS_PROMPT_SECTION) until the process restarts
— often hours until the next bob version build.

Fix: before each subagent dispatch, stat the mtime of every prompt-source module;
if any has changed since last check, call importlib.reload() so the updated
constants are picked up immediately.

Cost: one stat(2) per watched module per call — negligible.
Bound: reloads only when the file actually changed.
"""

from __future__ import annotations

import bob.orchestrator.prompt_source_reloader as _reloader

__all__ = [
    "reload_prompt_source_if_changed",
]


def reload_prompt_source_if_changed(module_name: str = "bob.superpowers") -> bool:
    """Hot-reload *module_name* if its on-disk source has changed since last call.

    Call this before each subagent dispatch so that patches applied to
    superpowers.py (or any other prompt-source module) land immediately
    without requiring an orchestrator restart.

    The check is cheap (one stat(2) + dict lookup) and bounded: a reload
    is triggered only when the on-disk mtime has actually changed.

    Args:
        module_name: Dotted Python module name to check and, if stale,
            reload.  Defaults to ``bob.superpowers``, which is the
            primary source of ``VERIFICATION_PROMPT_SECTION`` and
            ``SKILLS_PROMPT_SECTION``.

    Returns:
        True if the module was reloaded, False if it was already
        up-to-date or the module file could not be found.

    Raises:
        ValueError: If *module_name* is not a string.
    """
    return _reloader.reload_if_stale(module_name)
