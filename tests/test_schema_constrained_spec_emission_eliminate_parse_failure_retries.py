"""Tests for schema_constrained_spec_emission_eliminate_parse_failure_retries.

Verifies the public facade function and its constrained-decoding integration:
- Schema-valid specs are returned without retries.
- Invalid specs are REJECTED with SpecSchemaError, never silently coerced.
- The Anthropic tool-use path forces tool_choice to emit_spec.
- The schema mandates all required PRD slots.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.schema_constrained_spec_emission_eliminate_parse_failure_retries import (
    SpecSchemaError,
    SchemaFileMissingError,
    SchemaValidationError,
    emit_via_tool_schema,
    load_pinned_schema,
    never_auto_retries,
    schema_constrained_spec_emission_eliminate_parse_failure_retries,
    validate_or_reject,
    validate_spec_dict,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_SPEC: dict = {
    "functional_requirements": [
        {"id": "F-R1-001", "description": "System must emit schema-valid specs"}
    ],
    "non_functional_requirements": [
        {"id": "NFR-001", "category": "perf", "description": "No retry latency overhead"}
    ],
    "acceptance_criteria": [
        {
            "id": "AC-SCHEMA-001",
            "given": "A valid intent string",
            "when": "schema_constrained_spec_emission_eliminate_parse_failure_retries is called",
            "then": "A schema-valid spec dict is returned without retries",
            "verifier": "pytest: tests/test_schema_constrained_spec_emission_eliminate_parse_failure_retries.py",
        }
    ],
    "out_of_scope": ["Legacy XML format support", "YAML-only emission paths"],
    "risks": [{"description": "API key unavailable in CI; use mock client in tests"}],
}


def _make_mock_client(spec_payload: dict) -> MagicMock:
    """Build a mock Anthropic client that returns *spec_payload* as tool-use input."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = spec_payload

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# Primary AC test — required by acceptance criteria
# ---------------------------------------------------------------------------


def test_schema_constrained_spec_emission_eliminate_parse_failure_retries() -> None:
    """Primary test: function exists, returns valid spec, no retries on valid output."""
    mock_client = _make_mock_client(VALID_SPEC)

    result = schema_constrained_spec_emission_eliminate_parse_failure_retries(
        "Implement async task queue with retry back-off",
        client=mock_client,
    )

    # Returns schema-valid spec
    assert isinstance(result, dict)
    assert "functional_requirements" in result
    assert "non_functional_requirements" in result
    assert "acceptance_criteria" in result
    assert "out_of_scope" in result
    assert "risks" in result

    # No retries — messages.create called exactly once
    assert mock_client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Validate-or-reject behaviour
# ---------------------------------------------------------------------------


def test_validate_or_reject_passes_valid_spec() -> None:
    result = validate_or_reject(VALID_SPEC)
    assert result is VALID_SPEC


def test_validate_or_reject_rejects_missing_required_field() -> None:
    bad_spec = {k: v for k, v in VALID_SPEC.items() if k != "acceptance_criteria"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(bad_spec)
    assert "acceptance_criteria" in str(exc_info.value)


def test_validate_or_reject_never_silently_coerces() -> None:
    """Malformed spec must raise, not be silently fixed."""
    bad_spec = {"functional_requirements": "should-be-a-list"}
    with pytest.raises(SpecSchemaError):
        validate_or_reject(bad_spec)


def test_validate_spec_dict_annotates_source_label() -> None:
    bad_spec = {k: v for k, v in VALID_SPEC.items() if k != "risks"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_spec_dict(bad_spec, source_label="my-feature-spec.yaml")
    assert "my-feature-spec.yaml" in str(exc_info.value)


# ---------------------------------------------------------------------------
# No-retry guarantee
# ---------------------------------------------------------------------------


def test_never_auto_retries_returns_true() -> None:
    assert never_auto_retries() is True


def test_facade_no_retry_on_valid_spec() -> None:
    """Primary facade invokes messages.create exactly once for valid output."""
    mock_client = _make_mock_client(VALID_SPEC)

    schema_constrained_spec_emission_eliminate_parse_failure_retries(
        "Feature intent",
        client=mock_client,
    )

    assert mock_client.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Tool-use forced tool_choice
# ---------------------------------------------------------------------------


def test_facade_forces_tool_choice_emit_spec() -> None:
    mock_client = _make_mock_client(VALID_SPEC)

    schema_constrained_spec_emission_eliminate_parse_failure_retries(
        "Feature intent",
        client=mock_client,
    )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs.get("tool_choice", {}).get("type") == "tool"
    assert call_kwargs.get("tool_choice", {}).get("name") == "emit_spec"


def test_facade_includes_spec_schema_as_input_schema() -> None:
    mock_client = _make_mock_client(VALID_SPEC)

    schema_constrained_spec_emission_eliminate_parse_failure_retries(
        "Feature intent",
        client=mock_client,
    )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    tools = call_kwargs.get("tools", [])
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == "emit_spec"
    required_fields = tool["input_schema"].get("required", [])
    for slot in [
        "functional_requirements",
        "non_functional_requirements",
        "acceptance_criteria",
        "out_of_scope",
        "risks",
    ]:
        assert slot in required_fields, f"'{slot}' missing from tool input_schema required"


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------


def test_load_pinned_schema_returns_dict() -> None:
    schema = load_pinned_schema()
    assert isinstance(schema, dict)
    assert "required" in schema
    required = schema["required"]
    for slot in ["functional_requirements", "non_functional_requirements",
                 "acceptance_criteria", "out_of_scope", "risks"]:
        assert slot in required


def test_load_pinned_schema_raises_on_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.json"
    with pytest.raises(SchemaFileMissingError):
        load_pinned_schema(schema_path=missing)


def test_validate_or_reject_custom_schema_path(tmp_path: Path) -> None:
    """validate_or_reject accepts a custom schema_path override."""
    custom_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["acceptance_criteria"],
        "properties": {
            "acceptance_criteria": {"type": "array"},
        },
    }
    schema_file = tmp_path / "custom.json"
    schema_file.write_text(json.dumps(custom_schema))

    minimal_spec = {"acceptance_criteria": []}
    result = validate_or_reject(minimal_spec, schema_path=schema_file)
    assert result == minimal_spec


# ---------------------------------------------------------------------------
# Re-exports and type aliases
# ---------------------------------------------------------------------------


def test_schema_validation_error_is_alias_for_spec_schema_error() -> None:
    assert SchemaValidationError is SpecSchemaError


def test_spec_schema_error_carries_validation_errors() -> None:
    err = SpecSchemaError(
        "test error",
        raw_spec={"foo": "bar"},
        validation_errors=["[<root>] 'acceptance_criteria' is a required property"],
    )
    assert "acceptance_criteria" in str(err)
    assert err.raw_spec == {"foo": "bar"}
    assert len(err.validation_errors) == 1


# ---------------------------------------------------------------------------
# Outlines dispatch path (import-guarded)
# ---------------------------------------------------------------------------


def test_use_outlines_dispatches_to_emit_via_outlines() -> None:
    """When use_outlines=True, the facade calls emit_via_outlines, not emit_via_tool_schema."""
    with patch(
        "bob.schema_constrained_spec_emission_eliminate_parse_failure_retries.emit_via_outlines",
        return_value=VALID_SPEC,
    ) as mock_outlines:
        result = schema_constrained_spec_emission_eliminate_parse_failure_retries(
            "Some intent",
            use_outlines=True,
        )

    mock_outlines.assert_called_once()
    assert result == VALID_SPEC


def test_use_outlines_false_dispatches_to_tool_schema() -> None:
    """When use_outlines=False (default), the facade calls emit_via_tool_schema."""
    mock_client = _make_mock_client(VALID_SPEC)

    result = schema_constrained_spec_emission_eliminate_parse_failure_retries(
        "Some intent",
        client=mock_client,
        use_outlines=False,
    )

    assert mock_client.messages.create.call_count == 1
    assert result == VALID_SPEC
