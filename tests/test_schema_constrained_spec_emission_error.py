"""Error-path tests for spec_synthesis.constrained_emit.emit_with_schema.

AC: invalid input raises ValueError and the function does not silently succeed.
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


class TestErrorPaths:
    def test_empty_dict_raises_value_error(self):
        """An empty dict is missing all required fields — must raise ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        with pytest.raises(ValueError):
            emit_with_schema({})

    def test_none_value_for_required_field_raises(self):
        """Spec with None for a required array field raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["functional_requirements"] = None
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_string_instead_of_list_raises(self):
        """acceptance_criteria must be an array; string raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["acceptance_criteria"] = "not a list"
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_int_instead_of_list_raises(self):
        """risks must be an array; int raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["risks"] = 42
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_missing_functional_requirements_raises(self):
        """Missing 'functional_requirements' key raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "out_of_scope": [],
            "risks": [],
        }
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_missing_acceptance_criteria_raises(self):
        """Missing 'acceptance_criteria' key raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {
            "functional_requirements": [],
            "non_functional_requirements": [],
            "out_of_scope": [],
            "risks": [],
        }
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_missing_out_of_scope_raises(self):
        """Missing 'out_of_scope' key raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {
            "functional_requirements": [],
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "risks": [],
        }
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_missing_risks_raises(self):
        """Missing 'risks' key raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {
            "functional_requirements": [],
            "non_functional_requirements": [],
            "acceptance_criteria": [],
            "out_of_scope": [],
        }
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_ac_missing_required_subfield_raises(self):
        """AC item missing 'given' (required) raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["acceptance_criteria"] = [
            {
                "id": "AC-001",
                # missing: given, when, then, verifier
            }
        ]
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_fr_missing_description_raises(self):
        """FR item missing 'description' (required) raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["functional_requirements"] = [{"id": "FR-001"}]
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_nfr_invalid_category_raises(self):
        """NFR item with category not in enum raises ValueError."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["non_functional_requirements"] = [
            {"id": "NFR-001", "category": "invalid_cat", "description": "Desc"}
        ]
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_does_not_silently_succeed_on_invalid(self):
        """Function must never return normally when spec is invalid."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {"wrong": "completely wrong structure"}
        result = None
        raised = False
        try:
            result = emit_with_schema(bad_spec)
        except ValueError:
            raised = True
        assert raised, "emit_with_schema must raise, not silently return on invalid spec"
        assert result is None, "No return value should be produced for invalid spec"

    def test_raises_value_error_not_generic_exception(self):
        """The raised exception must be a ValueError (or subclass)."""
        from spec_synthesis.constrained_emit import emit_with_schema
        with pytest.raises(ValueError):
            emit_with_schema({})

    def test_out_of_scope_item_not_string_raises(self):
        """out_of_scope items must be strings; dict item should raise."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["out_of_scope"] = [{"not": "a string"}]
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)
