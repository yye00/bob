"""Error-path tests for spec_linter.linter.lint_acceptance_criteria.

Each test verifies that invalid input raises ValueError and the function
does not silently succeed (return a value when it should raise).
"""

from __future__ import annotations

import pytest

from spec_linter.linter import lint_acceptance_criteria


class TestErrorPaths:
    def test_none_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria("F", None)

    def test_string_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria("F", "File exists: src/foo.py")

    def test_integer_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria("F", 42)

    def test_dict_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria("F", {"key": "value"})

    def test_none_feature_name_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria(None, ["File exists: src/foo.py"])

    def test_int_feature_name_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria(123, ["File exists: src/foo.py"])

    def test_raises_not_returns_none_on_bad_input(self):
        try:
            result = lint_acceptance_criteria("F", None)
            assert False, f"Should have raised ValueError, got {result!r}"
        except ValueError:
            pass

    def test_error_message_mentions_type_on_bad_ac(self):
        with pytest.raises(ValueError, match="list"):
            lint_acceptance_criteria("F", "bad input")

    def test_tuple_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria("F", ("File exists: src/foo.py",))

    def test_set_acceptance_criteria_raises_value_error(self):
        with pytest.raises(ValueError):
            lint_acceptance_criteria("F", {"File exists: src/foo.py"})
