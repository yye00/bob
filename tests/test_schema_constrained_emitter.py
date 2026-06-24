"""Tests for bob3.schema_constrained_emitter.emit_with_schema.

Tests the integration facade: schema validation, rejection behaviour,
and integration with bob3.spec_critic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


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
                "verifier": "pytest tests/test_schema_constrained_emitter.py",
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


class TestEmitWithSchemaExists:
    def test_module_importable(self):
        """bob3.schema_constrained_emitter must be importable."""
        import bob3.schema_constrained_emitter  # noqa: F401

    def test_function_defined(self):
        """emit_with_schema must be defined in bob3.schema_constrained_emitter."""
        from bob3.schema_constrained_emitter import emit_with_schema
        assert callable(emit_with_schema)


class TestEmitWithSchemaValid:
    def test_valid_spec_returned_unchanged(self):
        """emit_with_schema returns valid spec dict unchanged."""
        from bob3.schema_constrained_emitter import emit_with_schema
        spec = _valid_spec()
        result = emit_with_schema(spec)
        assert isinstance(result, dict)
        assert result is spec

    def test_minimal_valid_spec_accepted(self):
        """Spec with all required fields as empty lists is accepted."""
        from bob3.schema_constrained_emitter import emit_with_schema
        spec = _minimal_valid_spec()
        result = emit_with_schema(spec)
        assert result is spec

    def test_returns_dict(self):
        """Return type is dict."""
        from bob3.schema_constrained_emitter import emit_with_schema
        result = emit_with_schema(_valid_spec())
        assert isinstance(result, dict)

    def test_additional_properties_allowed(self):
        """Extra keys are allowed by the schema (additionalProperties: true)."""
        from bob3.schema_constrained_emitter import emit_with_schema
        spec = _minimal_valid_spec()
        spec["extra_field"] = "allowed"
        result = emit_with_schema(spec)
        assert result["extra_field"] == "allowed"


class TestEmitWithSchemaInvalid:
    def test_empty_dict_raises_value_error(self):
        """Empty dict is missing all required fields — raises ValueError."""
        from bob3.schema_constrained_emitter import emit_with_schema
        with pytest.raises(ValueError):
            emit_with_schema({})

    def test_missing_required_field_raises(self):
        """Dict missing 'risks' raises ValueError."""
        from bob3.schema_constrained_emitter import emit_with_schema
        bad_spec = {k: v for k, v in _minimal_valid_spec().items() if k != "risks"}
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_wrong_type_for_array_field_raises(self):
        """String instead of list for acceptance_criteria raises ValueError."""
        from bob3.schema_constrained_emitter import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["acceptance_criteria"] = "not a list"
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_ac_missing_required_subfield_raises(self):
        """AC item missing required fields raises ValueError."""
        from bob3.schema_constrained_emitter import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["acceptance_criteria"] = [{"id": "AC-001"}]
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_never_silently_succeeds_on_invalid(self):
        """emit_with_schema must never return normally when spec is invalid."""
        from bob3.schema_constrained_emitter import emit_with_schema
        raised = False
        try:
            emit_with_schema({})
        except ValueError:
            raised = True
        assert raised, "emit_with_schema must raise on invalid spec"

    def test_custom_schema_path_respected(self):
        """schema_path kwarg is forwarded to underlying validation."""
        from bob3.schema_constrained_emitter import emit_with_schema
        schema_path = Path(__file__).parent.parent / "schemas" / "spec.v1.json"
        spec = _valid_spec()
        result = emit_with_schema(spec, schema_path=schema_path)
        assert result is spec


class TestIntegrationWithSpecCritic:
    def test_spec_critic_importable(self):
        """bob3.spec_critic must be importable alongside schema_constrained_emitter."""
        import bob3.spec_critic  # noqa: F401
        import bob3.schema_constrained_emitter  # noqa: F401

    def test_emit_with_schema_output_can_feed_spec_critic(self):
        """Validated spec can be passed to spec_critic critique_spec without type errors."""
        from bob3.schema_constrained_emitter import emit_with_schema

        spec = _valid_spec()
        validated = emit_with_schema(spec)
        # Just verifying we get a dict back that could feed a critic; not calling the LLM
        assert isinstance(validated, dict)
        assert "acceptance_criteria" in validated
        assert "functional_requirements" in validated
