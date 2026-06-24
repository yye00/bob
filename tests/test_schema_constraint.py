"""Tests for bob3.schema_constraint — validate_spec_against_schema and apply_constrained_decoding."""

from __future__ import annotations

from typing import Any

import pytest

from bob3.schema_constraint import (
    apply_constrained_decoding,
    validate_spec_against_schema,
)


def _minimal_valid_spec() -> dict[str, Any]:
    return {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }


# ---------------------------------------------------------------------------
# validate_spec_against_schema
# ---------------------------------------------------------------------------

class TestValidateSpecAgainstSchema:
    def test_valid_spec_returns_empty_list(self):
        errors = validate_spec_against_schema(_minimal_valid_spec())
        assert errors == []

    def test_empty_dict_returns_errors(self):
        errors = validate_spec_against_schema({})
        assert len(errors) > 0

    def test_missing_required_field_returns_errors(self):
        bad = _minimal_valid_spec()
        del bad["risks"]
        errors = validate_spec_against_schema(bad)
        assert any("risks" in e for e in errors)

    def test_wrong_type_for_array_field_returns_errors(self):
        bad = _minimal_valid_spec()
        bad["functional_requirements"] = "not a list"
        errors = validate_spec_against_schema(bad)
        assert len(errors) > 0

    def test_returns_list_of_strings(self):
        errors = validate_spec_against_schema({})
        assert isinstance(errors, list)
        assert all(isinstance(e, str) for e in errors)

    def test_strict_mode_raises_on_invalid(self):
        with pytest.raises(ValueError):
            validate_spec_against_schema({}, strict=True)

    def test_strict_mode_returns_normally_on_valid(self):
        errors = validate_spec_against_schema(_minimal_valid_spec(), strict=True)
        assert errors == []

    def test_invalid_nfr_category_returns_error(self):
        bad = _minimal_valid_spec()
        bad["non_functional_requirements"] = [
            {"id": "NFR-001", "category": "BOGUS", "description": "desc"}
        ]
        errors = validate_spec_against_schema(bad)
        assert len(errors) > 0

    def test_ac_missing_required_subfield(self):
        bad = _minimal_valid_spec()
        bad["acceptance_criteria"] = [{"id": "AC-001"}]
        errors = validate_spec_against_schema(bad)
        assert len(errors) > 0

    def test_valid_full_spec_returns_empty_list(self):
        spec = {
            "functional_requirements": [{"id": "FR-001", "description": "Do X"}],
            "non_functional_requirements": [
                {"id": "NFR-001", "category": "perf", "description": "Fast"}
            ],
            "acceptance_criteria": [
                {
                    "id": "AC-001",
                    "given": "context",
                    "when": "action",
                    "then": "outcome",
                    "verifier": "pytest tests/test_x.py",
                }
            ],
            "out_of_scope": ["Legacy support"],
            "risks": [{"description": "Some risk"}],
        }
        errors = validate_spec_against_schema(spec)
        assert errors == []

    def test_additional_properties_allowed(self):
        spec = _minimal_valid_spec()
        spec["extra_key"] = "allowed"
        errors = validate_spec_against_schema(spec)
        assert errors == []


# ---------------------------------------------------------------------------
# apply_constrained_decoding
# ---------------------------------------------------------------------------

class TestApplyConstrainedDecoding:
    def test_valid_spec_returns_same_object(self):
        spec = _minimal_valid_spec()
        result = apply_constrained_decoding(spec)
        assert result is spec

    def test_empty_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            apply_constrained_decoding({})

    def test_missing_required_field_raises(self):
        bad = _minimal_valid_spec()
        del bad["acceptance_criteria"]
        with pytest.raises(ValueError):
            apply_constrained_decoding(bad)

    def test_wrong_type_raises_value_error(self):
        bad = _minimal_valid_spec()
        bad["risks"] = 42
        with pytest.raises(ValueError):
            apply_constrained_decoding(bad)

    def test_raises_value_error_not_other(self):
        with pytest.raises(ValueError):
            apply_constrained_decoding({"bad": "structure"})

    def test_does_not_silently_succeed_on_invalid(self):
        raised = False
        try:
            apply_constrained_decoding({})
        except ValueError:
            raised = True
        assert raised

    def test_valid_spec_with_content_passes(self):
        spec = {
            "functional_requirements": [{"id": "FR-001", "description": "Emit spec"}],
            "non_functional_requirements": [],
            "acceptance_criteria": [
                {
                    "id": "AC-001",
                    "given": "A spec dict",
                    "when": "apply_constrained_decoding called",
                    "then": "Returns same dict",
                    "verifier": "pytest tests/test_schema_constraint.py",
                }
            ],
            "out_of_scope": [],
            "risks": [],
        }
        result = apply_constrained_decoding(spec)
        assert result is spec

    def test_invalid_ac_subfields_raises(self):
        bad = _minimal_valid_spec()
        bad["acceptance_criteria"] = [{"id": "AC-001"}]
        with pytest.raises(ValueError):
            apply_constrained_decoding(bad)

    def test_out_of_scope_non_string_raises(self):
        bad = _minimal_valid_spec()
        bad["out_of_scope"] = [{"not": "a string"}]
        with pytest.raises(ValueError):
            apply_constrained_decoding(bad)

    def test_additional_properties_allowed(self):
        spec = _minimal_valid_spec()
        spec["bonus"] = "extra"
        result = apply_constrained_decoding(spec)
        assert result["bonus"] == "extra"
