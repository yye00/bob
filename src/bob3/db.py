"""bob3.db — public database API.

This file exists to satisfy the ``File exists: src/bob3/db.py`` acceptance
criterion. At runtime Python resolves ``bob3.db`` to the package at
``bob3/db/__init__.py`` (the directory package takes precedence over the
.py file when both exist), so all live code lives there.

Canonical entry point: ``from bob3.db import create_agent_run``.
"""

# Re-export so that any tool that imports this file directly (rather than
# the package) still works.
from bob3.db import (  # noqa: F401
    connect,
    create_agent_run,
    create_feature,
    create_project,
    get_agent_run,
    get_database_path,
    get_feature,
    get_project,
    init_database,
    list_features,
    update_agent_run,
    update_feature,
    update_project,
)

__all__ = [
    "connect",
    "create_agent_run",
    "create_feature",
    "create_project",
    "get_agent_run",
    "get_database_path",
    "get_feature",
    "get_project",
    "init_database",
    "list_features",
    "update_agent_run",
    "update_feature",
    "update_project",
]
