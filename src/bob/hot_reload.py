"""Hot-reload subagent prompt source on each dispatch (feature bfef8e7f).

Exposes a single public function, :func:`reload_prompt_source_if_changed`,
that orchestrators call before each subagent dispatch to ensure patches
applied to superpowers.py (or any other prompt-source module) take effect
immediately without requiring an orchestrator restart.

The implementation delegates to
:mod:`bob.orchestrator.prompt_source_reloader`, which maintains an
mtime cache and calls :func:`importlib.reload` only when the file has
actually changed on disk.

Cost: one ``stat(2)`` per watched module per call — negligible.
Bound: reloads only when the file actually changed.
"""

from __future__ import annotations

import bob.orchestrator.prompt_source_reloader as _reloader

__all__ = [
    "check_and_reload_prompt_sources",
    "reload_prompt_source_if_changed",
    "reload_prompt_sources",
    "reload_prompt_sources_if_changed",
]


def reload_prompt_source_if_changed(module_name: str = "bob.superpowers") -> bool:
    """Hot-reload *module_name* if its on-disk source has changed since last call.

    Call this before each subagent dispatch so that patches applied to
    ``superpowers.py`` (or any other prompt-source module listed in
    ``bob.orchestrator.prompt_source_reloader._PROMPT_SOURCE_MODULES``)
    land immediately without requiring an orchestrator restart.

    The check is cheap (one ``stat(2)`` + dict lookup) and bounded: a
    reload is triggered only when the on-disk mtime has actually changed.

    Args:
        module_name: Dotted Python module name to check and, if stale,
            reload.  Defaults to ``bob.superpowers``, which is the
            primary source of ``VERIFICATION_PROMPT_SECTION`` and
            ``SKILLS_PROMPT_SECTION``.

    Returns:
        True if the module was reloaded, False if it was already
        up-to-date or the module file could not be found.

    Raises:
        ValueError: If *module_name* is not a non-empty string.
    """
    return _reloader.reload_if_stale(module_name)


def reload_prompt_sources() -> list[str]:
    """Hot-reload all watched prompt-source modules if their on-disk source has changed.

    Checks every module in
    ``bob.orchestrator.prompt_source_reloader._PROMPT_SOURCE_MODULES`` and
    reloads any whose on-disk mtime has advanced since the last call.

    Returns:
        List of module names that were reloaded (empty when all are up-to-date).
    """
    return _reloader.maybe_reload_all()


def reload_prompt_sources_if_changed() -> list[str]:
    """Alias for :func:`reload_prompt_sources`."""
    return reload_prompt_sources()


def check_and_reload_prompt_sources() -> list[str]:
    """Check all watched prompt-source modules and hot-reload any that have changed on disk.

    This is the primary entry point for orchestrators to call before each
    subagent dispatch.  It ensures that patches applied to ``superpowers.py``
    (or any other prompt-source module in the watch-list) take effect
    immediately without requiring an orchestrator restart.

    The implementation delegates to
    :func:`bob.orchestrator.prompt_source_reloader.maybe_reload_all`, which
    stats the mtime of each watched module and calls
    :func:`importlib.reload` only when a file has actually changed.

    Cost: one ``stat(2)`` per watched module per call — negligible.
    Bound: reloads only when the file actually changed.

    Returns:
        List of module names that were reloaded.  Empty when all watched
        modules are already up-to-date.
    """
    return _reloader.maybe_reload_all()
