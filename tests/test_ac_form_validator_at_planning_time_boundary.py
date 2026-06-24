"""Boundary tests for bob.validators.ac_form.validate_acceptance_criteria.

Tests that empty, zero, or minimum input returns a well-defined result
rather than raising (boundary case).
"""

from __future__ import annotations

import pytest

from bob.validators.ac_form import validate_acceptance_criteria


class TestBoundaryCases:
    def test_empty_list_returns_empty_list(self):
        """Zero ACs: no malformed entries → return [] (not an error)."""
        result = validate_acceptance_criteria([])
        assert result == []
        assert isinstance(result, list)

    def test_single_valid_ac_returns_empty_list(self):
        """Minimum valid input: one well-formed AC → return []."""
        result = validate_acceptance_criteria(["pytest: tests/test_foo.py"])
        assert result == []

    def test_single_valid_file_exists_ac_returns_empty_list(self):
        result = validate_acceptance_criteria(["File exists: src/something.py"])
        assert result == []

    def test_single_valid_function_defined_ac_returns_empty_list(self):
        result = validate_acceptance_criteria(["Function defined: bob.module.func"])
        assert result == []

    def test_single_valid_integration_ac_returns_empty_list(self):
        result = validate_acceptance_criteria(["integration: bob.spawn"])
        assert result == []

    def test_return_type_is_always_list(self):
        """validate_acceptance_criteria always returns a list, never None."""
        result = validate_acceptance_criteria([])
        assert result is not None
        assert isinstance(result, list)

    def test_single_malformed_ac_raises_not_returns_empty(self):
        """Even with one malformed AC, the function raises ValueError — not returns []."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["this is malformed"])

    def test_ac_with_leading_whitespace_passes_if_otherwise_valid(self):
        """Leading whitespace should be stripped before validation."""
        result = validate_acceptance_criteria(["  pytest: tests/test_foo.py"])
        assert result == []

    def test_ac_with_trailing_whitespace_passes_if_otherwise_valid(self):
        """Trailing whitespace should be stripped before validation."""
        result = validate_acceptance_criteria(["pytest: tests/test_foo.py  "])
        assert result == []

    def test_very_long_valid_path_passes(self):
        """Long but valid paths should not trip any length-based rejection."""
        long_path = "a" * 200 + ".py"
        result = validate_acceptance_criteria([f"File exists: src/{long_path}"])
        assert result == []
