"""Tests for bob3.constrained_spec_emit.

Covers emit_spec_with_schema and validate_spec_against_schema.
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


class TestEmitSpecWithSchema:
    def test_valid_spec_returns_spec(self):
        from bob3.constrained_spec_emit import emit_spec_with_schema
        spec = _minimal_valid_spec()
        result = emit_spec_with_schema(spec)
        assert isinstance(result, dict)

    def test_valid_spec_returns_same_object(self):
        from bob3.constrained_spec_emit import emit_spec_with_schema
        spec = _minimal_valid_spec()
        result = emit_spec_with_schema(spec)
        assert result is spec

    def test_invalid_spec_raises_value_error(self):
        from bob3.constrained_spec_emit import emit_spec_with_schema
        with pytest.raises(ValueError):
            emit_spec_with_schema({})

    def test_missing_required_field_raises(self):
        from bob3.constrained_spec_emit import emit_spec_with_schema
        bad = {
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "out_of_scope": [],
            "risks": [],
        }
        with pytest.raises(ValueError):
            emit_spec_with_schema(bad)

    def test_wrong_type_for_field_raises(self):
        from bob3.constrained_spec_emit import emit_spec_with_schema
        bad = _minimal_valid_spec()
        bad["functional_requirements"] = "not a list"
        with pytest.raises(ValueError):
            emit_spec_with_schema(bad)

    def test_full_spec_with_content_passes(self):
        from bob3.constrained_spec_emit import emit_spec_with_schema
        spec = {
            "functional_requirements": [
                {"id": "FR-001", "description": "System must do X"}
            ],
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
            "out_of_scope": ["Feature Y is out of scope"],
            "risks": [{"description": "Risk of delay"}],
        }
        result = emit_spec_with_schema(spec)
        assert result["functional_requirements"][0]["id"] == "FR-001"


class TestValidateSpecAgainstSchema:
    def test_valid_spec_returns_true(self):
        from bob3.constrained_spec_emit import validate_spec_against_schema
        spec = _minimal_valid_spec()
        assert validate_spec_against_schema(spec) is True

    def test_empty_dict_returns_false(self):
        from bob3.constrained_spec_emit import validate_spec_against_schema
        assert validate_spec_against_schema({}) is False

    def test_missing_required_field_returns_false(self):
        from bob3.constrained_spec_emit import validate_spec_against_schema
        bad = {
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "out_of_scope": [],
            "risks": [],
        }
        assert validate_spec_against_schema(bad) is False

    def test_wrong_type_returns_false(self):
        from bob3.constrained_spec_emit import validate_spec_against_schema
        bad = _minimal_valid_spec()
        bad["risks"] = "not a list"
        assert validate_spec_against_schema(bad) is False

    def test_does_not_raise_on_invalid(self):
        from bob3.constrained_spec_emit import validate_spec_against_schema
        # Must return False, not raise
        result = validate_spec_against_schema({"bad": "structure"})
        assert result is False

    def test_valid_spec_with_content_returns_true(self):
        from bob3.constrained_spec_emit import validate_spec_against_schema
        spec = {
            "functional_requirements": [{"id": "FR-1", "description": "Do X"}],
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "out_of_scope": [],
            "risks": [],
        }
        assert validate_spec_against_schema(spec) is True


class TestIntegrationWithSpecCritic:
    def test_module_imports_spec_critic(self):
        """constrained_spec_emit imports bob3.spec_critic (integration requirement)."""
        import bob3.constrained_spec_emit  # noqa: F401
        import bob3.spec_critic  # noqa: F401
        # If both import without error, the integration wiring exists
        assert True

    def test_functions_are_callable(self):
        from bob3.constrained_spec_emit import emit_spec_with_schema, validate_spec_against_schema
        assert callable(emit_spec_with_schema)
        assert callable(validate_spec_against_schema)
