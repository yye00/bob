"""Hot-reload subagent prompt source on each dispatch (feature 06837761).

Problem (bob3 v.13 r10)
-----------------------
A one-line patch to superpowers.py:749 (scoped-pytest mandate) was applied to
disk while the bob12-built orchestrator (PID 1520197) was running. Python's
import cache meant the orchestrator continued dispatching subagents with the
OLD prompt for 4+ hours — the patch only takes effect on the next bob3 version
build, which can be hours away.  During active defect-hunting loops this
defeats the dual-write protocol's "code-fix in bob(i)" half: every code patch
is invisibly delayed by one bob generation.

Fix
---
Before each subagent dispatch, call
:func:`bob3.orchestrator.prompt_source_reloader.maybe_reload_all`, which stats
the mtime of every watched prompt-source module (superpowers.py, models.py,
…).  If any has changed since the last check, ``importlib.reload()`` is called
so the updated constants (VERIFICATION_PROMPT_SECTION, SKILLS_PROMPT_SECTION,
…) are picked up immediately.

Cost: one ``os.stat`` per watched module per dispatch — negligible.
Bound: reloads only when the file actually changed.
"""

from __future__ import annotations

import bob3.orchestrator.prompt_source_reloader as _reloader

__all__ = ["hot_reload_subagent_prompt_source_each_dispatch_code_fixes"]


def hot_reload_subagent_prompt_source_each_dispatch_code_fixes() -> list[str]:
    """Hot-reload prompt-source modules if they changed on disk since last dispatch.

    Call this once before each subagent dispatch so that patches applied to
    ``superpowers.py`` (or any other prompt-source module) land immediately
    without requiring an orchestrator restart.

    The check is cheap (one ``stat(2)`` per watched module) and bounded: a
    reload is triggered only when the on-disk mtime has actually changed.

    Returns
    -------
    list[str]
        Module names that were reloaded.  Empty list when all watched modules
        were already up-to-date.
    """
    return _reloader.maybe_reload_all()
