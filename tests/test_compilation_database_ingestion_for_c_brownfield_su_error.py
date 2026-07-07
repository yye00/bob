"""Error-path tests for compile-commands ingestion.

Invalid input must raise ValueError; the function must not silently succeed.
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


def test_load_missing_compile_commands_raises(tmp_path):
    # workspace has no compile_commands.json
    with pytest.raises(ValueError):
        load_compile_commands(tmp_path)


def test_load_nonexistent_workspace_raises():
    with pytest.raises(ValueError):
        load_compile_commands(Path("/nonexistent/workspace/xyz123"))


def test_load_malformed_json_raises(tmp_path):
    (tmp_path / "compile_commands.json").write_text("{not valid json")
    with pytest.raises(ValueError):
        load_compile_commands(tmp_path)


def test_load_non_list_json_raises(tmp_path):
    (tmp_path / "compile_commands.json").write_text(json.dumps({"file": "a.cpp"}))
    with pytest.raises(ValueError):
        load_compile_commands(tmp_path)


def test_entry_missing_file_key_raises(tmp_path):
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "arguments": ["clang++", "-c", "a.cpp"]}
    ]))
    with pytest.raises(ValueError):
        load_compile_commands(tmp_path)


def test_entry_missing_command_and_arguments_raises(tmp_path):
    (tmp_path / "compile_commands.json").write_text(json.dumps([
        {"directory": str(tmp_path), "file": "a.cpp"}
    ]))
    with pytest.raises(ValueError):
        load_compile_commands(tmp_path)


def test_ingest_none_workspace_raises():
    with pytest.raises(ValueError):
        ingest_compilation_database(None, db_path=Path("/tmp/survey.db"))


def test_flags_hash_rejects_non_list():
    with pytest.raises(ValueError):
        flags_hash("not-a-list")
