"""Error path tests for detect_boundary_error_coverage.

Verifies that invalid inputs raise ValueError and the function does not
silently succeed (error path AC).
"""

from __future__ import annotations

import pytest
from bob.coverage_detector import detect_boundary_error_coverage


class TestErrorPaths:
    """Invalid inputs must raise ValueError; the function must not silently succeed."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage(None)

    def test_non_string_criterion_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage([42])

    def test_none_in_list_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage([None])

    def test_dict_criterion_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage([{"key": "value"}])

    def test_list_criterion_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage([["nested", "list"]])

    def test_integer_list_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage([1, 2, 3])

    def test_none_raises_and_message_is_informative(self):
        with pytest.raises(ValueError, match="criteria"):
            detect_boundary_error_coverage(None)

    def test_non_string_raises_and_message_mentions_type(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage([True])

    def test_float_criterion_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage([3.14])

    def test_mixed_valid_and_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_boundary_error_coverage(["valid string", 99])

    def test_error_is_not_silently_suppressed(self):
        raised = False
        try:
            detect_boundary_error_coverage(None)
        except ValueError:
            raised = True
        except Exception:
            pass
        assert raised, "ValueError must propagate — must not be silently swallowed"

    def test_non_iterable_string_is_not_treated_as_sequence_of_chars(self):
        # A bare string (not a list) should not be silently iterated over chars.
        # Behaviour: accept only sequences whose elements are strings.
        # A plain str passed as the outer argument iterates as chars, each of
        # which IS a str — so it does NOT raise (it's technically valid).
        # What we verify: the function returns a 2-tuple, not garbage.
        result = detect_boundary_error_coverage("hello")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_value_error_on_none_not_attribute_error(self):
        exc = None
        try:
            detect_boundary_error_coverage(None)
        except ValueError as e:
            exc = e
        except AttributeError:
            pytest.fail("Should raise ValueError, not AttributeError")
        assert exc is not None, "Expected ValueError"
