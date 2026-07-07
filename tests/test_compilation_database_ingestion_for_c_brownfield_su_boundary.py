"""Boundary tests for compile-commands ingestion.

Empty / zero / minimum input must return a well-defined result rather than raise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob.brownfield.compile_commands import (
    load_compile_commands,
    ingest_compilation_database,
    flags_hash,
)


def test_empty_compilation_database_returns_empty_list(tmp_path):
    (tmp_path / "compile_commands.json").write_text("[]")
    entries = load_compile_commands(tmp_path)
    assert entries == []


def test_ingest_empty_database_returns_zero_count(tmp_path):
    (tmp_path / "compile_commands.json").write_text("[]")
    result = ingest_compilation_database(tmp_path, db_path=tmp_path / "survey.db")
    assert result["count"] == 0
    assert result["entries"] == []


def test_flags_hash_empty_flags_is_defined(tmp_path):
    h = flags_hash([])
    assert isinstance(h, str)
    assert h  # non-empty, deterministic hash of empty list
    assert h == flags_hash([])


def test_entry_with_no_compile_flags(tmp_path):
    (tmp_path / "n.cpp").write_text("int n(){return 0;}\n")
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "file": "n.cpp", "arguments": ["clang++", "-c", "n.cpp"]}
    ]))
    entries = load_compile_commands(tmp_path)
    assert len(entries) == 1
    # no -I/-D/-std flags but result is well-defined
    assert isinstance(entries[0].flags, list)
    assert entries[0].flags_hash == flags_hash(entries[0].flags)


def test_ingest_missing_source_file_still_records_entry(tmp_path):
    # file referenced in cdb does not exist on disk — should not raise, sha empty
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "file": "ghost.cpp", "arguments": ["clang++", "-c", "ghost.cpp"]}
    ]))
    result = ingest_compilation_database(tmp_path, db_path=tmp_path / "survey.db")
    assert result["count"] == 1
    assert result["entries"][0]["flags_hash"]
