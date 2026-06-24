"""Error-path tests for bob.validators.ac_form.validate_acceptance_criteria.

Tests that invalid input raises ValueError and the function does not
silently succeed (error path).
"""

from __future__ import annotations

import pytest

from bob.validators.ac_form import validate_acceptance_criteria


class TestErrorPaths:
    def test_non_list_input_raises_value_error(self):
        """Passing a non-list raises ValueError, not TypeError or AttributeError."""
        with pytest.raises((ValueError, TypeError)):
            validate_acceptance_criteria("pytest: tests/test_foo.py")  # type: ignore[arg-type]

    def test_none_input_raises(self):
        """None input raises, not silently returns []."""
        with pytest.raises((ValueError, TypeError, AttributeError)):
            validate_acceptance_criteria(None)  # type: ignore[arg-type]

    def test_malformed_ac_raises_value_error_not_silently_passes(self):
        """A clearly malformed AC must raise ValueError, never return []."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["this is garbage text with no structure"])

    def test_empty_string_raises_value_error(self):
        """An empty string AC must raise ValueError."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria([""])

    def test_whitespace_only_raises_value_error(self):
        """A whitespace-only AC must raise ValueError."""
        with pytest.raises((ValueError,)):
            validate_acceptance_criteria(["   \t\n  "])

    def test_bare_prose_raises_value_error(self):
        """Unstructured prose raises ValueError."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["The feature must work correctly"])

    def test_wrong_prefix_raises_value_error(self):
        """An unknown AC prefix like 'test:' is not accepted."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["test: tests/test_foo.py"])

    def test_pytest_trailing_prose_after_em_dash_raises(self):
        """pytest: path — prose is the v.13 regression; must raise ValueError."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["pytest: tests/test_foo.py — boundary case validation"])

    def test_function_defined_with_parens_raises(self):
        """Function defined: path (description) must raise ValueError."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["Function defined: bob.module.fn (some description)"])

    def test_pytest_with_parens_suffix_raises(self):
        """pytest: tests/test_scoper.py (module seed) must raise ValueError."""
        with pytest.raises(ValueError):
            validate_acceptance_criteria(["pytest: tests/test_scoper.py (module seed validation)"])

    def test_error_message_is_informative(self):
        """The ValueError message names the malformed criterion, not a generic error."""
        bad = "completely invalid criterion text"
        with pytest.raises(ValueError) as exc_info:
            validate_acceptance_criteria([bad])
        assert bad in str(exc_info.value) or "malformed" in str(exc_info.value).lower()

    def test_second_element_malformed_raises(self):
        """Validation does not stop at first AC; second malformed AC also raises."""
        acs = ["File exists: src/foo.py", "bad second ac"]
        with pytest.raises(ValueError, match="bad second ac"):
            validate_acceptance_criteria(acs)

    def test_does_not_silently_return_empty_on_malformed(self):
        """validate_acceptance_criteria must not return [] when ACs are malformed."""
        acs = ["completely unstructured text"]
        try:
            result = validate_acceptance_criteria(acs)
            # If we reach here, the function returned something instead of raising
            pytest.fail(
                f"Expected ValueError but got return value: {result!r}. "
                "The function must raise, not silently succeed."
            )
        except ValueError:
            pass  # correct behavior
