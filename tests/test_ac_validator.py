"""Tests for bob3.ac_validator.validate_acceptance_criteria.

Verifies the public API at bob3.ac_validator is reachable and behaves
identically to the underlying bob3.validators.ac_form implementation.
"""

from __future__ import annotations

import pytest

from bob3.ac_validator import validate_acceptance_criteria, MalformedACError


class TestPublicAPIReachable:
    def test_module_exposes_validate_acceptance_criteria(self):
        assert callable(validate_acceptance_criteria)

    def test_module_exposes_malformed_ac_error(self):
        assert MalformedACError is ValueError


class TestValidCriteria:
    def test_empty_list_returns_empty(self):
        assert validate_acceptance_criteria([]) == []

    def test_pytest_ac_passes(self):
        assert validate_acceptance_criteria(["pytest: tests/test_foo.py"]) == []

    def test_file_exists_ac_passes(self):
        assert validate_acceptance_criteria(["File exists: src/bob3/ac_validator.py"]) == []

    def test_function_defined_ac_passes(self):
        assert validate_acceptance_criteria(
            ["Function defined: bob3.ac_validator.validate_acceptance_criteria"]
        ) == []

    def test_integration_ac_passes(self):
        assert validate_acceptance_criteria(["integration: bob3.plan_reviewer"]) == []

    def test_class_defined_ac_passes(self):
        assert validate_acceptance_criteria(["Class defined: bob3.validators.ac_form.MalformedACError"]) == []

    def test_behavior_ears_ac_passes(self):
        assert validate_acceptance_criteria(
            ["behavior: system rejects malformed AC when validator runs at planning time"]
        ) == []

    def test_multiple_valid_acs_pass(self):
        acs = [
            "File exists: src/bob3/ac_validator.py",
            "Function defined: bob3.ac_validator.validate_acceptance_criteria",
            "pytest: tests/test_ac_validator.py",
            "integration: bob3.plan_reviewer",
        ]
        assert validate_acceptance_criteria(acs) == []


class TestMalformedCriteria:
    def test_prose_ac_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["The feature must work correctly"])

    def test_v13_pytest_trailing_prose_raises(self):
        bad = "pytest: tests/test_foo.py — boundary case validation"
        with pytest.raises(ValueError):
            validate_acceptance_criteria([bad])

    def test_v13_function_defined_parens_raises(self):
        bad = "Function defined: bob3.module.fn (validates input)"
        with pytest.raises(ValueError):
            validate_acceptance_criteria([bad])

    def test_v13_pytest_scoper_parens_raises(self):
        bad = "pytest: tests/test_scoper.py (module seed validation)"
        with pytest.raises(ValueError):
            validate_acceptance_criteria([bad])

    def test_error_message_names_malformed_ac(self):
        bad = "completely unstructured prose text"
        with pytest.raises(ValueError) as exc_info:
            validate_acceptance_criteria([bad])
        assert bad in str(exc_info.value) or "malformed" in str(exc_info.value).lower()

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria([""])
