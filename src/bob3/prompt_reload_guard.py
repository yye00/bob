"""Prompt-source hot-reload guard — feature 43aa5d71.

Public façade for hot-reloading prompt-source modules (e.g. superpowers.py)
on each subagent dispatch so that in-flight patches take effect immediately
without requiring an orchestrator restart.

Delegates to :mod:`bob3.orchestrator.prompt_source_reloader` which maintains
the mtime cache and calls ``importlib.reload`` only when the file has actually
changed on disk.
"""

from __future__ import annotations

import bob3.orchestrator.prompt_source_reloader as _reloader

__all__ = [
    "reload_prompt_source_if_changed",
    "reload_prompt_sources",
]


def reload_prompt_source_if_changed(module_name: str = "bob3.superpowers") -> bool:
    """Hot-reload *module_name* if its on-disk source has changed since last call.

    Call before each subagent dispatch so that patches applied to
    ``superpowers.py`` (or any watched prompt-source module) land
    immediately without requiring an orchestrator restart.

    The check is cheap (one ``stat(2)`` + dict lookup) and bounded: a
    reload is triggered only when the on-disk mtime has actually changed.

    Args:
        module_name: Dotted Python module name to check and, if stale,
            reload.  Defaults to ``bob3.superpowers``.

    Returns:
        True if the module was reloaded, False if it was already
        up-to-date or the module file could not be found.

    Raises:
        ValueError: If *module_name* is not a non-empty string.
    """
    if not isinstance(module_name, str):
        raise ValueError(
            f"module_name must be a str, got {type(module_name).__name__!r}"
        )
    return _reloader.reload_if_stale(module_name)


def reload_prompt_sources() -> list[str]:
    """Hot-reload all watched prompt-source modules if their on-disk source has changed.

    Checks every module listed in
    ``bob3.orchestrator.prompt_source_reloader._PROMPT_SOURCE_MODULES`` and
    reloads any whose on-disk mtime has advanced since the last call.

    Returns:
        List of module names that were reloaded (empty when all are
        up-to-date or when no files changed).
    """
    return _reloader.maybe_reload_all()
