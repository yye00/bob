"""Database access facade.

The bob database implementation lives in the ``bob.db`` package
(``bob/db/__init__.py``). This module is a thin, named re-export so callers and
ACs that reference ``bob.database`` resolve to the same API — in particular
``create_agent_run``, which MUST write its agent_run row to the project's own
database (resolved from ``BOB_DATABASE_PATH``) rather than a cwd-relative DB.
"""

from __future__ import annotations

from bob import db as _db
from bob.db import *  # noqa: F401,F403 - re-export the full db API surface

# Explicitly re-export the most commonly referenced entry points so static
# importers (and the ``Function defined: bob.database.<name>`` ACs) resolve.
create_agent_run = _db.create_agent_run
create_feature = _db.create_feature
get_feature = _db.get_feature
update_feature = _db.update_feature
list_features = _db.list_features
connect = _db.connect

__all__ = [name for name in dir(_db) if not name.startswith("_")]
