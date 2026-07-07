"""Tests for compile-commands ingestion (C++ brownfield survey front end).

Feature 2604f85f: drive the brownfield survey off compile_commands.json so that
each C++ translation unit is parsed with its exact per-TU flags, and persist the
flag set + flags-hash alongside each file so index invalidation keys on
(path, sha, flags-hash).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bob.brownfield.compile_commands import (
    load_compile_commands,
    ingest_compilation_database,
    CompileEntry,
    flags_hash,
)


def _write_cdb(workspace: Path, entries: list[dict]) -> Path:
    cdb = workspace / "compile_commands.json"
    cdb.write_text(json.dumps(entries))
    return cdb


def test_load_compile_commands_arguments_form(tmp_path):
    src = tmp_path / "a.cpp"
    src.write_text("int main() { return 0; }\n")
    _write_cdb(tmp_path, [
        {
            "directory": str(tmp_path),
            "file": "a.cpp",
            "arguments": ["hipcc", "-I/opt/rocm/include", "-DNDEBUG", "-std=c++17", "-c", "a.cpp"],
        }
    ])
    entries = load_compile_commands(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert isinstance(e, CompileEntry)
    # file is resolved to an absolute path against directory
    assert e.file == str((tmp_path / "a.cpp").resolve())
    assert "-I/opt/rocm/include" in e.flags
    assert "-DNDEBUG" in e.flags
    assert "-std=c++17" in e.flags
    # the driver and the -c/file are compile-invocation noise but flags captured
    assert e.flags_hash == flags_hash(e.flags)


def test_load_compile_commands_command_string_form(tmp_path):
    src = tmp_path / "b.cpp"
    src.write_text("int f() { return 1; }\n")
    _write_cdb(tmp_path, [
        {
            "directory": str(tmp_path),
            "file": "b.cpp",
            "command": "amdclang++ -I/inc -DFOO=1 -std=c++14 -c b.cpp -o b.o",
        }
    ])
    entries = load_compile_commands(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert "-I/inc" in e.flags
    assert "-DFOO=1" in e.flags
    assert "-std=c++14" in e.flags


def test_load_compile_commands_accepts_direct_json_path(tmp_path):
    src = tmp_path / "c.cpp"
    src.write_text("int g() { return 2; }\n")
    cdb = _write_cdb(tmp_path, [
        {"directory": str(tmp_path), "file": "c.cpp", "arguments": ["clang++", "-c", "c.cpp"]}
    ])
    entries = load_compile_commands(cdb)
    assert len(entries) == 1
    assert entries[0].file == str((tmp_path / "c.cpp").resolve())


def test_flags_hash_is_order_independent_and_deterministic():
    h1 = flags_hash(["-I/a", "-DB", "-std=c++17"])
    h2 = flags_hash(["-std=c++17", "-DB", "-I/a"])
    assert h1 == h2
    assert h1 == flags_hash(["-I/a", "-DB", "-std=c++17"])
    assert flags_hash(["-I/a"]) != flags_hash(["-I/b"])


def test_ingest_persists_per_tu_flags_and_hash(tmp_path):
    (tmp_path / "x.cpp").write_text("int x() { return 0; }\n")
    (tmp_path / "y.cpp").write_text("int y() { return 0; }\n")
    _write_cdb(tmp_path, [
        {"directory": str(tmp_path), "file": "x.cpp",
         "arguments": ["hipcc", "-I/inc", "-std=c++17", "-c", "x.cpp"]},
        {"directory": str(tmp_path), "file": "y.cpp",
         "arguments": ["hipcc", "-DBAR", "-std=c++20", "-c", "y.cpp"]},
    ])
    db_path = tmp_path / "survey.db"
    result = ingest_compilation_database(tmp_path, db_path=db_path)
    assert result["count"] == 2

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT path, sha, flags, flags_hash FROM compile_commands ORDER BY path"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 2
    by_name = {Path(r[0]).name: r for r in rows}
    assert "x.cpp" in by_name and "y.cpp" in by_name
    # each row has a non-empty sha and flags_hash
    for r in rows:
        assert r[1]  # sha
        assert r[3]  # flags_hash
        flags = json.loads(r[2])
        assert isinstance(flags, list)
    # x and y have distinct flags -> distinct hashes
    assert by_name["x.cpp"][3] != by_name["y.cpp"][3]
    # persisted flags_hash matches recomputation
    xflags = json.loads(by_name["x.cpp"][2])
    assert by_name["x.cpp"][3] == flags_hash(xflags)


def test_ingest_index_invalidation_on_flags_change(tmp_path):
    src = tmp_path / "z.cpp"
    src.write_text("int z() { return 0; }\n")
    _write_cdb(tmp_path, [
        {"directory": str(tmp_path), "file": "z.cpp",
         "arguments": ["hipcc", "-std=c++17", "-c", "z.cpp"]},
    ])
    db_path = tmp_path / "survey.db"
    ingest_compilation_database(tmp_path, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        first = conn.execute("SELECT flags_hash FROM compile_commands").fetchone()[0]
    finally:
        conn.close()

    # change the compile flags for the same file+sha
    _write_cdb(tmp_path, [
        {"directory": str(tmp_path), "file": "z.cpp",
         "arguments": ["hipcc", "-std=c++20", "-DEXTRA", "-c", "z.cpp"]},
    ])
    ingest_compilation_database(tmp_path, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT flags_hash FROM compile_commands").fetchall()
    finally:
        conn.close()
    # only one row for z.cpp, and its hash changed
    assert len(rows) == 1
    assert rows[0][0] != first


def test_ingest_returns_entries_with_flags_hash(tmp_path):
    (tmp_path / "m.cpp").write_text("int m() { return 0; }\n")
    _write_cdb(tmp_path, [
        {"directory": str(tmp_path), "file": "m.cpp",
         "arguments": ["hipcc", "-I/rocm", "-c", "m.cpp"]},
    ])
    result = ingest_compilation_database(tmp_path, db_path=tmp_path / "survey.db")
    assert "entries" in result
    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert entry["flags_hash"]
    assert Path(entry["path"]).name == "m.cpp"


def test_survey_module_still_imports():
    # integration: bob.brownfield.survey
    import bob.brownfield.survey as survey
    assert hasattr(survey, "_parse_python_file")
    assert hasattr(survey, "build_survey")
