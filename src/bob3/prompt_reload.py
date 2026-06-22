"""Hot-reload prompt-source modules on each subagent dispatch (feature 2ce973a8).

Thin public API over ``bob3.orchestrator.prompt_source_reloader``.
Call :func:`reload_if_modified` once before each subagent dispatch so that
patches applied to ``superpowers.py`` (or any other prompt-source module) land
immediately without requiring an orchestrator restart.

Problem solved: when a patch lands on disk while the orchestrator is running,
Python's import cache means the running process continues serving the pre-patch
module-level constants for the lifetime of the process — often hours until the
next bob version build.  This module provides a cheap (one stat + dict lookup)
bounded (only reloads on actual mtime changes) fix.
"""

from __future__ import annotations

import bob3.orchestrator.prompt_source_reloader as _reloader

__all__ = ["reload_if_changed", "reload_if_modified"]


def reload_if_modified(module_name: str = "bob3.superpowers") -> bool:
    """Reload *module_name* if its on-disk source has changed since last call.

    Wraps :func:`bob3.orchestrator.prompt_source_reloader.reload_if_stale`.
    Call this once before each subagent dispatch to ensure code-fixes patched
    to disk take effect immediately — without waiting for the next orchestrator
    build.

    Args:
        module_name: Dotted module name to check and optionally reload.
                     Defaults to ``bob3.superpowers``.

    Returns:
        True if the module was reloaded, False if already up-to-date or the
        module file cannot be located.

    Raises:
        ValueError: If *module_name* is not a non-empty string.
    """
    if not isinstance(module_name, str):
        raise ValueError(
            f"module_name must be a str, got {type(module_name).__name__!r}"
        )
    return _reloader.reload_if_stale(module_name)


def reload_if_changed(module_name: str = "bob3.superpowers") -> bool:
    """Reload *module_name* if its on-disk source has changed since last call.

    Canonical alias for :func:`reload_if_modified`.  Call this once before
    each subagent dispatch so that patches applied to ``superpowers.py``
    (or any other prompt-source module) land immediately without requiring
    an orchestrator restart.

    Args:
        module_name: Dotted module name to check and optionally reload.
                     Defaults to ``bob3.superpowers``.

    Returns:
        True if the module was reloaded, False if already up-to-date or the
        module file cannot be located.

    Raises:
        ValueError: If *module_name* is not a non-empty string.
    """
    if not isinstance(module_name, str):
        raise ValueError(
            f"module_name must be a str, got {type(module_name).__name__!r}"
        )
    return _reloader.reload_if_stale(module_name)
