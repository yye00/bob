"""Hot-reload subagent prompt source on each dispatch (feature 9b346569).

A prior incident: a one-line patch to ``superpowers.py`` (the scoped-pytest
mandate) was applied to disk while the orchestrator (PID 1520197) was already
running.  Python's import cache meant the running orchestrator kept dispatching
subagents with the OLD prompt for 4+ hours — the patch only took effect on the
NEXT bob version build.

Fix: on each subagent dispatch, check the mtime of the prompt-source module
(``bob.superpowers`` and friends).  If it changed since the last reload, call
:func:`importlib.reload` before reading ``VERIFICATION_PROMPT_SECTION`` /
``SKILLS_PROMPT_SECTION``.  Cheap (a ``stat`` + dict lookup) and bounded (only
reloads when the file actually changed on disk).
"""

from __future__ import annotations

import importlib
import logging
import os
from types import ModuleType
from typing import Dict

logger = logging.getLogger(__name__)

# module name/id -> last observed source mtime
_MTIME_CACHE: Dict[str, float] = {}


def _resolve_module(module: "ModuleType | str") -> ModuleType:
    """Return a live module object for ``module`` (a module or its name).

    Raises:
        ValueError: if ``module`` is not a module or a non-empty string, or if
            a named module cannot be imported.
    """
    if isinstance(module, ModuleType):
        return module
    if isinstance(module, str):
        name = module.strip()
        if not name:
            raise ValueError("module name must be a non-empty string")
        try:
            return importlib.import_module(name)
        except ImportError as exc:
            raise ValueError(f"cannot import module {name!r}: {exc}") from exc
    raise ValueError(
        f"module must be a module object or module name, got {type(module).__name__!r}"
    )


def _module_source_mtime(module: ModuleType) -> "float | None":
    """Return the mtime of the module's source file, or None if unavailable."""
    source = getattr(module, "__file__", None)
    if not source:
        return None
    try:
        return os.stat(source).st_mtime
    except OSError:
        return None


def reload_if_changed(module: "ModuleType | str") -> bool:
    """Reload ``module`` iff its source file changed since the last check.

    On the first call for a given module the current mtime is recorded and the
    module is NOT reloaded (nothing has "changed" yet) — this returns ``False``.
    On subsequent calls the source mtime is compared against the cached value;
    if it advanced, :func:`importlib.reload` is invoked and ``True`` returned.

    Args:
        module: The module object to reload, or its importable dotted name.

    Returns:
        ``True`` if the module was reloaded, ``False`` otherwise (unchanged,
        or source mtime is unavailable).

    Raises:
        ValueError: if ``module`` is not a module object or a non-empty,
            importable module name.
    """
    mod = _resolve_module(module)
    key = mod.__name__

    current = _module_source_mtime(mod)
    if current is None:
        # No introspectable source (built-in, frozen, namespace) — nothing to do.
        return False

    previous = _MTIME_CACHE.get(key)
    if previous is None:
        _MTIME_CACHE[key] = current
        return False

    if current > previous:
        importlib.reload(mod)
        _MTIME_CACHE[key] = current
        logger.info("hot-reloaded prompt source %s (mtime %s -> %s)", key, previous, current)
        return True

    # Keep the cache honest even if the file went backwards in time.
    _MTIME_CACHE[key] = current
    return False


def reset_cache() -> None:
    """Clear the recorded mtime cache (mainly for tests)."""
    _MTIME_CACHE.clear()
