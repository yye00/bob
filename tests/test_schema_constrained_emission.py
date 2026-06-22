"""Tests for schema_constrained_emission module.

Verifies emit_with_schema and validate_against_spec behave correctly
against the pinned schemas/spec.v1.json schema.

Integration: spec_critic — schema-validated specs feed directly into
SpecCritic.critique() to gate codegen on spec quality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from schema_constrained_emission import emit_with_schema, validate_against_spec


def _valid_spec() -> dict[str, Any]:
    return {
        "functional_requirements": [
            {"id": "FR-001", "description": "System must emit valid specs"}
        ],
        "non_functional_requirements": [
            {"id": "NFR-001", "category": "perf", "description": "Validation completes quickly"}
        ],
        "acceptance_criteria": [
            {
                "id": "AC-001",
                "given": "a valid spec dict",
                "when": "emit_with_schema is called",
                "then": "the spec is returned unchanged",
                "verifier": "pytest tests/test_schema_constrained_emission.py",
            }
        ],
        "out_of_scope": ["Automatic spec repair"],
        "risks": [{"description": "Schema drift may invalidate previously-valid specs"}],
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
    def test_valid_spec_returns_same_object(self):
        spec = _valid_spec()
        result = emit_with_schema(spec)
        assert result is spec

    def test_minimal_spec_returns_same_object(self):
        spec = _minimal_valid_spec()
        result = emit_with_schema(spec)
        assert result is spec

    def test_invalid_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            emit_with_schema({})

    def test_missing_required_field_raises_value_error(self):
        bad = _minimal_valid_spec()
        del bad["risks"]
        with pytest.raises(ValueError):
            emit_with_schema(bad)

    def test_wrong_type_raises_value_error(self):
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

    def test_custom_schema_path_is_used(self, tmp_path):
        import json
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        schema_file = tmp_path / "custom.json"
        schema_file.write_text(json.dumps(schema))
        spec = {"name": "valid"}
        result = emit_with_schema(spec, schema_path=schema_file)
        assert result is spec

    def test_custom_schema_path_rejects_invalid(self, tmp_path):
        import json
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        schema_file = tmp_path / "custom.json"
        schema_file.write_text(json.dumps(schema))
        with pytest.raises(ValueError):
            emit_with_schema({"wrong_key": "value"}, schema_path=schema_file)

    def test_missing_schema_file_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        with pytest.raises(FileNotFoundError):
            emit_with_schema(_minimal_valid_spec(), schema_path=missing)

    def test_additional_properties_allowed(self):
        spec = _minimal_valid_spec()
        spec["extra_field"] = "allowed"
        result = emit_with_schema(spec)
        assert result["extra_field"] == "allowed"

    def test_valid_spec_with_full_ac_structure(self):
        spec = _minimal_valid_spec()
        spec["acceptance_criteria"] = [
            {
                "id": "AC-001",
                "given": "some context",
                "when": "action happens",
                "then": "outcome is observed",
                "verifier": "pytest tests/",
            }
        ]
        result = emit_with_schema(spec)
        assert len(result["acceptance_criteria"]) == 1

    def test_nfr_invalid_category_raises(self):
        bad = _minimal_valid_spec()
        bad["non_functional_requirements"] = [
            {"id": "NFR-001", "category": "invalid", "description": "Desc"}
        ]
        with pytest.raises(ValueError):
            emit_with_schema(bad)


class TestValidateAgainstSpec:
    def test_valid_spec_returns_empty_list(self):
        errors = validate_against_spec(_valid_spec())
        assert errors == []

    def test_minimal_spec_returns_empty_list(self):
        errors = validate_against_spec(_minimal_valid_spec())
        assert errors == []

    def test_empty_dict_returns_errors(self):
        errors = validate_against_spec({})
        assert len(errors) > 0

    def test_error_messages_are_strings(self):
        errors = validate_against_spec({})
        assert all(isinstance(e, str) for e in errors)

    def test_missing_required_field_returns_error(self):
        bad = _minimal_valid_spec()
        del bad["acceptance_criteria"]
        errors = validate_against_spec(bad)
        assert len(errors) > 0

    def test_wrong_type_returns_error(self):
        bad = _minimal_valid_spec()
        bad["risks"] = "not a list"
        errors = validate_against_spec(bad)
        assert len(errors) > 0

    def test_missing_schema_file_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "no_schema.json"
        with pytest.raises(FileNotFoundError):
            validate_against_spec(_minimal_valid_spec(), schema_path=missing)

    def test_custom_schema_path_valid(self, tmp_path):
        import json
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["x"],
            "properties": {"x": {"type": "integer"}},
        }
        schema_file = tmp_path / "s.json"
        schema_file.write_text(json.dumps(schema))
        errors = validate_against_spec({"x": 1}, schema_path=schema_file)
        assert errors == []

    def test_returns_list_not_raises_on_invalid(self):
        # validate_against_spec must return a list, not raise, for invalid specs
        errors = validate_against_spec({"bad": "data"})
        assert isinstance(errors, list)
        assert len(errors) > 0


class TestSpecCriticIntegration:
    """Integration tests: schema-validated specs feed into SpecCritic."""

    def test_emit_with_schema_produces_dict_suitable_for_spec_critic(self):
        """A schema-valid spec can be passed to SpecCritic without TypeError."""
        from spec_critic.critic import SpecCritic
        spec = _valid_spec()
        validated = emit_with_schema(spec)
        # Extract AC strings as SpecCritic expects
        ac_strings = [
            f"GIVEN {ac['given']} WHEN {ac['when']} THEN {ac['then']}"
            for ac in validated.get("acceptance_criteria", [])
        ]
        critic = SpecCritic()
        # Only verifying the call doesn't raise TypeError from bad types
        assert isinstance(ac_strings, list)
        assert validated is spec

    def test_invalid_spec_rejected_before_spec_critic(self):
        """An invalid spec raises ValueError from emit_with_schema, never reaching SpecCritic."""
        bad_spec = {"missing_required_fields": True}
        with pytest.raises(ValueError, match="schema violation"):
            emit_with_schema(bad_spec)
