"""Tests for bob3.spec_emission — schema-constrained spec emission.

Covers emit_constrained_spec and validate_spec_against_schema.
Integration: bob3.critic is imported as a side-effect of importing spec_emission.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def _minimal_valid_spec() -> dict[str, Any]:
    return {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }


class TestEmitConstrainedSpec:
    def test_valid_spec_returns_same_dict(self):
        from bob3.spec_emission import emit_constrained_spec
        spec = _minimal_valid_spec()
        result = emit_constrained_spec(spec)
        assert result is spec

    def test_valid_spec_with_content_passes(self):
        from bob3.spec_emission import emit_constrained_spec
        spec = _minimal_valid_spec()
        spec["functional_requirements"] = [{"id": "FR-001", "description": "Do X"}]
        spec["risks"] = [{"description": "Some risk"}]
        result = emit_constrained_spec(spec)
        assert result["functional_requirements"][0]["id"] == "FR-001"

    def test_empty_dict_raises_value_error(self):
        from bob3.spec_emission import emit_constrained_spec
        with pytest.raises(ValueError):
            emit_constrained_spec({})

    def test_missing_required_field_raises_value_error(self):
        from bob3.spec_emission import emit_constrained_spec
        bad = {
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "out_of_scope": [],
            "risks": [],
        }
        with pytest.raises(ValueError):
            emit_constrained_spec(bad)

    def test_wrong_type_for_field_raises_value_error(self):
        from bob3.spec_emission import emit_constrained_spec
        bad = _minimal_valid_spec()
        bad["functional_requirements"] = "not a list"
        with pytest.raises(ValueError):
            emit_constrained_spec(bad)

    def test_invalid_ac_missing_subfields_raises(self):
        from bob3.spec_emission import emit_constrained_spec
        bad = _minimal_valid_spec()
        bad["acceptance_criteria"] = [{"id": "AC-001"}]  # missing given/when/then/verifier
        with pytest.raises(ValueError):
            emit_constrained_spec(bad)

    def test_invalid_nfr_category_raises(self):
        from bob3.spec_emission import emit_constrained_spec
        bad = _minimal_valid_spec()
        bad["non_functional_requirements"] = [
            {"id": "NFR-001", "category": "not_valid", "description": "D"}
        ]
        with pytest.raises(ValueError):
            emit_constrained_spec(bad)

    def test_full_valid_ac_passes(self):
        from bob3.spec_emission import emit_constrained_spec
        spec = _minimal_valid_spec()
        spec["acceptance_criteria"] = [
            {
                "id": "AC-001",
                "given": "a valid context",
                "when": "the action fires",
                "then": "outcome is correct",
                "verifier": "pytest tests/test_foo.py",
            }
        ]
        result = emit_constrained_spec(spec)
        assert len(result["acceptance_criteria"]) == 1

    def test_additional_properties_allowed(self):
        from bob3.spec_emission import emit_constrained_spec
        spec = _minimal_valid_spec()
        spec["custom_field"] = "allowed"
        result = emit_constrained_spec(spec)
        assert result["custom_field"] == "allowed"

    def test_schema_path_override_missing_raises_file_not_found(self, tmp_path):
        from bob3.spec_emission import emit_constrained_spec
        with pytest.raises(FileNotFoundError):
            emit_constrained_spec(_minimal_valid_spec(), schema_path=tmp_path / "nonexistent.json")

    def test_custom_schema_path_used(self, tmp_path):
        import json
        from bob3.spec_emission import emit_constrained_spec
        # Write a minimal schema that accepts any object
        schema = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"}
        schema_file = tmp_path / "custom_schema.json"
        schema_file.write_text(json.dumps(schema))
        spec = {"anything": "goes"}
        result = emit_constrained_spec(spec, schema_path=schema_file)
        assert result == {"anything": "goes"}


class TestValidateSpecAgainstSchema:
    def test_valid_spec_returns_true(self):
        from bob3.spec_emission import validate_spec_against_schema
        assert validate_spec_against_schema(_minimal_valid_spec()) is True

    def test_invalid_spec_returns_false(self):
        from bob3.spec_emission import validate_spec_against_schema
        assert validate_spec_against_schema({}) is False

    def test_does_not_raise_on_invalid_input(self):
        from bob3.spec_emission import validate_spec_against_schema
        # Must return False, not raise
        result = validate_spec_against_schema({"wrong": "structure"})
        assert result is False

    def test_missing_field_returns_false(self):
        from bob3.spec_emission import validate_spec_against_schema
        bad = _minimal_valid_spec()
        del bad["risks"]
        assert validate_spec_against_schema(bad) is False

    def test_wrong_type_returns_false(self):
        from bob3.spec_emission import validate_spec_against_schema
        bad = _minimal_valid_spec()
        bad["acceptance_criteria"] = 42
        assert validate_spec_against_schema(bad) is False

    def test_schema_path_override_missing_returns_false(self, tmp_path):
        from bob3.spec_emission import validate_spec_against_schema
        result = validate_spec_against_schema(
            _minimal_valid_spec(), schema_path=tmp_path / "nonexistent.json"
        )
        assert result is False

    def test_returns_bool_not_truthy(self):
        from bob3.spec_emission import validate_spec_against_schema
        result = validate_spec_against_schema(_minimal_valid_spec())
        assert result is True
        result2 = validate_spec_against_schema({})
        assert result2 is False


class TestIntegrationWithCritic:
    def test_import_triggers_bob3_critic_integration(self):
        """Importing spec_emission must also import bob3.spec_critic (integration AC)."""
        import bob3.spec_emission  # noqa: F401
        import sys
        assert "bob3.spec_critic" in sys.modules

    def test_emit_constrained_spec_reachable_from_bob3(self):
        from bob3.spec_emission import emit_constrained_spec
        assert callable(emit_constrained_spec)

    def test_validate_spec_against_schema_reachable_from_bob3(self):
        from bob3.spec_emission import validate_spec_against_schema
        assert callable(validate_spec_against_schema)
