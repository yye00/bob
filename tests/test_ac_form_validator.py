"""Tests for bob3.validators.ac_form.validate_acceptance_criteria.

Verifies:
- validate_acceptance_criteria accepts all canonical AC forms (pytest:/File exists:/Function defined:/integration:)
- validate_acceptance_criteria raises ValueError for malformed ACs and lists all offenders
- validate_acceptance_criteria returns an empty list when all ACs are valid
- Trailing prose after a pytest: path is detected as malformed (v.13 regression class)
- Function-defined parenthetical descriptions are detected as malformed (v.13 regression class)
- pytest_scoper module-seed parens are detected as malformed (v.13 regression class)
- All canonical prefixes are validated: pytest:, File exists:, Function defined:, integration:, Class defined:, behavior:
"""

from __future__ import annotations

import pytest

from bob3.validators.ac_form import validate_acceptance_criteria


class TestValidAcceptanceCriteria:
    def test_empty_list_returns_empty(self):
        result = validate_acceptance_criteria([])
        assert result == []

    def test_pytest_canonical_passes(self):
        result = validate_acceptance_criteria(["pytest: tests/test_foo.py"])
        assert result == []

    def test_file_exists_canonical_passes(self):
        result = validate_acceptance_criteria(["File exists: src/bob3/validators/ac_form.py"])
        assert result == []

    def test_function_defined_canonical_passes(self):
        result = validate_acceptance_criteria(["Function defined: bob3.validators.ac_form.validate_acceptance_criteria"])
        assert result == []

    def test_integration_canonical_passes(self):
        result = validate_acceptance_criteria(["integration: bob3.spawn"])
        assert result == []

    def test_class_defined_canonical_passes(self):
        result = validate_acceptance_criteria(["Class defined: bob3.validators.ac_form.ValidationError"])
        assert result == []

    def test_behavior_ears_canonical_passes(self):
        result = validate_acceptance_criteria(["behavior: system rejects malformed AC when validator runs"])
        assert result == []

    def test_multiple_valid_acs_pass(self):
        acs = [
            "File exists: src/bob3/validators/ac_form.py",
            "Function defined: bob3.validators.ac_form.validate_acceptance_criteria",
            "pytest: tests/test_ac_form_validator.py",
            "integration: bob3.spawn",
        ]
        result = validate_acceptance_criteria(acs)
        assert result == []

    def test_pytest_with_path_containing_dashes_passes(self):
        result = validate_acceptance_criteria(["pytest: tests/test_ac-form.py"])
        assert result == []

    def test_pytest_with_double_colon_selector_passes(self):
        result = validate_acceptance_criteria(["pytest: tests/test_foo.py::TestClass::test_method"])
        assert result == []


class TestMalformedAcceptanceCriteria:
    def test_raises_value_error_on_malformed_ac(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["this is completely unstructured AC text"])

    def test_returns_offending_ac_in_error_message(self):
        bad_ac = "this is completely unstructured AC text"
        with pytest.raises(ValueError, match="malformed"):
            validate_acceptance_criteria([bad_ac])

    def test_v13_pytest_trailing_prose_raises(self):
        """v.13 regression: pytest: path followed by prose — trailing text after a space."""
        bad_ac = "pytest: tests/test_foo.py — this test verifies the feature works"
        with pytest.raises(ValueError):
            validate_acceptance_criteria([bad_ac])

    def test_v13_function_defined_with_parenthetical_raises(self):
        """v.13 regression: Function defined: module.fn (description in parens)."""
        bad_ac = "Function defined: bob3.module.fn (validates input)"
        with pytest.raises(ValueError):
            validate_acceptance_criteria([bad_ac])

    def test_v13_pytest_scoper_module_seed_parens_raises(self):
        """v.13 regression: pytest_scoper module seed with parens in path."""
        bad_ac = "pytest: tests/test_scoper.py (module seed validation)"
        with pytest.raises(ValueError):
            validate_acceptance_criteria([bad_ac])

    def test_multiple_malformed_acs_all_reported(self):
        acs = [
            "File exists: src/bob3/validators/ac_form.py",
            "this is vague and unstructured",
            "also bad criterion here",
        ]
        with pytest.raises(ValueError) as exc_info:
            validate_acceptance_criteria(acs)
        msg = str(exc_info.value)
        assert "this is vague and unstructured" in msg
        assert "also bad criterion here" in msg

    def test_empty_string_ac_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria([""])

    def test_whitespace_only_ac_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["   "])

    def test_unknown_prefix_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["unknown_prefix: some value"])

    def test_pytest_no_path_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["pytest:"])

    def test_file_exists_no_path_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["File exists:"])

    def test_function_defined_no_dotted_path_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["Function defined:"])

    def test_integration_no_module_raises(self):
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["integration:"])

    def test_mixed_valid_and_invalid_raises(self):
        """When any AC is malformed, ValueError is raised listing all malformed ones."""
        acs = [
            "pytest: tests/test_valid.py",
            "bad unstructured criterion",
        ]
        with pytest.raises(ValueError, match="bad unstructured criterion"):
            validate_acceptance_criteria(acs)

    def test_error_contains_ac_index(self):
        """Error message includes index information for locating the offender."""
        acs = [
            "File exists: src/foo.py",
            "malformed ac at index 1",
        ]
        with pytest.raises(ValueError) as exc_info:
            validate_acceptance_criteria(acs)
        msg = str(exc_info.value)
        assert "1" in msg or "malformed ac at index 1" in msg
