"""Boundary-case tests for bob.synthesizer.

AC: empty, zero, or minimum input returns a well-defined result rather than raising.
"""
import pytest
from bob_legacy.synthesizer import parse_criteria_response, inject_boundary_error_criteria


class TestParseCriteriaResponseBoundary:
    def test_empty_string_returns_none(self):
        """Empty string is boundary: must return None, not raise."""
        result = parse_criteria_response("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only string is boundary: must return None, not raise."""
        result = parse_criteria_response("   \n\t  ")
        assert result is None

    def test_empty_json_array_returns_none(self):
        """Zero-element array is boundary: must return None, not raise."""
        result = parse_criteria_response('```json\n[]\n```')
        assert result is None

    def test_single_element_array_returns_list(self):
        """Minimum non-empty array (1 element): must return a list."""
        result = parse_criteria_response('```json\n["pytest: tests/test_x.py"]\n```')
        assert isinstance(result, list)
        assert len(result) == 1

    def test_single_object_with_criterion_key(self):
        """Minimum object-format (1 element): must return a list, not raise."""
        result = parse_criteria_response('```json\n[{"criterion": "pytest: tests/test_x.py"}]\n```')
        assert isinstance(result, list)
        assert len(result) == 1

    def test_null_json_response_returns_none(self):
        """JSON null is boundary: must return None, not raise."""
        result = parse_criteria_response('```json\nnull\n```')
        assert result is None


class TestInjectBoundaryErrorCriteriaBoundary:
    def test_empty_list_returns_list_not_raises(self):
        """Empty list is boundary: function must return a list (not raise)."""
        result = inject_boundary_error_criteria([], title="some feature")
        assert isinstance(result, list)

    def test_empty_title_does_not_raise(self):
        """Empty title is boundary: must return a list, not raise."""
        criteria = ["File exists: src/foo.py"]
        result = inject_boundary_error_criteria(criteria, title="")
        assert isinstance(result, list)

    def test_single_element_criteria(self):
        """Minimum non-empty criteria (1 element): must return a list."""
        criteria = ["pytest: tests/test_foo.py"]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_criteria_with_whitespace_only_strings(self):
        """Criteria containing blank strings: function must handle gracefully."""
        criteria = ["", "  ", "pytest: tests/test_foo.py"]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert isinstance(result, list)
