"""Error path tests: criterion_checker raises ValueError for invalid input.

Feature c2168748: enhanced_verification MUST recognize 'Class defined:' AC
prefix. This file verifies that invalid input raises ValueError and the
function does not silently succeed.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from bob3.enhanced_verification import criterion_checker


def _empty_workspace() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp())


class TestErrorPaths:
    def test_non_string_criterion_raises_value_error(self):
        """Non-string criterion raises ValueError."""
        with pytest.raises(ValueError, match="criterion must be a str"):
            criterion_checker(None, _empty_workspace())  # type: ignore[arg-type]

    def test_integer_criterion_raises_value_error(self):
        """Integer criterion raises ValueError."""
        with pytest.raises(ValueError, match="criterion must be a str"):
            criterion_checker(42, _empty_workspace())  # type: ignore[arg-type]

    def test_list_criterion_raises_value_error(self):
        """List criterion raises ValueError."""
        with pytest.raises(ValueError, match="criterion must be a str"):
            criterion_checker(["Class defined: Foo"], _empty_workspace())  # type: ignore[arg-type]

    def test_dict_criterion_raises_value_error(self):
        """Dict criterion raises ValueError."""
        with pytest.raises(ValueError, match="criterion must be a str"):
            criterion_checker({"criterion": "Class defined: Foo"}, _empty_workspace())  # type: ignore[arg-type]

    def test_error_message_includes_type_name(self):
        """ValueError message mentions the actual type received."""
        with pytest.raises(ValueError) as exc_info:
            criterion_checker(123, _empty_workspace())  # type: ignore[arg-type]
        assert "int" in str(exc_info.value)

    def test_valid_class_defined_does_not_raise(self):
        """Valid 'Class defined:' criterion does not raise even when class absent."""
        try:
            result = criterion_checker("Class defined: pkg.MissingClass", _empty_workspace())
        except ValueError:
            pytest.fail("criterion_checker raised ValueError for valid string criterion")
        assert result is False

    def test_function_does_not_silently_succeed_on_invalid_type(self):
        """criterion_checker must never return True for non-string input."""
        for bad_input in (None, 0, [], {}, object()):
            with pytest.raises((ValueError, TypeError)):
                criterion_checker(bad_input, _empty_workspace())  # type: ignore[arg-type]
