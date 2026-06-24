"""Tests that schema-constrained emission does NOT retry on valid output.

When the spec schema is used as a constraint (tool-use input_schema or
Outlines logit masking), the model is *forced* to produce valid JSON.
The emit path therefore needs zero retries — validate_or_reject() either
passes immediately or raises SpecSchemaError with no retry loop.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.spec_quality.schema_constrained_emit import (
    SpecSchemaError,
    emit_via_tool_schema,
    validate_or_reject,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SPEC: dict = {
    "functional_requirements": [
        {"id": "F-R1-001", "description": "System must do X"}
    ],
    "non_functional_requirements": [
        {"id": "NFR-001", "category": "perf", "description": "Latency < 100ms"}
    ],
    "acceptance_criteria": [
        {
            "id": "AC-001",
            "given": "A valid intent",
            "when": "emit_via_tool_schema is called",
            "then": "A schema-valid spec is returned without retries",
            "verifier": "pytest: tests/test_schema_constrained_no_retry_needed.py",
        }
    ],
    "out_of_scope": ["Legacy XML format support"],
    "risks": [{"description": "API key not available in CI"}],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validate_or_reject_returns_spec_unchanged() -> None:
    """validate_or_reject returns the spec dict unchanged when valid."""
    result = validate_or_reject(VALID_SPEC)
    assert result is VALID_SPEC


def test_validate_or_reject_no_exception_on_valid() -> None:
    """validate_or_reject does NOT raise on a conformant spec."""
    # Should not raise
    validate_or_reject(VALID_SPEC)


def test_validate_or_reject_does_not_call_retry_logic() -> None:
    """validate_or_reject has no retry loop; it passes or raises immediately.

    We verify this by confirming that calling it once on a valid spec
    produces exactly one validation pass with no internal retry counter.
    """
    call_count = 0
    original_load = __import__(
        "bob3.spec_quality.schema_constrained_emit", fromlist=["_load_schema"]
    )._load_schema

    def counting_load(schema_path=None):
        nonlocal call_count
        call_count += 1
        return original_load(schema_path)

    with patch(
        "bob3.spec_quality.schema_constrained_emit._load_schema", side_effect=counting_load
    ):
        validate_or_reject(VALID_SPEC)

    assert call_count == 1, (
        f"_load_schema was called {call_count} time(s); expected exactly 1 "
        "(no retry loop should exist)"
    )


def test_emit_via_tool_schema_no_retry_on_success() -> None:
    """emit_via_tool_schema returns immediately on first valid tool-use response.

    We mock the Anthropic client and verify messages.create is called exactly
    once — no retry loop.
    """
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = VALID_SPEC

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    result = emit_via_tool_schema(
        "Implement feature X with validation",
        client=mock_client,
    )

    assert mock_client.messages.create.call_count == 1, (
        "messages.create should be called exactly once; "
        f"was called {mock_client.messages.create.call_count} time(s)"
    )
    assert result == VALID_SPEC


def test_emit_via_tool_schema_uses_tool_choice_forced() -> None:
    """emit_via_tool_schema forces tool_choice to emit_spec, not auto."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = VALID_SPEC

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    emit_via_tool_schema("Feature intent", client=mock_client)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "tool_choice" in call_kwargs, "tool_choice must be set"
    assert call_kwargs["tool_choice"]["type"] == "tool"
    assert call_kwargs["tool_choice"]["name"] == "emit_spec"


def test_emit_via_tool_schema_includes_spec_schema_as_input_schema() -> None:
    """emit_via_tool_schema passes the spec v1 JSON-Schema as the tool input_schema."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = VALID_SPEC

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    emit_via_tool_schema("Feature intent", client=mock_client)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    tools = call_kwargs.get("tools", [])
    assert len(tools) == 1, "Exactly one tool should be defined"
    tool = tools[0]
    assert tool["name"] == "emit_spec"
    assert "input_schema" in tool
    # The input_schema must include the required fields from spec.v1.json
    required_fields = tool["input_schema"].get("required", [])
    for required_slot in [
        "functional_requirements",
        "non_functional_requirements",
        "acceptance_criteria",
        "out_of_scope",
        "risks",
    ]:
        assert required_slot in required_fields, (
            f"'{required_slot}' must be in tool input_schema required fields"
        )


def test_validate_or_reject_with_custom_schema_path(tmp_path: Path) -> None:
    """validate_or_reject accepts a custom schema_path override."""
    minimal_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["acceptance_criteria"],
        "properties": {
            "acceptance_criteria": {"type": "array"},
        },
    }
    schema_file = tmp_path / "custom.json"
    schema_file.write_text(json.dumps(minimal_schema))

    minimal_spec = {"acceptance_criteria": []}
    result = validate_or_reject(minimal_spec, schema_path=schema_file)
    assert result == minimal_spec
