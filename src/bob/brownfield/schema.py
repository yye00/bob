"""BF-1 SQLite schema constants for the brownfield survey database.

The survey.db file uses these three tables:
  symbols     — every class/function/method discovered in the repo
  edges       — relationships between symbols (ref, import, inherits)
  file_hashes — per-file SHA + mtime for incremental-refresh tracking

PageRank scores are stored in symbols.pagerank after each survey run.
"""

from __future__ import annotations

# DDL for the BF-1 survey database.
SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS symbols (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT    NOT NULL,
    kind      TEXT    NOT NULL,
    name      TEXT    NOT NULL,
    sha       TEXT    NOT NULL,
    lineno    INTEGER NOT NULL,
    parent_id INTEGER REFERENCES symbols(id),
    pagerank  REAL    DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS edges (
    src_id INTEGER NOT NULL REFERENCES symbols(id),
    dst_id INTEGER NOT NULL REFERENCES symbols(id),
    kind   TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS file_hashes (
    path      TEXT PRIMARY KEY,
    sha       TEXT NOT NULL,
    mtime     REAL NOT NULL,
    parsed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Valid symbol kinds stored in symbols.kind.
SYMBOL_KINDS: tuple[str, ...] = ("class", "function", "method")

# Valid edge kinds stored in edges.kind.
EDGE_KINDS: tuple[str, ...] = ("ref", "import", "inherits")
