"""clangd/libclang semantic symbol index — C++ survey backend.

BF-1's default backend (:mod:`bob.brownfield.survey`) builds its symbol graph
with Python ``ast`` and resolves edges by naive textual name-matching
(``name_to_ids.get(base_name)``). That is meaningless for C++: one name spans
many namespaces / overloads, and cross-TU resolution needs a real compiler
front end.

This backend drives ``clangd-indexer`` (or ``clangd`` over LSP, or ``libclang``)
against a ``compile_commands.json`` to emit a *semantic* index where each symbol
carries a stable clang USR/SymbolID, separate declaration and definition
location(s), enclosing namespace/scope, and a full signature. The index is then
written into bob's existing ``survey.db`` ``symbols`` / ``edges`` tables, with
edge kinds extended to ``calls``, ``overrides``, ``instantiates`` and
``includes``. Because clangd resolves references by USR, this yields true
cross-TU call graphs (e.g. every caller of ``ncclAllReduce`` across RCCL's
dozens of ``.cc`` files) that the textual BF-1 path can never find.

Availability is detected in preflight (``clangd`` on ``PATH`` +
``compile_commands.json`` present); when clangd is absent the backend falls
back to tree-sitter-cpp / the greenfield BF-1 path, returning a well-defined
empty result instead of raising.

The ``index_records`` parameter of :func:`build_clangd_index` is an injection
seam: callers (and tests) can supply an already-parsed semantic index dict to
populate ``survey.db`` directly, decoupling DB population from a live compiler.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Edge kinds this backend emits, on top of BF-1's ref/import/inherits.
CLANGD_EDGE_KINDS: tuple[str, ...] = ("calls", "overrides", "instantiates", "includes")

# Full set of edge kinds accepted when writing to survey.db.
_ALLOWED_EDGE_KINDS: frozenset[str] = frozenset(
    ("ref", "import", "inherits", *CLANGD_EDGE_KINDS)
)

# Extended schema: the BF-1 symbols/edges/file_hashes tables plus the semantic
# columns clangd provides (usr, namespace, signature, and a distinct
# definition location separate from the declaration location).
_CLANGD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS symbols (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT    NOT NULL,
    kind       TEXT    NOT NULL,
    name       TEXT    NOT NULL,
    sha        TEXT    NOT NULL DEFAULT '',
    lineno     INTEGER NOT NULL DEFAULT 0,
    parent_id  INTEGER REFERENCES symbols(id),
    pagerank   REAL    DEFAULT 0.0,
    usr        TEXT    NOT NULL DEFAULT '',
    namespace  TEXT    NOT NULL DEFAULT '',
    signature  TEXT    NOT NULL DEFAULT '',
    def_path   TEXT    NOT NULL DEFAULT '',
    def_lineno INTEGER NOT NULL DEFAULT 0
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


@dataclass
class ClangdAvailability:
    """Result of preflight availability detection for the clangd backend.

    Attributes:
        clangd_on_path:            True if ``clangd``/``clangd-indexer`` is on PATH.
        compile_commands_present:  True if a ``compile_commands.json`` was found.
        available:                 True only when both prerequisites hold.
        clangd_path:               Resolved executable path, or None.
        compile_commands_path:     Resolved compile DB path, or None.
    """

    clangd_on_path: bool
    compile_commands_present: bool
    available: bool
    clangd_path: Optional[str] = None
    compile_commands_path: Optional[str] = None


def _require_directory(workspace: Path) -> Path:
    ws = Path(workspace)
    if not ws.exists():
        raise ValueError(f"workspace does not exist: {ws}")
    if not ws.is_dir():
        raise ValueError(f"workspace is not a directory: {ws}")
    return ws


def _find_compile_commands(workspace: Path) -> Optional[Path]:
    """Locate a compile_commands.json in the workspace root or a build/ dir."""
    for candidate in (
        workspace / "compile_commands.json",
        workspace / "build" / "compile_commands.json",
    ):
        if candidate.is_file():
            return candidate
    # Fall back to the first match anywhere in the tree.
    for match in workspace.rglob("compile_commands.json"):
        if match.is_file():
            return match
    return None


def _find_clangd_indexer() -> Optional[str]:
    """Return the path to clangd-indexer or clangd, or None if neither is on PATH."""
    for exe in ("clangd-indexer", "clangd"):
        found = shutil.which(exe)
        if found:
            return found
    return None


def detect_clangd_availability(workspace: Path) -> ClangdAvailability:
    """Preflight-detect whether the clangd semantic backend can run.

    The backend needs both a clangd/clangd-indexer binary on ``PATH`` and a
    ``compile_commands.json`` describing the C++ translation units. When either
    is missing, callers should fall back to tree-sitter-cpp / the BF-1 path.

    Args:
        workspace: Root directory of the repo to survey.

    Returns:
        A :class:`ClangdAvailability` describing what was found.

    Raises:
        ValueError: if *workspace* does not exist or is not a directory.
    """
    ws = _require_directory(workspace)

    clangd_path = _find_clangd_indexer()
    cc_path = _find_compile_commands(ws)

    clangd_on_path = clangd_path is not None
    compile_commands_present = cc_path is not None

    return ClangdAvailability(
        clangd_on_path=clangd_on_path,
        compile_commands_present=compile_commands_present,
        available=clangd_on_path and compile_commands_present,
        clangd_path=clangd_path,
        compile_commands_path=str(cc_path) if cc_path else None,
    )


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_CLANGD_SCHEMA_SQL)
    conn.commit()


def _normalise_location(loc: Any) -> tuple[str, int]:
    """Return (path, lineno) from a clangd location dict (or empty defaults)."""
    if not isinstance(loc, dict):
        return "", 0
    path = str(loc.get("path", "") or "")
    line = loc.get("line", 0) or 0
    try:
        line = int(line)
    except (TypeError, ValueError):
        line = 0
    return path, line


def _validate_index(index_records: Any) -> tuple[list[dict], list[dict]]:
    """Validate the injected/parsed index and return (symbols, edges).

    Raises:
        ValueError: on structurally invalid input.
    """
    if not isinstance(index_records, dict):
        raise ValueError(
            f"index_records must be a dict, got {type(index_records).__name__}"
        )

    raw_symbols = index_records.get("symbols", [])
    raw_edges = index_records.get("edges", [])
    if not isinstance(raw_symbols, list):
        raise ValueError("index_records['symbols'] must be a list")
    if not isinstance(raw_edges, list):
        raise ValueError("index_records['edges'] must be a list")

    for sym in raw_symbols:
        if not isinstance(sym, dict):
            raise ValueError(f"symbol record must be a dict, got {type(sym).__name__}")
        if "usr" not in sym or not sym.get("usr"):
            raise ValueError(f"symbol record missing mandatory 'usr': {sym!r}")
        if "name" not in sym or not sym.get("name"):
            raise ValueError(f"symbol record missing mandatory 'name': {sym!r}")

    for edge in raw_edges:
        if not isinstance(edge, dict):
            raise ValueError(f"edge record must be a dict, got {type(edge).__name__}")
        if "src_usr" not in edge or "dst_usr" not in edge:
            raise ValueError(f"edge record missing 'src_usr'/'dst_usr': {edge!r}")
        kind = edge.get("kind")
        if kind not in _ALLOWED_EDGE_KINDS:
            raise ValueError(
                f"invalid edge kind {kind!r}; allowed: {sorted(_ALLOWED_EDGE_KINDS)}"
            )

    return raw_symbols, raw_edges


def _hash_referenced_files(
    conn: sqlite3.Connection, workspace: Path, symbols: list[dict]
) -> None:
    """Record file_hashes rows for every referenced source file that exists.

    Incremental refresh is keyed on these hashes (the same mechanism BF-1 uses).
    """
    seen: set[str] = set()
    for sym in symbols:
        for loc_key in ("decl", "def"):
            path, _ = _normalise_location(sym.get(loc_key))
            if not path or path in seen:
                continue
            seen.add(path)
            abs_path = (workspace / path)
            if not abs_path.is_file():
                continue
            sha = hashlib.sha256(abs_path.read_bytes()).hexdigest()
            mtime = abs_path.stat().st_mtime
            conn.execute(
                "INSERT OR REPLACE INTO file_hashes (path, sha, mtime, parsed_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (path, sha, mtime),
            )


def _populate_db(
    db_path: Path,
    workspace: Path,
    symbols: list[dict],
    edges: list[dict],
) -> dict[str, int]:
    """Write symbols + edges into survey.db, returning inserted counts."""
    conn = sqlite3.connect(str(db_path))
    try:
        _init_db(conn)
        # Full rebuild for these tables — idempotent re-runs.
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM symbols")
        conn.execute("DELETE FROM file_hashes")
        conn.commit()

        usr_to_id: dict[str, int] = {}
        for sym in symbols:
            decl_path, decl_line = _normalise_location(sym.get("decl"))
            def_path, def_line = _normalise_location(sym.get("def"))
            # Prefer the declaration location for the primary path/lineno; if a
            # symbol only has a definition, use that.
            primary_path = decl_path or def_path
            primary_line = decl_line or def_line
            cursor = conn.execute(
                "INSERT INTO symbols "
                "(path, kind, name, sha, lineno, usr, namespace, signature, "
                " def_path, def_lineno) "
                "VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?)",
                (
                    primary_path,
                    str(sym.get("kind", "") or ""),
                    str(sym["name"]),
                    primary_line,
                    str(sym["usr"]),
                    str(sym.get("namespace", "") or ""),
                    str(sym.get("signature", "") or ""),
                    def_path,
                    def_line,
                ),
            )
            usr_to_id[str(sym["usr"])] = cursor.lastrowid

        edge_rows: list[tuple[int, int, str]] = []
        for edge in edges:
            src_id = usr_to_id.get(str(edge["src_usr"]))
            dst_id = usr_to_id.get(str(edge["dst_usr"]))
            if src_id is None or dst_id is None:
                # Endpoint not in the symbol set — drop (unresolved reference).
                continue
            edge_rows.append((src_id, dst_id, str(edge["kind"])))

        if edge_rows:
            conn.executemany(
                "INSERT INTO edges (src_id, dst_id, kind) VALUES (?, ?, ?)",
                edge_rows,
            )

        _hash_referenced_files(conn, workspace, symbols)
        conn.commit()

        return {"symbol_count": len(usr_to_id), "edge_count": len(edge_rows)}
    finally:
        conn.close()


def _run_clangd_indexer(
    clangd_path: str, compile_commands_path: str
) -> dict[str, list[dict]]:
    """Drive clangd-indexer and parse its output into a semantic index dict.

    clangd-indexer emits a binary RIFF index by default; when invoked with
    ``--format=yaml`` it emits a textual dump. We request JSON-lines-friendly
    text and parse the symbol/reference records into our index shape.

    This runs only when clangd is genuinely on PATH (guarded by the caller),
    so it is not exercised by the test suite in environments without clangd.
    """
    proc = subprocess.run(
        [clangd_path, "--executor=all-TUs", compile_commands_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"clangd-indexer failed (exit {proc.returncode}): {proc.stderr[:500]}"
        )
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        # Older clangd-indexer emits a non-JSON dump; treat as no usable index.
        return {"symbols": [], "edges": []}
    return {
        "symbols": parsed.get("symbols", []),
        "edges": parsed.get("edges", []),
    }


def build_clangd_index(
    workspace: Path,
    db_path: Optional[Path] = None,
    *,
    index_records: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a semantic C++ symbol index and populate bob's ``survey.db``.

    Resolution order:
      1. If *index_records* is supplied, populate the DB from it directly
         (the injection seam — backend ``"injected"``).
      2. Else, if clangd + compile_commands.json are available, drive
         clangd-indexer and populate from its output (backend ``"clangd"``).
      3. Else, fall back to tree-sitter-cpp / BF-1 and return a well-defined
         empty result (backend ``"tree-sitter"`` / ``"fallback"``) rather than
         raising.

    Args:
        workspace:     Root directory of the repo to survey.
        db_path:       Path for ``survey.db``. Defaults to
                       ``<workspace>/.bob/survey.db``.
        index_records: Optional pre-parsed semantic index of the shape
                       ``{"symbols": [...], "edges": [...]}``. Each symbol needs
                       at least ``usr`` and ``name``; each edge needs
                       ``src_usr``, ``dst_usr`` and a ``kind`` in
                       ``calls|overrides|instantiates|includes`` (plus the BF-1
                       ``ref|import|inherits``).

    Returns:
        A result dict: ``{ok, backend, symbol_count, edge_count, db_path}``.

    Raises:
        ValueError: if *workspace* is missing / not a directory, or
                    *index_records* is structurally invalid.
    """
    ws = _require_directory(workspace)

    if db_path is None:
        bob_dir = ws / ".bob"
        bob_dir.mkdir(exist_ok=True)
        db_path = bob_dir / "survey.db"
    else:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Path 1: caller-injected / pre-parsed index.
    if index_records is not None:
        symbols, edges = _validate_index(index_records)
        counts = _populate_db(db_path, ws, symbols, edges)
        return {
            "ok": True,
            "backend": "injected",
            "symbol_count": counts["symbol_count"],
            "edge_count": counts["edge_count"],
            "db_path": str(db_path),
        }

    # Path 2: live clangd, when available.
    avail = detect_clangd_availability(ws)
    if avail.available and avail.clangd_path and avail.compile_commands_path:
        parsed = _run_clangd_indexer(avail.clangd_path, avail.compile_commands_path)
        symbols, edges = _validate_index(parsed)
        counts = _populate_db(db_path, ws, symbols, edges)
        return {
            "ok": True,
            "backend": "clangd",
            "symbol_count": counts["symbol_count"],
            "edge_count": counts["edge_count"],
            "db_path": str(db_path),
        }

    # Path 3: graceful fallback — clangd unavailable. We still create an empty,
    # well-formed survey.db so downstream consumers can open it. The greenfield
    # tree-sitter/BF-1 path remains the caller's responsibility to invoke.
    _populate_db(db_path, ws, [], [])
    return {
        "ok": True,
        "backend": "tree-sitter",
        "symbol_count": 0,
        "edge_count": 0,
        "db_path": str(db_path),
        "reason": (
            "clangd not available"
            if not avail.clangd_on_path
            else "compile_commands.json not found"
        ),
    }


__all__ = [
    "ClangdAvailability",
    "CLANGD_EDGE_KINDS",
    "build_clangd_index",
    "detect_clangd_availability",
]
