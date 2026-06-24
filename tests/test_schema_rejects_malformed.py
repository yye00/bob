"""Tests that validate_or_reject raises SpecSchemaError on malformed specs.

Specs that fail validation are REJECTED with an explicit SpecSchemaError,
never silently coerced or auto-retried.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bob.spec_quality.schema_constrained_emit import (
    SpecSchemaError,
    emit_via_tool_schema,
    validate_or_reject,
    validate_spec_dict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SPEC: dict = {
    "functional_requirements": [],
    "non_functional_requirements": [],
    "acceptance_criteria": [],
    "out_of_scope": [],
    "risks": [],
}


def _make_spec(**overrides: object) -> dict:
    spec = dict(VALID_SPEC)
    spec.update(overrides)
    return spec


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


def test_rejects_spec_missing_functional_requirements() -> None:
    spec = {k: v for k, v in VALID_SPEC.items() if k != "functional_requirements"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(spec)
    assert "functional_requirements" in str(exc_info.value)


def test_rejects_spec_missing_non_functional_requirements() -> None:
    spec = {k: v for k, v in VALID_SPEC.items() if k != "non_functional_requirements"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(spec)
    assert "non_functional_requirements" in str(exc_info.value)


def test_rejects_spec_missing_acceptance_criteria() -> None:
    spec = {k: v for k, v in VALID_SPEC.items() if k != "acceptance_criteria"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(spec)
    assert "acceptance_criteria" in str(exc_info.value)


def test_rejects_spec_missing_out_of_scope() -> None:
    spec = {k: v for k, v in VALID_SPEC.items() if k != "out_of_scope"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(spec)
    assert "out_of_scope" in str(exc_info.value)


def test_rejects_spec_missing_risks() -> None:
    spec = {k: v for k, v in VALID_SPEC.items() if k != "risks"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(spec)
    assert "risks" in str(exc_info.value)


def test_rejects_entirely_empty_spec() -> None:
    with pytest.raises(SpecSchemaError):
        validate_or_reject({})


# ---------------------------------------------------------------------------
# Wrong types
# ---------------------------------------------------------------------------


def test_rejects_spec_with_string_functional_requirements() -> None:
    """functional_requirements must be an array, not a string."""
    spec = _make_spec(functional_requirements="should be a list")
    with pytest.raises(SpecSchemaError):
        validate_or_reject(spec)


def test_rejects_spec_with_dict_out_of_scope() -> None:
    """out_of_scope must be an array, not a dict."""
    spec = _make_spec(out_of_scope={"item": "foo"})
    with pytest.raises(SpecSchemaError):
        validate_or_reject(spec)


def test_rejects_nfr_with_invalid_category() -> None:
    """non_functional_requirements category must be one of the enum values."""
    spec = _make_spec(
        non_functional_requirements=[
            {"id": "NFR-001", "category": "invalid_category", "description": "Test"}
        ]
    )
    with pytest.raises(SpecSchemaError):
        validate_or_reject(spec)


def test_rejects_ac_missing_given_field() -> None:
    """acceptance_criteria items must have 'given' field."""
    spec = _make_spec(
        acceptance_criteria=[
            {
                "id": "AC-001",
                # missing 'given'
                "when": "something happens",
                "then": "expected outcome",
                "verifier": "pytest: tests/foo.py",
            }
        ]
    )
    with pytest.raises(SpecSchemaError):
        validate_or_reject(spec)


def test_rejects_ac_missing_when_field() -> None:
    """acceptance_criteria items must have 'when' field."""
    spec = _make_spec(
        acceptance_criteria=[
            {
                "id": "AC-001",
                "given": "a condition",
                # missing 'when'
                "then": "expected outcome",
                "verifier": "pytest: tests/foo.py",
            }
        ]
    )
    with pytest.raises(SpecSchemaError):
        validate_or_reject(spec)


def test_rejects_ac_missing_verifier_field() -> None:
    """acceptance_criteria items must have 'verifier' field."""
    spec = _make_spec(
        acceptance_criteria=[
            {
                "id": "AC-001",
                "given": "a condition",
                "when": "something happens",
                "then": "expected outcome",
                # missing 'verifier'
            }
        ]
    )
    with pytest.raises(SpecSchemaError):
        validate_or_reject(spec)


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


def test_rejection_error_contains_validation_errors_list() -> None:
    """SpecSchemaError.validation_errors is a non-empty list on failure."""
    spec = {}  # missing all required fields
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(spec)
    assert isinstance(exc_info.value.validation_errors, list)
    assert len(exc_info.value.validation_errors) > 0


def test_rejection_error_preserves_raw_spec() -> None:
    """SpecSchemaError.raw_spec preserves the failing input for forensics."""
    bad_spec = {"acceptance_criteria": "wrong_type"}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(bad_spec)
    assert exc_info.value.raw_spec is bad_spec


def test_rejection_error_str_includes_violation_details() -> None:
    """str(SpecSchemaError) includes field-level violation details."""
    spec = {}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_or_reject(spec)
    error_str = str(exc_info.value)
    assert "violation" in error_str.lower() or "error" in error_str.lower()


# ---------------------------------------------------------------------------
# validate_spec_dict source label propagation
# ---------------------------------------------------------------------------


def test_validate_spec_dict_raises_with_source_label() -> None:
    """validate_spec_dict SpecSchemaError message includes the source label."""
    bad_spec = {}
    with pytest.raises(SpecSchemaError) as exc_info:
        validate_spec_dict(bad_spec, source_label="my_feature_id")
    assert "my_feature_id" in str(exc_info.value)


# ---------------------------------------------------------------------------
# emit_via_tool_schema rejects bad model output
# ---------------------------------------------------------------------------


def test_emit_via_tool_schema_raises_on_no_tool_use_block() -> None:
    """emit_via_tool_schema raises SpecSchemaError when model returns no tool-use block."""
    # Model response with only text content, no tool_use block
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Here is your spec: {}"

    mock_response = MagicMock()
    mock_response.content = [text_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with pytest.raises(SpecSchemaError):
        emit_via_tool_schema("Feature intent", client=mock_client)


def test_emit_via_tool_schema_raises_on_schema_violating_tool_output() -> None:
    """emit_via_tool_schema validates tool output; rejects schema-violating results."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = {"acceptance_criteria": "wrong_type"}  # violates schema

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with pytest.raises(SpecSchemaError):
        emit_via_tool_schema("Feature intent", client=mock_client)
