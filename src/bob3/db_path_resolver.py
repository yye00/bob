"""bob3.db_path_resolver — canonical DB path resolution.

Resolves the absolute path to the project's SQLite database using a
priority chain:
  1. Explicit ``db_path`` argument (highest priority)
  2. ``BOB3_DATABASE_PATH`` environment variable
  3. ``<cwd>/bob3.db`` (lowest priority fallback)

Every orchestration entrypoint MUST call get_absolute_db_path and thread
the returned absolute path to all downstream steps and spawned sub-agents
so they all write to the same database file regardless of cwd changes.
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)


def get_absolute_db_path(
    db_path: pathlib.Path | str | None = None,
) -> pathlib.Path:
    """Return the absolute path to the project's SQLite database.

    Priority:
    1. ``db_path`` argument (explicit override, highest precedence)
    2. ``BOB3_DATABASE_PATH`` environment variable
    3. ``cwd/bob3.db`` (lowest priority, cwd-relative fallback)

    The returned path is always absolute (resolved via ``Path.resolve()``).
    The resolved path is logged at DEBUG level so a mismatch between
    different invocations is immediately visible in telemetry.

    Args:
        db_path: Optional explicit path. If supplied, it takes precedence
            over the environment variable and cwd fallback.

    Returns:
        Absolute ``pathlib.Path`` pointing to the database file.
    """
    if db_path is not None:
        resolved = pathlib.Path(db_path).resolve()
    else:
        env_val = os.environ.get("BOB3_DATABASE_PATH")
        if env_val:
            resolved = pathlib.Path(env_val).resolve()
        else:
            resolved = (pathlib.Path.cwd() / "bob3.db").resolve()

    logger.debug("get_absolute_db_path: resolved database path = %s", resolved)
    return resolved


__all__ = ["get_absolute_db_path"]
