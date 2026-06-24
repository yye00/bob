"""Tests that load_pinned_schema raises SchemaFileMissingError when absent.

Missing-file error path: if schemas/spec.v1.json does not exist,
load_pinned_schema must raise SchemaFileMissingError (not a bare
FileNotFoundError or silent failure).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.spec_quality.schema_constrained_emit import (
    SchemaFileMissingError,
    handle_missing_schema_file,
    load_pinned_schema,
)


def test_load_pinned_schema_raises_when_file_absent(tmp_path: Path) -> None:
    absent_path = tmp_path / "nonexistent_spec.v1.json"
    with pytest.raises(SchemaFileMissingError):
        load_pinned_schema(schema_path=absent_path)


def test_load_pinned_schema_error_message_contains_path(tmp_path: Path) -> None:
    absent_path = tmp_path / "nonexistent_spec.v1.json"
    with pytest.raises(SchemaFileMissingError) as exc_info:
        load_pinned_schema(schema_path=absent_path)
    assert str(absent_path) in str(exc_info.value)


def test_load_pinned_schema_raises_schema_file_missing_not_generic(tmp_path: Path) -> None:
    absent_path = tmp_path / "no_such_schema.json"
    with pytest.raises(SchemaFileMissingError) as exc_info:
        load_pinned_schema(schema_path=absent_path)
    # Must be SchemaFileMissingError, not a bare FileNotFoundError
    assert type(exc_info.value) is SchemaFileMissingError


def test_handle_missing_schema_file_raises(tmp_path: Path) -> None:
    absent_path = tmp_path / "missing.json"
    with pytest.raises(SchemaFileMissingError):
        handle_missing_schema_file(schema_path=absent_path)


def test_load_pinned_schema_succeeds_when_file_exists(tmp_path: Path) -> None:
    schema_file = tmp_path / "spec.v1.json"
    schema_content = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["functional_requirements"],
        "properties": {
            "functional_requirements": {"type": "array"}
        },
    }
    import json
    schema_file.write_text(json.dumps(schema_content))
    result = load_pinned_schema(schema_path=schema_file)
    assert result["type"] == "object"
    assert "functional_requirements" in result["required"]
