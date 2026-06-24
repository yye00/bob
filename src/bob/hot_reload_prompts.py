"""Hot-reload subagent prompt source on each dispatch (feature d65a017c).

Exposes :func:`reload_prompt_source_if_changed` so orchestrator dispatch
paths can call it before building subagent prompts, ensuring that patches
to superpowers.py (or any other prompt-source module) land immediately
without requiring an orchestrator restart.
"""

from __future__ import annotations

from bob.orchestrator.prompt_source_reloader import reload_if_stale


def reload_prompt_source_if_changed(module_name: str = "bob.superpowers") -> bool:
    """Hot-reload a single prompt-source module if its on-disk source has changed.

    Checks the mtime of *module_name*'s source file and calls
    importlib.reload() only when the file has been modified since the last
    check.  Designed for per-dispatch use: cheap (one stat + dict lookup)
    and bounded (reloads only on actual changes).

    Args:
        module_name: Dotted module name to check and optionally reload.
                     Defaults to ``bob.superpowers`` — the primary source
                     of VERIFICATION_PROMPT_SECTION and SKILLS_PROMPT_SECTION.

    Returns:
        True if the module was reloaded, False if it was already up-to-date
        or the module file could not be found.

    Raises:
        ValueError: If *module_name* is not a string.
    """
    return reload_if_stale(module_name)


__all__ = ["reload_prompt_source_if_changed"]
