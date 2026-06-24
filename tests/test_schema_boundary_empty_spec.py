"""Tests validate_or_reject on boundary / zero-input edge cases.

Empty spec ({}), missing required fields, and other boundary conditions must
raise SchemaValidationError with informative messages — never silently pass.
"""
from __future__ import annotations

import pytest

from bob3.spec_quality.schema_constrained_emit import (
    SchemaValidationError,
    validate_or_reject,
)


def test_validate_or_reject_raises_on_empty_dict() -> None:
    with pytest.raises(SchemaValidationError):
        validate_or_reject({})


def test_validate_or_reject_empty_dict_message_contains_missing_required() -> None:
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_or_reject({})
    error_text = str(exc_info.value).lower()
    # jsonschema reports "is a required property" — check for "required"
    assert "missing required" in error_text or "required" in error_text, (
        f"Error message should mention missing required fields. Got: {error_text!r}"
    )


def test_validate_or_reject_raises_on_none_value_for_required_field() -> None:
    spec = {
        "functional_requirements": None,
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }
    with pytest.raises(SchemaValidationError):
        validate_or_reject(spec)


def test_validate_or_reject_raises_on_wrong_type_for_required_field() -> None:
    spec = {
        "functional_requirements": "not a list",
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }
    with pytest.raises(SchemaValidationError):
        validate_or_reject(spec)


def test_validate_or_reject_accepts_all_required_fields_present() -> None:
    spec = {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }
    result = validate_or_reject(spec)
    assert result is spec


def test_validate_or_reject_empty_dict_error_is_schema_validation_error() -> None:
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_or_reject({})
    assert isinstance(exc_info.value, SchemaValidationError)


def test_validate_or_reject_missing_one_required_field() -> None:
    base = {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }
    for slot in list(base.keys()):
        partial = {k: v for k, v in base.items() if k != slot}
        with pytest.raises(SchemaValidationError):
            validate_or_reject(partial)
