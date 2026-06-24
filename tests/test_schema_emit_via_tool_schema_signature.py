"""Tests that emit_via_tool_schema has the correct public signature.

Verifies parameter names, defaults, and that the function is callable
with the expected arguments without actually invoking the Anthropic API.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bob.spec_quality.schema_constrained_emit import (
    SchemaValidationError,
    SpecSchemaError,
    emit_via_tool_schema,
    never_auto_retries,
)


def test_emit_via_tool_schema_is_callable() -> None:
    assert callable(emit_via_tool_schema)


def test_emit_via_tool_schema_has_intent_parameter() -> None:
    sig = inspect.signature(emit_via_tool_schema)
    assert "intent" in sig.parameters


def test_emit_via_tool_schema_has_client_parameter() -> None:
    sig = inspect.signature(emit_via_tool_schema)
    assert "client" in sig.parameters
    assert sig.parameters["client"].default is None


def test_emit_via_tool_schema_has_model_parameter() -> None:
    sig = inspect.signature(emit_via_tool_schema)
    assert "model" in sig.parameters


def test_emit_via_tool_schema_has_schema_path_parameter() -> None:
    sig = inspect.signature(emit_via_tool_schema)
    assert "schema_path" in sig.parameters
    assert sig.parameters["schema_path"].default is None


def test_emit_via_tool_schema_has_extra_context_parameter() -> None:
    sig = inspect.signature(emit_via_tool_schema)
    assert "extra_context" in sig.parameters


def test_schema_validation_error_is_alias_for_spec_schema_error() -> None:
    assert SchemaValidationError is SpecSchemaError


def test_never_auto_retries_returns_true() -> None:
    assert never_auto_retries() is True


def test_emit_via_tool_schema_raises_on_missing_tool_use_block(tmp_path: Path) -> None:
    import json
    schema_file = tmp_path / "spec.v1.json"
    schema_content = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["functional_requirements"],
        "properties": {"functional_requirements": {"type": "array"}},
    }
    schema_file.write_text(json.dumps(schema_content))

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = []  # No tool-use block
    mock_client.messages.create.return_value = mock_response

    with pytest.raises(SchemaValidationError):
        emit_via_tool_schema(
            "build a feature",
            client=mock_client,
            schema_path=schema_file,
        )


def test_emit_via_tool_schema_returns_validated_spec(tmp_path: Path) -> None:
    import json
    schema_file = tmp_path / "spec.v1.json"
    schema_content = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["functional_requirements"],
        "properties": {
            "functional_requirements": {"type": "array"},
        },
    }
    schema_file.write_text(json.dumps(schema_content))

    valid_spec = {"functional_requirements": []}
    mock_tool_use_block = MagicMock()
    mock_tool_use_block.type = "tool_use"
    mock_tool_use_block.input = valid_spec

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [mock_tool_use_block]
    mock_client.messages.create.return_value = mock_response

    result = emit_via_tool_schema(
        "build a feature",
        client=mock_client,
        schema_path=schema_file,
    )
    assert result == valid_spec
