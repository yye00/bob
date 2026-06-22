"""Top-level prompt-reloader façade (feature 20f0c750).

Thin public API over ``bob3.orchestrator.prompt_source_reloader``.
Call :func:`reload_if_modified` once before each subagent dispatch so that
patches applied to ``superpowers.py`` (or any other prompt-source module) land
immediately without requiring an orchestrator restart.
"""

from __future__ import annotations

import bob3.orchestrator.prompt_source_reloader as _reloader

__all__ = ["reload_if_changed", "reload_if_modified", "reload_prompt_source_if_changed"]


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

    Canonical alias for :func:`reload_if_modified` — satisfies AC2 of feature
    e4ddf163.  Call this once before each subagent dispatch so that patches
    applied to ``superpowers.py`` land immediately without an orchestrator
    restart.

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


def reload_prompt_source_if_changed(module_name: str = "bob3.superpowers") -> bool:
    """Reload *module_name* if its on-disk source has changed since last call.

    Alias for :func:`reload_if_modified` using the canonical name required by
    feature 9fd01e1e.  Call this once before each subagent dispatch so that
    patches applied to ``superpowers.py`` (or any other prompt-source module)
    land immediately without requiring an orchestrator restart.

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
