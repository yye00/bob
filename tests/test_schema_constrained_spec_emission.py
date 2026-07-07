"""Tests for bob.schema_constrained_spec_emission.

Covers the public ``emit_spec`` / ``validate_spec`` API: schema-conforming
specs pass through unchanged, malformed specs are REJECTED with a ValueError
(never silently coerced), and the module integrates with bob.synthesizer.
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


class TestEmitSpec:
    def test_valid_spec_returned_unchanged(self):
        from bob.schema_constrained_spec_emission import emit_spec
        spec = _minimal_valid_spec()
        result = emit_spec(spec)
        assert result is spec

    def test_full_spec_all_slots_populated(self):
        from bob.schema_constrained_spec_emission import emit_spec
        spec = {
            "functional_requirements": [
                {"id": "FR-001", "description": "Do X", "priority": "must"}
            ],
            "non_functional_requirements": [
                {"id": "NFR-001", "category": "perf", "description": "Fast"}
            ],
            "acceptance_criteria": [
                {
                    "id": "AC-001",
                    "given": "ctx",
                    "when": "act",
                    "then": "outcome",
                    "verifier": "pytest tests/test_x.py",
                }
            ],
            "out_of_scope": ["not this"],
            "risks": [{"description": "a risk", "severity": "low"}],
        }
        result = emit_spec(spec)
        assert result["functional_requirements"][0]["id"] == "FR-001"

    def test_malformed_spec_raises_value_error(self):
        from bob.schema_constrained_spec_emission import emit_spec
        with pytest.raises(ValueError):
            emit_spec({})

    def test_missing_required_slot_raises(self):
        from bob.schema_constrained_spec_emission import emit_spec
        bad = _minimal_valid_spec()
        del bad["risks"]
        with pytest.raises(ValueError):
            emit_spec(bad)

    def test_non_dict_input_raises_value_error(self):
        from bob.schema_constrained_spec_emission import emit_spec
        with pytest.raises(ValueError):
            emit_spec("not a dict")  # type: ignore[arg-type]

    def test_does_not_silently_coerce(self):
        from bob.schema_constrained_spec_emission import emit_spec
        bad = _minimal_valid_spec()
        bad["acceptance_criteria"] = "not a list"
        result = None
        raised = False
        try:
            result = emit_spec(bad)
        except ValueError:
            raised = True
        assert raised
        assert result is None


class TestValidateSpec:
    def test_valid_spec_returns_empty_list(self):
        from bob.schema_constrained_spec_emission import validate_spec
        assert validate_spec(_minimal_valid_spec()) == []

    def test_invalid_spec_returns_errors_without_raising(self):
        from bob.schema_constrained_spec_emission import validate_spec
        errors = validate_spec({})
        assert isinstance(errors, list)
        assert len(errors) >= 1

    def test_non_dict_returns_error_not_raise(self):
        from bob.schema_constrained_spec_emission import validate_spec
        errors = validate_spec(123)  # type: ignore[arg-type]
        assert isinstance(errors, list)
        assert len(errors) >= 1


class TestSynthesizerIntegration:
    def test_module_imports_bob_synthesizer(self):
        import bob.schema_constrained_spec_emission as mod
        import bob.synthesizer

        assert mod.bob.synthesizer is bob.synthesizer

    def test_emit_spec_is_callable(self):
        from bob.schema_constrained_spec_emission import emit_spec
        assert callable(emit_spec)


class TestEmitConstrainedSpec:
    def test_valid_spec_returned_unchanged(self):
        from bob.schema_constrained_spec_emission import emit_constrained_spec
        spec = _minimal_valid_spec()
        assert emit_constrained_spec(spec) is spec

    def test_invalid_spec_rejected_with_value_error(self):
        from bob.schema_constrained_spec_emission import emit_constrained_spec
        with pytest.raises(ValueError):
            emit_constrained_spec({})

    def test_non_dict_rejected(self):
        from bob.schema_constrained_spec_emission import emit_constrained_spec
        with pytest.raises(ValueError):
            emit_constrained_spec("nope")  # type: ignore[arg-type]


class TestRejectInvalidSpec:
    def test_valid_spec_passes_through(self):
        from bob.schema_constrained_spec_emission import reject_invalid_spec
        spec = _minimal_valid_spec()
        assert reject_invalid_spec(spec) is spec

    def test_invalid_spec_raises_and_does_not_silently_succeed(self):
        from bob.schema_constrained_spec_emission import reject_invalid_spec
        result = None
        raised = False
        try:
            result = reject_invalid_spec(_minimal_valid_spec() | {"risks": "bad"})
        except ValueError:
            raised = True
        assert raised
        assert result is None

    def test_missing_slot_raises(self):
        from bob.schema_constrained_spec_emission import reject_invalid_spec
        bad = _minimal_valid_spec()
        del bad["acceptance_criteria"]
        with pytest.raises(ValueError):
            reject_invalid_spec(bad)
