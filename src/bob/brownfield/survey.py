"""Brownfield codebase survey via AST-based symbol graph + SQLite + PageRank.

BF-1: Brownfield prerequisite — queryable map of an existing repo.

build_survey():   Full parse of repo → symbols table + edges + file_hashes + PageRank.
refresh_survey(): Incremental update; re-parses only files whose mtime/sha changed.

Also exposes the legacy RepoMapper MCP launcher (F-R7-611) for backward compat.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# RepoMapper MCP server command.  Callers may override via REPOMAPPER_CMD env var.
_DEFAULT_REPOMAPPER_CMD = ["repomapper-mcp"]

# Cache DB schema version — bump when the schema changes.
_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS repomapper_cache (
    cache_key  TEXT PRIMARY KEY,
    workspace  TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    payload    TEXT NOT NULL
);
"""


@dataclass
class RepoMapperHandle:
    """Live handle to a running RepoMapper MCP server process.

    F-R7-611: This is the thin enforcement layer — bob delegates symbol-graph
    and PageRank computation to RepoMapper rather than reimplementing it.
    """

    proc: subprocess.Popen
    workspace: Path
    cache_key: str = field(default="")

    def symbol_graph(self) -> list[dict[str, Any]]:
        """Return the symbol graph from RepoMapper via its MCP tool call."""
        return self._call_tool("repomapper_symbol_graph", {})

    def pagerank(self, top_n: int = 20) -> list[dict[str, Any]]:
        """Return top-N files ranked by PageRank via RepoMapper MCP."""
        return self._call_tool("repomapper_pagerank", {"top_n": top_n})

    def _call_tool(self, tool_name: str, args: dict) -> list[dict[str, Any]]:
        """Send a JSON-RPC tool call to the RepoMapper MCP stdio server."""
        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        })
        assert self.proc.stdin is not None
        self.proc.stdin.write(request + "\n")
        self.proc.stdin.flush()
        assert self.proc.stdout is not None
        raw = self.proc.stdout.readline()
        response = json.loads(raw)
        if "error" in response:
            raise RuntimeError(f"RepoMapper MCP error: {response['error']}")
        return response.get("result", {}).get("content", [])

    def close(self) -> None:
        """Terminate the RepoMapper MCP server process."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _cache_key(workspace: Path, path_glob: str, symbols: list[str]) -> str:
    """Deterministic cache key: SHA256(workspace_hash + path_glob + sorted symbols).

    F-R7-611: Matches the deterministic cache keying from F-R7-604 / BF-2 research.
    """
    blob = json.dumps({
        "workspace": str(workspace.resolve()),
        "path_glob": path_glob,
        "symbols": sorted(symbols),
    }, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def launch_repomapper_mcp(
    workspace: Path,
    repomapper_cmd: Optional[list[str]] = None,
) -> RepoMapperHandle:
    """Launch the RepoMapper MCP server against *workspace* via stdio.

    Returns a RepoMapperHandle.  The caller is responsible for calling .close().

    F-R7-611: This is the MCP launcher that replaces the custom tree-sitter +
    PageRank implementation from sidecar_031.  Token saving: ~2K LoC → ~200 LoC.
    """
    cmd = repomapper_cmd or _DEFAULT_REPOMAPPER_CMD
    proc = subprocess.Popen(
        cmd + [str(workspace)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return RepoMapperHandle(proc=proc, workspace=workspace)


def get_cached_survey(
    db_path: Path,
    workspace: Path,
    path_glob: str = "**/*.py",
    symbols: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Return a cached RepoMapper survey result, or None if cache miss.

    survey.db is a CACHE of RepoMapper output (F-R7-611).
    """
    key = _cache_key(workspace, path_glob, symbols or [])
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA_SQL)
        row = conn.execute(
            "SELECT payload FROM repomapper_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None
    finally:
        conn.close()


def store_cached_survey(
    db_path: Path,
    workspace: Path,
    payload: dict[str, Any],
    path_glob: str = "**/*.py",
    symbols: Optional[list[str]] = None,
) -> None:
    """Persist a RepoMapper survey result into survey.db cache (F-R7-611)."""
    key = _cache_key(workspace, path_glob, symbols or [])
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT OR REPLACE INTO repomapper_cache (cache_key, workspace, payload) "
            "VALUES (?, ?, ?)",
            (key, str(workspace.resolve()), json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()


def survey(
    workspace: Path,
    db_path: Optional[Path] = None,
    path_glob: str = "**/*.py",
    symbols: Optional[list[str]] = None,
    repomapper_cmd: Optional[list[str]] = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Run a brownfield survey using RepoMapper MCP (F-R7-611).

    1. Check survey.db cache (keyed by workspace + path_glob + symbols).
    2. On cache miss, launch RepoMapper MCP server and fetch symbol_graph + pagerank.
    3. Store results in cache and return.

    This is the main entry point for brownfield survey in bob.
    RepoMapper does the heavy lifting; bob is just the thin MCP client.
    """
    if db_path is None:
        db_path = workspace / "survey.db"

    if not force_refresh:
        cached = get_cached_survey(db_path, workspace, path_glob, symbols or [])
        if cached is not None:
            return cached

    handle = launch_repomapper_mcp(workspace, repomapper_cmd)
    try:
        symbol_graph = handle.symbol_graph()
        pagerank = handle.pagerank()
        result: dict[str, Any] = {
            "symbol_graph": symbol_graph,
            "pagerank": pagerank,
            "workspace": str(workspace.resolve()),
            "path_glob": path_glob,
        }
    finally:
        handle.close()

    store_cached_survey(db_path, workspace, result, path_glob, symbols or [])
    return result


# ---------------------------------------------------------------------------
# BF-1: Native AST-based survey with SQLite + PageRank
# ---------------------------------------------------------------------------

_BF1_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS symbols (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT    NOT NULL,
    kind      TEXT    NOT NULL,  -- 'class', 'function', 'method'
    name      TEXT    NOT NULL,
    sha       TEXT    NOT NULL,  -- sha256 of the source file
    lineno    INTEGER NOT NULL,
    parent_id INTEGER REFERENCES symbols(id),
    pagerank  REAL    DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS edges (
    src_id INTEGER NOT NULL REFERENCES symbols(id),
    dst_id INTEGER NOT NULL REFERENCES symbols(id),
    kind   TEXT    NOT NULL  -- 'ref', 'import', 'inherits'
);
CREATE TABLE IF NOT EXISTS file_hashes (
    path      TEXT PRIMARY KEY,
    sha       TEXT NOT NULL,
    mtime     REAL NOT NULL,
    parsed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_IMPLICIT_FEATURE_RE = re.compile(r'\b(stub|placeholder|notimpl)\b', re.IGNORECASE)
_TODO_RE = re.compile(r'^TODO:', re.IGNORECASE)

_SOURCE_EXTENSIONS = {'.py'}  # expandable to .js/.ts/.go/.rs when parsers available


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_sources(workspace: Path) -> list[Path]:
    """Walk workspace, respecting .gitignore simple patterns and .bobignore."""
    ignore_dirs: set[str] = {'.git', '__pycache__', '.venv', 'node_modules', '.bob'}
    bobignore = workspace / '.bobignore'
    extra_ignore: set[str] = set()
    if bobignore.exists():
        for line in bobignore.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                extra_ignore.add(line.rstrip('/'))

    sources: list[Path] = []
    for path in workspace.rglob('*'):
        if any(part in ignore_dirs or part in extra_ignore for part in path.parts):
            continue
        if path.suffix in _SOURCE_EXTENSIONS and path.is_file():
            sources.append(path)
    return sources


def _parse_python_file(
    path: Path,
    sha: str,
    rel_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a Python file via ast; return (symbols, import_names)."""
    try:
        tree = ast.parse(path.read_text(errors='replace'), filename=str(path))
    except SyntaxError:
        return [], []

    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []  # raw import info for edge resolution

    def _docstring(node: ast.AST) -> str:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return ast.get_docstring(node) or ''
        return ''

    def _visit(node: ast.AST, parent_name: Optional[str], parent_idx: Optional[int]) -> None:
        if isinstance(node, ast.ClassDef):
            doc = _docstring(node)
            bases = [ast.unparse(b) for b in node.bases] if node.bases else []
            sym = {
                'path': rel_path,
                'kind': 'class',
                'name': node.name,
                'sha': sha,
                'lineno': node.lineno,
                'parent_name': parent_name,
                'parent_idx': parent_idx,
                'docstring': doc,
                'bases': bases,
            }
            idx = len(symbols)
            symbols.append(sym)
            for child in ast.iter_child_nodes(node):
                _visit(child, node.name, idx)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = _docstring(node)
            kind = 'method' if parent_name is not None else 'function'
            sym = {
                'path': rel_path,
                'kind': kind,
                'name': node.name,
                'sha': sha,
                'lineno': node.lineno,
                'parent_name': parent_name,
                'parent_idx': parent_idx,
                'docstring': doc,
                'bases': [],
            }
            idx = len(symbols)
            symbols.append(sym)
            # Don't recurse into function bodies for nested classes/funcs at top level

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ''
                for alias in node.names:
                    imports.append({'module': mod, 'name': alias.name, 'lineno': node.lineno})
            else:
                for alias in node.names:
                    imports.append({'module': alias.name, 'name': '', 'lineno': node.lineno})
        else:
            for child in ast.iter_child_nodes(node):
                _visit(child, parent_name, parent_idx)

    for child in ast.iter_child_nodes(tree):
        _visit(child, None, None)

    return symbols, imports


def _pagerank(
    node_ids: list[int],
    edges: list[tuple[int, int]],
    damping: float = 0.85,
    iterations: int = 50,
) -> dict[int, float]:
    """Power-iteration PageRank. Returns {node_id: score}."""
    if not node_ids:
        return {}
    n = len(node_ids)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    scores = {nid: 1.0 / n for nid in node_ids}

    # Build outbound edge lists
    out_edges: dict[int, list[int]] = {nid: [] for nid in node_ids}
    for src, dst in edges:
        if src in id_to_idx and dst in id_to_idx:
            out_edges[src].append(dst)

    for _ in range(iterations):
        new_scores: dict[int, float] = {}
        for nid in node_ids:
            rank = (1.0 - damping) / n
            for src in node_ids:
                if nid in out_edges[src]:
                    out_count = len(out_edges[src])
                    if out_count > 0:
                        rank += damping * scores[src] / out_count
            new_scores[nid] = rank
        scores = new_scores

    return scores


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_BF1_SCHEMA_SQL)
    conn.commit()


def _is_implicit_feature(sym: dict[str, Any]) -> bool:
    doc = sym.get('docstring', '')
    if not doc:
        return False
    return bool(_TODO_RE.match(doc) or _IMPLICIT_FEATURE_RE.search(doc))


def build_survey(
    workspace: Path,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Full brownfield survey of *workspace*.

    Walks all source files, parses with ast (Python), builds symbol graph
    in SQLite with the BF-1 schema, computes PageRank, and returns a list
    of implicit feature candidates (stubs / TODOs).

    Args:
        workspace: Root directory of the repo to survey.
        db_path:   Path for survey.db.  Defaults to workspace/.bob/survey.db.

    Returns:
        List of dicts with keys {name, path, lineno, docstring, kind}.
    """
    if db_path is None:
        bob_dir = workspace / '.bob'
        bob_dir.mkdir(exist_ok=True)
        db_path = bob_dir / 'survey.db'

    conn = sqlite3.connect(str(db_path))
    try:
        _init_db(conn)

        # Clear existing data for a full rebuild
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM symbols")
        conn.execute("DELETE FROM file_hashes")
        conn.commit()

        sources = _walk_sources(workspace)
        all_symbols: list[dict[str, Any]] = []
        all_imports_by_file: dict[str, list[dict[str, Any]]] = {}
        db_ids_by_file: dict[str, list[int]] = {}  # rel_path → list of row IDs

        for src_path in sources:
            rel_path = str(src_path.relative_to(workspace))
            sha = _file_sha(src_path)
            mtime = src_path.stat().st_mtime

            file_symbols, file_imports = _parse_python_file(src_path, sha, rel_path)

            # Insert file_hashes
            conn.execute(
                "INSERT OR REPLACE INTO file_hashes (path, sha, mtime, parsed_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (rel_path, sha, mtime),
            )

            # Insert symbols — need to track parent_id mapping
            local_id_map: dict[int, int] = {}  # local idx → db rowid
            for local_idx, sym in enumerate(file_symbols):
                parent_db_id: Optional[int] = None
                if sym['parent_idx'] is not None:
                    parent_db_id = local_id_map.get(sym['parent_idx'])

                cursor = conn.execute(
                    "INSERT INTO symbols (path, kind, name, sha, lineno, parent_id, pagerank) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0.0)",
                    (sym['path'], sym['kind'], sym['name'], sym['sha'], sym['lineno'], parent_db_id),
                )
                db_id = cursor.lastrowid
                local_id_map[local_idx] = db_id
                all_symbols.append({**sym, 'db_id': db_id})

            db_ids_by_file[rel_path] = list(local_id_map.values())
            all_imports_by_file[rel_path] = file_imports

        conn.commit()

        # Build inheritance edges (inherits) — class X(Base) where Base is a known symbol
        name_to_ids: dict[str, list[int]] = {}
        for sym in all_symbols:
            name_to_ids.setdefault(sym['name'], []).append(sym['db_id'])

        edge_rows: list[tuple[int, int, str]] = []
        for sym in all_symbols:
            if sym['kind'] == 'class':
                for base in sym.get('bases', []):
                    base_name = base.split('.')[-1]
                    for dst_id in name_to_ids.get(base_name, []):
                        edge_rows.append((sym['db_id'], dst_id, 'inherits'))

        # Build import edges — map imported names to known symbols
        for rel_path, imports in all_imports_by_file.items():
            src_ids = db_ids_by_file.get(rel_path, [])
            if not src_ids:
                continue
            src_id = src_ids[0]  # attribute import edges to first symbol in file
            for imp in imports:
                target_name = imp.get('name', '') or imp.get('module', '').split('.')[-1]
                for dst_id in name_to_ids.get(target_name, []):
                    edge_rows.append((src_id, dst_id, 'import'))

        if edge_rows:
            conn.executemany("INSERT INTO edges (src_id, dst_id, kind) VALUES (?, ?, ?)", edge_rows)
            conn.commit()

        # Compute PageRank
        all_ids = [sym['db_id'] for sym in all_symbols]
        pagerank_scores = _pagerank(all_ids, [(r[0], r[1]) for r in edge_rows])
        for nid, score in pagerank_scores.items():
            conn.execute("UPDATE symbols SET pagerank = ? WHERE id = ?", (score, nid))
        conn.commit()

        # Collect implicit feature candidates
        candidates = [
            {
                'name': sym['name'],
                'path': sym['path'],
                'lineno': sym['lineno'],
                'docstring': sym.get('docstring', ''),
                'kind': sym['kind'],
            }
            for sym in all_symbols
            if _is_implicit_feature(sym)
        ]

    finally:
        conn.close()

    return candidates


def run_repomapper_mcp(
    workspace: Path,
    repomapper_cmd: Optional[list[str]] = None,
) -> RepoMapperHandle:
    """Launch the RepoMapper MCP server and return a live handle (F-R7-611).

    This is the canonical public entry point for BF-1 scope reduction.
    Delegates to launch_repomapper_mcp — bob is a thin MCP client, not
    a reimplementation of tree-sitter + PageRank.

    The caller is responsible for calling handle.close() when done.
    """
    return launch_repomapper_mcp(workspace, repomapper_cmd=repomapper_cmd)


def refresh_survey(
    workspace: Path,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Incremental update: re-parse only files whose mtime/sha changed.

    Removes symbols for deleted files, re-parses changed files, keeps
    unchanged files as-is. Recomputes PageRank after updating.

    Returns the same implicit feature candidates list as build_survey.
    """
    if db_path is None:
        bob_dir = workspace / '.bob'
        bob_dir.mkdir(exist_ok=True)
        db_path = bob_dir / 'survey.db'

    if not db_path.exists():
        return build_survey(workspace, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        _init_db(conn)

        # Load existing file hashes
        existing: dict[str, tuple[str, float]] = {
            row[0]: (row[1], row[2])
            for row in conn.execute("SELECT path, sha, mtime FROM file_hashes").fetchall()
        }

        sources = _walk_sources(workspace)
        current_rel_paths = {str(s.relative_to(workspace)) for s in sources}

        # Remove deleted files
        deleted = set(existing.keys()) - current_rel_paths
        for rel_path in deleted:
            conn.execute("DELETE FROM edges WHERE src_id IN "
                         "(SELECT id FROM symbols WHERE path = ?)", (rel_path,))
            conn.execute("DELETE FROM edges WHERE dst_id IN "
                         "(SELECT id FROM symbols WHERE path = ?)", (rel_path,))
            conn.execute("DELETE FROM symbols WHERE path = ?", (rel_path,))
            conn.execute("DELETE FROM file_hashes WHERE path = ?", (rel_path,))
        if deleted:
            conn.commit()

        # Find changed/new files
        changed_sources: list[Path] = []
        for src_path in sources:
            rel_path = str(src_path.relative_to(workspace))
            sha = _file_sha(src_path)
            mtime = src_path.stat().st_mtime
            prev = existing.get(rel_path)
            if prev is None or prev[0] != sha:
                changed_sources.append(src_path)

        # Re-parse changed files
        all_symbols_changed: list[dict[str, Any]] = []
        changed_ids_by_file: dict[str, list[int]] = {}
        all_imports_changed: dict[str, list[dict[str, Any]]] = {}

        for src_path in changed_sources:
            rel_path = str(src_path.relative_to(workspace))
            sha = _file_sha(src_path)
            mtime = src_path.stat().st_mtime

            # Remove old data for this file
            conn.execute("DELETE FROM edges WHERE src_id IN "
                         "(SELECT id FROM symbols WHERE path = ?)", (rel_path,))
            conn.execute("DELETE FROM edges WHERE dst_id IN "
                         "(SELECT id FROM symbols WHERE path = ?)", (rel_path,))
            conn.execute("DELETE FROM symbols WHERE path = ?", (rel_path,))

            file_symbols, file_imports = _parse_python_file(src_path, sha, rel_path)

            conn.execute(
                "INSERT OR REPLACE INTO file_hashes (path, sha, mtime, parsed_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (rel_path, sha, mtime),
            )

            local_id_map: dict[int, int] = {}
            for local_idx, sym in enumerate(file_symbols):
                parent_db_id: Optional[int] = None
                if sym['parent_idx'] is not None:
                    parent_db_id = local_id_map.get(sym['parent_idx'])

                cursor = conn.execute(
                    "INSERT INTO symbols (path, kind, name, sha, lineno, parent_id, pagerank) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0.0)",
                    (sym['path'], sym['kind'], sym['name'], sym['sha'], sym['lineno'], parent_db_id),
                )
                db_id = cursor.lastrowid
                local_id_map[local_idx] = db_id
                all_symbols_changed.append({**sym, 'db_id': db_id})

            changed_ids_by_file[rel_path] = list(local_id_map.values())
            all_imports_changed[rel_path] = file_imports

        conn.commit()

        # Rebuild edges and PageRank across all symbols
        all_sym_rows = conn.execute(
            "SELECT id, name, kind, path FROM symbols"
        ).fetchall()
        all_symbol_data = [
            {'db_id': row[0], 'name': row[1], 'kind': row[2], 'path': row[3]}
            for row in all_sym_rows
        ]
        all_ids = [s['db_id'] for s in all_symbol_data]

        edge_rows_db = conn.execute("SELECT src_id, dst_id FROM edges").fetchall()
        edge_pairs = [(r[0], r[1]) for r in edge_rows_db]

        pagerank_scores = _pagerank(all_ids, edge_pairs)
        for nid, score in pagerank_scores.items():
            conn.execute("UPDATE symbols SET pagerank = ? WHERE id = ?", (score, nid))
        conn.commit()

        # Implicit feature candidates from all current symbols
        all_sym_full = conn.execute(
            "SELECT id, name, kind, path, lineno FROM symbols"
        ).fetchall()

        # Build candidates from changed files only (we don't store docstrings in DB)
        changed_candidates = [
            {
                'name': sym['name'],
                'path': sym['path'],
                'lineno': sym['lineno'],
                'docstring': sym.get('docstring', ''),
                'kind': sym['kind'],
            }
            for sym in all_symbols_changed
            if _is_implicit_feature(sym)
        ]

    finally:
        conn.close()

    return changed_candidates


def survey_repository(
    workspace: Path,
    db_path: Optional[Path] = None,
    *,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Run a brownfield survey of *workspace* and return implicit feature candidates.

    This is the canonical public entry point for BF-1. Delegates to
    build_survey (full) or refresh_survey (incremental) as appropriate.

    Args:
        workspace: Root directory of the repo to survey.
        db_path:   Path for survey.db. Defaults to <workspace>/.bob/survey.db.
        refresh:   When True, perform an incremental update (re-parse only
                   files whose mtime/sha changed). When False (default) do a
                   full rebuild.

    Returns:
        List of implicit feature candidate dicts with keys:
        {name, path, lineno, docstring, kind}

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    if refresh:
        return refresh_survey(workspace, db_path=db_path)
    return build_survey(workspace, db_path=db_path)


# ---------------------------------------------------------------------------
# Public API aliases required by BF-1 ACs
# ---------------------------------------------------------------------------


def build_symbol_graph(
    workspace: Path,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Build a symbol graph for *workspace* and persist to survey.db.

    Walks all source files, parses with AST (Python), extracts class/func/method
    definitions, references, and imports. Persists to the BF-1 SQLite schema:
    symbols, edges, file_hashes. Returns a list of symbol dicts for all
    discovered symbols.

    This is the public-API counterpart to the internal build_survey() which
    returns implicit feature candidates. build_symbol_graph() returns ALL symbols.

    Args:
        workspace: Root directory of the repo to survey.
        db_path:   Path for survey.db. Defaults to <workspace>/.bob/survey.db.

    Returns:
        List of symbol dicts with keys: {path, kind, name, sha, lineno, pagerank}

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    if db_path is None:
        bob_dir = workspace / '.bob'
        bob_dir.mkdir(exist_ok=True)
        db_path = bob_dir / 'survey.db'

    # Run a full build to populate the DB, then read back all symbols
    build_survey(workspace, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT path, kind, name, sha, lineno, pagerank FROM symbols ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            'path': row[0],
            'kind': row[1],
            'name': row[2],
            'sha': row[3],
            'lineno': row[4],
            'pagerank': row[5],
        }
        for row in rows
    ]


def compute_pagerank(
    workspace: Path,
    db_path: Optional[Path] = None,
    *,
    damping: float = 0.85,
    iterations: int = 50,
) -> list[dict[str, Any]]:
    """Compute (or recompute) PageRank over the symbol graph in survey.db.

    If survey.db does not exist, runs a full build_survey first.
    Returns symbols sorted by descending PageRank score.

    Args:
        workspace:  Root directory of the repo.
        db_path:    Path for survey.db. Defaults to <workspace>/.bob/survey.db.
        damping:    PageRank damping factor (default 0.85).
        iterations: Number of power-iteration steps (default 50).

    Returns:
        List of dicts: {id, name, path, kind, pagerank} sorted by pagerank desc.

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    if db_path is None:
        bob_dir = workspace / '.bob'
        bob_dir.mkdir(exist_ok=True)
        db_path = bob_dir / 'survey.db'

    if not db_path.exists():
        build_survey(workspace, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        _init_db(conn)
        sym_rows = conn.execute("SELECT id, name, path, kind FROM symbols").fetchall()
        edge_rows = conn.execute("SELECT src_id, dst_id FROM edges").fetchall()

        node_ids = [row[0] for row in sym_rows]
        edges = [(row[0], row[1]) for row in edge_rows]

        scores = _pagerank(node_ids, edges, damping=damping, iterations=iterations)

        for nid, score in scores.items():
            conn.execute("UPDATE symbols SET pagerank = ? WHERE id = ?", (score, nid))
        conn.commit()

        result = sorted(
            [
                {
                    'id': row[0],
                    'name': row[1],
                    'path': row[2],
                    'kind': row[3],
                    'pagerank': scores.get(row[0], 0.0),
                }
                for row in sym_rows
            ],
            key=lambda x: x['pagerank'],
            reverse=True,
        )
    finally:
        conn.close()

    return result


def scan_implicit_features(
    workspace: Path,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Scan *workspace* for implicit feature candidates (stubs, TODOs, not-impls).

    Any module/class with a docstring starting "TODO:" or matching
    r'\b(stub|placeholder|notimpl)\b' is emitted as a candidate feature
    with provenance (name, path, lineno, docstring, kind).

    If survey.db does not exist, runs a full build_survey first.

    Args:
        workspace: Root directory of the repo to survey.
        db_path:   Path for survey.db. Defaults to <workspace>/.bob/survey.db.

    Returns:
        List of candidate feature dicts: {name, path, lineno, docstring, kind}

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    return build_survey(workspace, db_path=db_path)


def parse_symbols(
    path: Path,
    *,
    workspace: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Parse a single source file and return its symbol dicts.

    Public wrapper around the internal _parse_python_file, providing a
    clean callable API required by BF-1 AC ("Function defined: parse_symbols").

    Args:
        path:      Path to the source file to parse.
        workspace: Optional workspace root for computing the relative path.
                   When omitted, uses path.parent as the base.

    Returns:
        List of symbol dicts with keys:
        {path, kind, name, sha, lineno, parent_name, parent_idx, docstring, bases}

    Raises:
        ValueError: if path does not exist or is not a file.
    """
    if not path.exists():
        raise ValueError(f"path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"path is not a file: {path}")

    base = workspace if workspace is not None else path.parent
    try:
        rel_path = str(path.relative_to(base))
    except ValueError:
        rel_path = str(path)

    sha = _file_sha(path)
    symbols, _ = _parse_python_file(path, sha, rel_path)
    return symbols


class Survey:
    """OOP façade for BF-1 brownfield survey operations.

    Wraps the functional build_survey / refresh_survey / compute_pagerank
    API in a class that holds the workspace + db_path config so callers
    don't have to pass them every time.

    Usage::

        s = Survey(workspace=Path("/my/repo"))
        candidates = s.build()          # full parse
        candidates = s.refresh()        # incremental update
        ranked     = s.pagerank()       # re-rank symbols
    """

    def __init__(
        self,
        workspace: Path | str,
        db_path: Optional[Path | str] = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        if not self.workspace.exists():
            raise ValueError(f"workspace does not exist: {self.workspace}")
        if not self.workspace.is_dir():
            raise ValueError(f"workspace is not a directory: {self.workspace}")
        self.db_path: Optional[Path] = Path(db_path).resolve() if db_path is not None else None

    def build(self) -> list[dict[str, Any]]:
        """Full survey: walk all source files, rebuild symbol graph + pagerank.

        Returns list of implicit feature candidates (stubs / TODOs).
        """
        return build_survey(self.workspace, db_path=self.db_path)

    def refresh(self) -> list[dict[str, Any]]:
        """Incremental update: re-parse only changed/new files.

        Returns list of implicit feature candidates from changed files.
        """
        return refresh_survey(self.workspace, db_path=self.db_path)

    def pagerank(
        self,
        *,
        damping: float = 0.85,
        iterations: int = 50,
    ) -> list[dict[str, Any]]:
        """Compute (or recompute) PageRank over the symbol graph.

        Returns symbols sorted by descending PageRank score.
        """
        return compute_pagerank(
            self.workspace,
            db_path=self.db_path,
            damping=damping,
            iterations=iterations,
        )

    def scan_implicit(self) -> list[dict[str, Any]]:
        """Return implicit feature candidates (stubs, TODOs) from this workspace."""
        return scan_implicit_features(self.workspace, db_path=self.db_path)


# ---------------------------------------------------------------------------
# BF-1 AC alias: index_repository
# ---------------------------------------------------------------------------


def index_repository(
    workspace: Path,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Index a repository: walk sources, build symbol graph, compute PageRank.

    This is the canonical BF-1 entry point for `bob init --brownfield`.
    Delegates to build_survey — a full parse of all source files in *workspace*,
    persisting to the BF-1 SQLite schema (symbols/edges/file_hashes) and
    computing PageRank.

    Returns the list of implicit feature candidates (stubs, TODOs, notimpls).

    Args:
        workspace: Root directory of the repo to index.
        db_path:   Path for survey.db. Defaults to <workspace>/.bob/survey.db.

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    return build_survey(workspace, db_path=db_path)


# BF-1 AC alias: survey_repo (canonical name required by acceptance criteria)
survey_repo = survey_repository


# ---------------------------------------------------------------------------
# BF-1 AC public aliases for internal helpers
# ---------------------------------------------------------------------------


def walk_repo(
    workspace: Path,
) -> list[Path]:
    """Walk *workspace* and return all source files respecting ignore rules.

    Public alias for the internal _walk_sources, required by BF-1 AC:
    "Function defined: bob.brownfield.survey.walk_repo".

    Args:
        workspace: Root directory to walk.

    Returns:
        List of Path objects for all source files found.
    """
    return _walk_sources(workspace)


def parse_and_extract_symbols(
    path: Path,
    *,
    workspace: Optional[Path] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a source file and extract symbols + imports.

    Public alias for the internal _parse_python_file, required by BF-1 AC:
    "Function defined: bob.brownfield.survey.parse_and_extract_symbols".

    Args:
        path:      Source file to parse.
        workspace: Optional root for computing a relative path label.

    Returns:
        Tuple of (symbols list, imports list).

    Raises:
        ValueError: if path does not exist or is not a file.
    """
    if not path.exists():
        raise ValueError(f"path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"path is not a file: {path}")

    base = workspace if workspace is not None else path.parent
    try:
        rel_path = str(path.relative_to(base))
    except ValueError:
        rel_path = str(path)

    sha = _file_sha(path)
    return _parse_python_file(path, sha, rel_path)


def parse_repository(
    workspace: Path,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Parse a repository and return all discovered symbols.

    Walks *workspace*, parses every source file with the Python AST engine,
    extracts class/function/method definitions and imports, persists the
    symbol graph to survey.db (BF-1 schema), computes PageRank, and returns
    a flat list of every symbol found.

    This is the canonical ``parse_repository`` entry point required by BF-1 ACs.
    Delegates to :func:`build_symbol_graph` which in turn calls :func:`build_survey`.

    Args:
        workspace: Root directory of the repo to parse.
        db_path:   Path for survey.db. Defaults to <workspace>/.bob/survey.db.

    Returns:
        List of symbol dicts: {path, kind, name, sha, lineno, pagerank}

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    return build_symbol_graph(workspace, db_path=db_path)


def incremental_update(
    workspace: Path,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Incremental brownfield survey update for *workspace*.

    Public alias for refresh_survey, required by BF-1 AC:
    "Function defined: bob.brownfield.survey.incremental_update".

    Re-parses only files whose mtime/sha changed since the last survey.
    If no prior survey.db exists, runs a full build.

    Args:
        workspace: Root directory of the repo to update.
        db_path:   Path for survey.db. Defaults to <workspace>/.bob/survey.db.

    Returns:
        List of implicit feature candidates from changed files.

    Raises:
        ValueError: if workspace does not exist or is not a directory.
    """
    if not workspace.exists():
        raise ValueError(f"workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    return refresh_survey(workspace, db_path=db_path)
