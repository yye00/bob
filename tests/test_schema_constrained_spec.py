"""Tests for schema_constrained_spec module.

Verifies emit_with_schema and validate_against_schema behave correctly
against the pinned schemas/spec.v1.json schema.
"""

from __future__ import annotations

from typing import Any

import pytest

from schema_constrained_spec import emit_with_schema, validate_against_schema


def _valid_spec() -> dict[str, Any]:
    return {
        "functional_requirements": [
            {"id": "FR-001", "description": "System must do X"}
        ],
        "non_functional_requirements": [
            {"id": "NFR-001", "category": "perf", "description": "Fast enough"}
        ],
        "acceptance_criteria": [
            {
                "id": "AC-001",
                "given": "a valid input",
                "when": "the function is called",
                "then": "a result is returned",
                "verifier": "pytest tests/test_something.py",
            }
        ],
        "out_of_scope": ["Offline mode"],
        "risks": [{"description": "Some known risk"}],
    }


def _minimal_valid_spec() -> dict[str, Any]:
    return {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }


class TestEmitWithSchema:
    def test_valid_spec_returns_same_dict(self):
        spec = _valid_spec()
        result = emit_with_schema(spec)
        assert result is spec

    def test_minimal_spec_is_valid(self):
        spec = _minimal_valid_spec()
        result = emit_with_schema(spec)
        assert isinstance(result, dict)

    def test_invalid_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_with_schema({})

    def test_missing_required_field_raises_value_error(self):
        bad = _minimal_valid_spec()
        del bad["risks"]
        with pytest.raises(ValueError):
            emit_with_schema(bad)

    def test_wrong_type_for_field_raises_value_error(self):
        bad = _minimal_valid_spec()
        bad["acceptance_criteria"] = "not a list"
        with pytest.raises(ValueError):
            emit_with_schema(bad)

    def test_error_message_mentions_violation_count(self):
        with pytest.raises(ValueError, match="schema violation"):
            emit_with_schema({})

    def test_does_not_silently_coerce_invalid_spec(self):
        bad = {"wrong": "structure"}
        raised = False
        try:
            emit_with_schema(bad)
        except ValueError:
            raised = True
        assert raised, "emit_with_schema must raise ValueError for invalid spec"

    def test_additional_properties_are_preserved(self):
        spec = _minimal_valid_spec()
        spec["extra"] = "data"
        result = emit_with_schema(spec)
        assert result["extra"] == "data"

    def test_nfr_invalid_category_raises(self):
        bad = _minimal_valid_spec()
        bad["non_functional_requirements"] = [
            {"id": "NFR-X", "category": "invalid", "description": "Desc"}
        ]
        with pytest.raises(ValueError):
            emit_with_schema(bad)

    def test_ac_missing_verifier_raises(self):
        bad = _minimal_valid_spec()
        bad["acceptance_criteria"] = [
            {"id": "AC-001", "given": "g", "when": "w", "then": "t"}
            # missing verifier
        ]
        with pytest.raises(ValueError):
            emit_with_schema(bad)


class TestValidateAgainstSchema:
    def test_valid_spec_returns_empty_list(self):
        errors = validate_against_schema(_valid_spec())
        assert errors == []

    def test_minimal_spec_returns_empty_list(self):
        errors = validate_against_schema(_minimal_valid_spec())
        assert errors == []

    def test_empty_dict_returns_errors(self):
        errors = validate_against_schema({})
        assert len(errors) > 0

    def test_errors_are_strings(self):
        errors = validate_against_schema({})
        for e in errors:
            assert isinstance(e, str)

    def test_missing_field_produces_error_mentioning_field(self):
        bad = _minimal_valid_spec()
        del bad["functional_requirements"]
        errors = validate_against_schema(bad)
        assert any("functional_requirements" in e for e in errors)

    def test_valid_spec_no_raise(self):
        # validate_against_schema never raises for invalid data — it returns errors
        errors = validate_against_schema({"totally": "wrong"})
        assert isinstance(errors, list)
        assert len(errors) > 0

    def test_returns_list_type(self):
        result = validate_against_schema(_valid_spec())
        assert isinstance(result, list)

    def test_invalid_nfr_category_appears_in_errors(self):
        bad = _minimal_valid_spec()
        bad["non_functional_requirements"] = [
            {"id": "N1", "category": "badcat", "description": "D"}
        ]
        errors = validate_against_schema(bad)
        assert len(errors) > 0
