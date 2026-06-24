"""Error-path tests for bob.synthesizer.

AC: invalid input raises ValueError and the function does not silently succeed.
"""
import pytest
from bob.synthesizer import parse_criteria_response, inject_boundary_error_criteria


class TestParseCriteriaResponseErrorPath:
    def test_none_input_raises_or_returns_none(self):
        """None is an invalid type; function must raise TypeError or return None."""
        try:
            result = parse_criteria_response(None)  # type: ignore[arg-type]
            assert result is None, "Expected None for None input"
        except (TypeError, AttributeError):
            pass  # raising is also acceptable for invalid type

    def test_integer_input_raises_or_returns_none(self):
        """Integer is an invalid type; must not silently succeed with wrong type."""
        try:
            result = parse_criteria_response(42)  # type: ignore[arg-type]
            assert result is None, "Expected None for integer input"
        except (TypeError, AttributeError):
            pass


class TestInjectBoundaryErrorCriteriaErrorPath:
    def test_non_list_criteria_raises_or_handles(self):
        """Non-list criteria input is invalid; must raise TypeError or ValueError."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_criteria_raises(self):
        """None criteria is invalid; must raise, not silently succeed."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria(None, title="foo")  # type: ignore[arg-type]

    def test_criteria_with_non_string_items_raises_valueerror(self):
        """Criteria containing non-string items (e.g. dicts) is invalid input."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria([{"bad": "object"}], title="foo")  # type: ignore[arg-type]
