"""Hot-reload prompt-source modules on each subagent dispatch (feature 5899f432).

Problem: when a patch lands on disk while the orchestrator is running (e.g.
superpowers.py line 749 is edited), Python's import cache means the running
process continues serving the pre-patch module-level constants
(VERIFICATION_PROMPT_SECTION, etc.) for the lifetime of the process — often
hours until the next bob version build.

Fix: before each subagent dispatch, stat the mtime of every prompt-source
module; if any has changed since the last reload, call importlib.reload()
so the updated constants are picked up immediately.

Design:
- Cheap: only a stat(2) + dict lookup per call.
- Bounded: only reloads when the file actually changed.
- Safe: FileNotFoundError from a missing module is silently swallowed so
  a missing file never crashes the orchestrator.

Modules covered:
- bob.superpowers  — VERIFICATION_PROMPT_SECTION / SKILLS_PROMPT_SECTION
- bob.models       — Feature / Project field definitions (verifier cache issue)
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

logger = logging.getLogger(__name__)

# Module name → last-known mtime (seconds, float).
# None means "not yet loaded"; 0.0 means "file was missing on last check".
_MTIME_CACHE: dict[str, float] = {}

# Canonical module names to watch.
_PROMPT_SOURCE_MODULES: tuple[str, ...] = (
    "bob.superpowers",
    "bob.models",
)


def get_prompt_mtime(module_name: str) -> Optional[float]:
    """Return the mtime of the on-disk .py source for *module_name*.

    Returns None if the module is not importable or its ``__file__`` is
    absent / not a .py file.  Returns the mtime as a float (os.stat
    st_mtime) otherwise.

    Raises:
        ValueError: If *module_name* is not a non-empty string.
    """
    if not isinstance(module_name, str):
        raise ValueError(f"module_name must be a str, got {type(module_name).__name__!r}")
    module: ModuleType | None = sys.modules.get(module_name)
    if module is None:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            return None

    file_attr = getattr(module, "__file__", None)
    if not file_attr:
        return None

    src = Path(file_attr)
    # importlib may point at the .pyc; resolve to the .py source.
    if src.suffix == ".pyc":
        src = src.with_suffix(".py")

    try:
        return src.stat().st_mtime
    except OSError:
        return None


def reload_if_stale(module_name: str) -> bool:
    """Reload *module_name* if its on-disk source has changed since last call.

    Returns True if a reload was performed, False otherwise.

    Side effects:
    - Updates ``_MTIME_CACHE[module_name]`` to the current mtime.
    - Calls ``importlib.reload`` on the module when a change is detected.
    - Logs a warning when a reload is triggered.
    - Silently returns False when the module file is missing or unimportable.

    Raises:
        ValueError: If *module_name* is not a string.
    """
    if not isinstance(module_name, str):
        raise ValueError(f"module_name must be a str, got {type(module_name).__name__!r}")
    current_mtime = get_prompt_mtime(module_name)
    if current_mtime is None:
        # File is missing or module not importable — nothing to reload.
        return False

    last_mtime = _MTIME_CACHE.get(module_name)

    if last_mtime is None:
        # First call: record the mtime without reloading.
        _MTIME_CACHE[module_name] = current_mtime
        return False

    if current_mtime == last_mtime:
        return False

    # mtime changed — reload.
    logger.warning(
        "prompt_source_reloader: %s changed on disk (%.3f → %.3f), reloading",
        module_name,
        last_mtime,
        current_mtime,
    )
    module = sys.modules.get(module_name)
    if module is None:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            logger.error("prompt_source_reloader: failed to import %s: %s", module_name, exc)
            return False
    else:
        try:
            importlib.reload(module)
        except Exception as exc:
            logger.error("prompt_source_reloader: failed to reload %s: %s", module_name, exc)
            return False

    _MTIME_CACHE[module_name] = current_mtime
    return True


def maybe_reload_all() -> list[str]:
    """Check and hot-reload all watched prompt-source modules if stale.

    Call this once before each subagent dispatch.  It is cheap (one stat
    per module) and bounded (only reloads on actual mtime changes).

    Returns:
        List of module names that were reloaded (empty when everything was
        up-to-date or when no files changed).
    """
    reloaded: list[str] = []
    for mod_name in _PROMPT_SOURCE_MODULES:
        if reload_if_stale(mod_name):
            reloaded.append(mod_name)
    return reloaded


def reload_models_if_stale() -> bool:
    """Hot-reload bob.models if the source file has changed.

    Extends the scope of the reloader to cover the bob.models module,
    which caches Feature and Project field definitions at import time.
    When the verifier reads Feature fields from a cached import, it may
    miss fields added in a recent patch (bob v.13 r10 cached-Feature-fields
    defect).

    Returns True if a reload was performed, False otherwise.
    """
    return reload_if_stale("bob.models")


__all__ = [
    "get_prompt_mtime",
    "reload_if_stale",
    "maybe_reload_all",
    "reload_models_if_stale",
]
