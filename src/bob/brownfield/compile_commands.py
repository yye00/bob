"""Compilation-database ingestion for the C++ brownfield survey (feature 2604f85f).

bob's BF-1 survey (``bob.brownfield.survey``) is hardwired to Python: it globs
``**/*.py`` and parses with the stdlib ``ast`` module. C++ cannot be parsed
correctly without the exact per-translation-unit compile flags (``-I`` include
dirs, ``-D`` defines, ``-std``, the hipcc/amdclang++ driver). This module is the
compile-commands-aware front end: it reads a ``compile_commands.json`` database
(produced by CMake with ``-DCMAKE_EXPORT_COMPILE_COMMANDS=ON``, or by
``bear``/``intercept-build`` for non-CMake builds) and drives the survey off the
database's ``file``/``arguments``/``directory`` entries instead of a glob.

Each entry names exactly one translation unit and the exact flags needed to parse
it. bob persists the per-TU flag set (and a flags-hash) alongside each file in
``survey.db`` so every downstream stage (localizer, verifier, stub-detector) can
re-invoke clang tooling with identical flags, and keys index invalidation on
``(path, sha, flags-hash)``.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Compile-invocation tokens that are not semantic parse flags: the driver name,
# the -c compile switch, and -o <output>. These are stripped so the flags-hash
# reflects only what affects parsing (includes, defines, std, feature flags).
_NON_FLAG_TOKENS = {"-c"}

_COMPILE_COMMANDS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS compile_commands (
    path       TEXT PRIMARY KEY,
    directory  TEXT NOT NULL,
    sha        TEXT NOT NULL,
    flags      TEXT NOT NULL,       -- JSON array of parse-relevant flags
    flags_hash TEXT NOT NULL,       -- order-independent hash of flags
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@dataclass
class CompileEntry:
    """One translation unit from a compile_commands.json database.

    Attributes:
        file:       Absolute path to the translation unit.
        directory:  Build working directory the command was invoked from.
        flags:      Parse-relevant compile flags (includes, defines, -std, ...).
        flags_hash: Order-independent hash of ``flags`` for index invalidation.
    """

    file: str
    directory: str
    flags: list[str] = field(default_factory=list)
    flags_hash: str = ""

    def __post_init__(self) -> None:
        if not self.flags_hash:
            self.flags_hash = flags_hash(self.flags)


def flags_hash(flags: list[str]) -> str:
    """Return an order-independent, deterministic SHA256 hash of *flags*.

    Two compile invocations that differ only in flag order produce the same
    hash; any change to the actual flag set changes the hash. This is the
    ``flags-hash`` component of the ``(path, sha, flags-hash)`` invalidation key.

    Raises:
        ValueError: if *flags* is not a list.
    """
    if not isinstance(flags, list):
        raise ValueError(f"flags must be a list, got {type(flags).__name__}")
    blob = json.dumps(sorted(str(f) for f in flags), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _extract_flags(tokens: list[str], tu_file: str) -> list[str]:
    """Strip non-semantic tokens (driver, -c, -o out, the TU file) from *tokens*.

    Keeps only flags that influence how the translation unit parses: include
    dirs, defines, -std, and other compiler feature flags.
    """
    if not tokens:
        return []
    flags: list[str] = []
    # First token is the compiler driver (hipcc / amdclang++ / clang++ / ...).
    tu_names = {tu_file, Path(tu_file).name}
    skip_next = False
    for i in range(1, len(tokens)):
        if skip_next:
            skip_next = False
            continue
        tok = tokens[i]
        if tok == "-o":
            skip_next = True  # drop -o and its argument
            continue
        if tok in _NON_FLAG_TOKENS:
            continue
        if tok in tu_names:
            continue
        flags.append(tok)
    return flags


def _entry_from_raw(raw: dict[str, Any]) -> CompileEntry:
    """Build a CompileEntry from one raw compile_commands.json record.

    Raises:
        ValueError: if the record is missing ``file`` or lacks both
            ``arguments`` and ``command``.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"compile_commands entry must be an object, got {type(raw).__name__}")
    if "file" not in raw:
        raise ValueError("compile_commands entry missing required 'file' key")

    directory = str(raw.get("directory", "") or "")
    file_field = str(raw["file"])

    if "arguments" in raw and raw["arguments"] is not None:
        tokens = [str(t) for t in raw["arguments"]]
    elif "command" in raw and raw["command"] is not None:
        tokens = shlex.split(str(raw["command"]))
    else:
        raise ValueError(
            f"compile_commands entry for {file_field!r} has neither "
            "'arguments' nor 'command'"
        )

    # Resolve the TU path against the build directory when relative.
    file_path = Path(file_field)
    if not file_path.is_absolute() and directory:
        file_path = Path(directory) / file_path
    resolved = str(file_path.resolve())

    flags = _extract_flags(tokens, file_field)
    return CompileEntry(file=resolved, directory=directory, flags=flags)


def _resolve_cdb_path(workspace: Path) -> Path:
    """Return the compile_commands.json path for *workspace*.

    Accepts either a directory (looks for compile_commands.json inside) or a
    direct path to a compile_commands.json file.
    """
    if workspace.is_file():
        return workspace
    return workspace / "compile_commands.json"


def load_compile_commands(workspace: Path | str) -> list[CompileEntry]:
    """Load and parse a compile_commands.json database.

    *workspace* may be a directory containing ``compile_commands.json`` or a
    direct path to the JSON file.

    Returns:
        A list of :class:`CompileEntry`, one per translation unit. An empty
        database returns an empty list (a well-defined boundary result).

    Raises:
        ValueError: if the workspace/file does not exist, the JSON is malformed,
            the top-level value is not a list, or any entry is invalid.
    """
    if workspace is None:
        raise ValueError("workspace must not be None")
    workspace = Path(workspace)
    if not workspace.exists():
        raise ValueError(f"path does not exist: {workspace}")

    cdb_path = _resolve_cdb_path(workspace)
    if not cdb_path.exists():
        raise ValueError(f"compile_commands.json not found at: {cdb_path}")

    try:
        raw_text = cdb_path.read_text()
        data = json.loads(raw_text)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"failed to parse {cdb_path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(
            f"compile_commands.json must contain a JSON array, got {type(data).__name__}"
        )

    return [_entry_from_raw(raw) for raw in data]


def _file_sha(path: Path) -> str:
    """SHA256 of *path*'s bytes, or '' if the file is missing/unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def ingest_compilation_database(
    workspace: Path | str,
    db_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Ingest a compile_commands.json into survey.db, persisting per-TU flags.

    For every translation unit in the database this writes a row into the
    ``compile_commands`` table holding the file path, build directory, source
    SHA, the parse-relevant flag set (as JSON) and its flags-hash. Re-ingesting
    the same file replaces its row, so index invalidation keys naturally on
    ``(path, sha, flags-hash)``.

    Args:
        workspace: Directory containing ``compile_commands.json`` (or a direct
            path to the JSON file).
        db_path:   Path for survey.db. Defaults to ``<workspace>/.bob/survey.db``
            when *workspace* is a directory, else ``survey.db`` next to the JSON.

    Returns:
        ``{"count": int, "entries": [{"path", "sha", "flags", "flags_hash", "directory"}]}``.
        An empty database yields ``{"count": 0, "entries": []}``.

    Raises:
        ValueError: for the same invalid-input conditions as
            :func:`load_compile_commands`, plus a None workspace.
    """
    if workspace is None:
        raise ValueError("workspace must not be None")
    workspace = Path(workspace)

    entries = load_compile_commands(workspace)

    if db_path is None:
        base_dir = workspace if workspace.is_dir() else workspace.parent
        bob_dir = base_dir / ".bob"
        bob_dir.mkdir(exist_ok=True, parents=True)
        db_path = bob_dir / "survey.db"
    db_path = Path(db_path)

    out_entries: list[dict[str, Any]] = []
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_COMPILE_COMMANDS_SCHEMA_SQL)
        for e in entries:
            sha = _file_sha(Path(e.file))
            flags_json = json.dumps(e.flags)
            conn.execute(
                "INSERT OR REPLACE INTO compile_commands "
                "(path, directory, sha, flags, flags_hash, ingested_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (e.file, e.directory, sha, flags_json, e.flags_hash),
            )
            out_entries.append({
                "path": e.file,
                "directory": e.directory,
                "sha": sha,
                "flags": e.flags,
                "flags_hash": e.flags_hash,
            })
        conn.commit()
    finally:
        conn.close()

    return {"count": len(out_entries), "entries": out_entries}
