"""Boundary-case tests for spec_synthesis.constrained_emit.emit_with_schema.

AC: empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

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


class TestBoundaryCases:
    def test_empty_lists_all_required_fields(self):
        """Spec with all required fields as empty lists is valid (minimum input)."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        result = emit_with_schema(spec)
        assert isinstance(result, dict)

    def test_zero_functional_requirements(self):
        """Zero functional requirements is allowed — minItems=0 in schema."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["functional_requirements"] = []
        result = emit_with_schema(spec)
        assert result["functional_requirements"] == []

    def test_zero_acceptance_criteria(self):
        """Zero acceptance criteria is allowed."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["acceptance_criteria"] = []
        result = emit_with_schema(spec)
        assert result["acceptance_criteria"] == []

    def test_zero_risks(self):
        """Zero risks is a valid boundary value."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["risks"] = []
        result = emit_with_schema(spec)
        assert result["risks"] == []

    def test_zero_out_of_scope(self):
        """Empty out_of_scope list is valid."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["out_of_scope"] = []
        result = emit_with_schema(spec)
        assert result["out_of_scope"] == []

    def test_single_functional_requirement(self):
        """Single-item functional_requirements is valid minimum content."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["functional_requirements"] = [{"id": "FR-001", "description": "Do X"}]
        result = emit_with_schema(spec)
        assert len(result["functional_requirements"]) == 1

    def test_additional_properties_allowed(self):
        """Schema allows additionalProperties=true; extra keys should not cause rejection."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["extra_field"] = "allowed by additionalProperties: true"
        result = emit_with_schema(spec)
        assert result["extra_field"] == "allowed by additionalProperties: true"

    def test_result_is_same_object_not_copy(self):
        """emit_with_schema returns the same dict object (no unnecessary copying)."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        result = emit_with_schema(spec)
        assert result is spec

    def test_minimum_ac_all_required_fields(self):
        """An AC with all required fields (id, given, when, then, verifier) is valid."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["acceptance_criteria"] = [
            {
                "id": "AC-001",
                "given": "some context",
                "when": "action happens",
                "then": "outcome is observed",
                "verifier": "pytest tests/test_something.py",
            }
        ]
        result = emit_with_schema(spec)
        assert len(result["acceptance_criteria"]) == 1

    def test_minimum_nfr_all_required_fields(self):
        """An NFR with id, category, description is valid."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["non_functional_requirements"] = [
            {"id": "NFR-001", "category": "perf", "description": "Fast enough"}
        ]
        result = emit_with_schema(spec)
        assert len(result["non_functional_requirements"]) == 1

    def test_minimum_risk_only_description(self):
        """A risk with only 'description' (the sole required field) is valid."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        spec["risks"] = [{"description": "Some risk exists"}]
        result = emit_with_schema(spec)
        assert len(result["risks"]) == 1
