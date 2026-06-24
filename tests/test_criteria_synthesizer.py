"""Tests for bob.criteria_synthesizer.

Verifies that parse_criteria_response and inject_boundary_error_criteria
are importable from bob.criteria_synthesizer and behave correctly.
"""
from __future__ import annotations

import pytest
from bob.criteria_synthesizer import parse_criteria_response, inject_boundary_error_criteria


class TestParseCriteriaResponse:
    def test_parses_flat_string_array(self):
        result = parse_criteria_response('```json\n["pytest: tests/test_foo.py"]\n```')
        assert result == ["pytest: tests/test_foo.py"]

    def test_parses_object_array_criterion_key(self):
        """Objects with 'criterion' key must be extracted, not str(dict)."""
        payload = '```json\n[{"id":1,"criterion":"pytest: tests/test_x.py","description":"desc"}]\n```'
        result = parse_criteria_response(payload)
        assert result == ["pytest: tests/test_x.py"]

    def test_parses_object_array_ac_key(self):
        payload = '```json\n[{"ac":"File exists: src/foo.py"}]\n```'
        result = parse_criteria_response(payload)
        assert result == ["File exists: src/foo.py"]

    def test_empty_string_returns_none(self):
        assert parse_criteria_response("") is None

    def test_empty_array_returns_none(self):
        assert parse_criteria_response('```json\n[]\n```') is None

    def test_null_json_returns_none(self):
        assert parse_criteria_response('```json\nnull\n```') is None

    def test_non_string_input_returns_none(self):
        try:
            result = parse_criteria_response(None)  # type: ignore[arg-type]
            assert result is None
        except (TypeError, AttributeError):
            pass

    def test_multiple_objects_extracted(self):
        payload = (
            '```json\n'
            '[{"criterion":"File exists: src/a.py"},{"criterion":"pytest: tests/test_a.py"}]\n'
            '```'
        )
        result = parse_criteria_response(payload)
        assert result == ["File exists: src/a.py", "pytest: tests/test_a.py"]


class TestInjectBoundaryErrorCriteria:
    def test_injects_boundary_and_error_when_absent(self):
        criteria = ["File exists: src/foo.py", "pytest: tests/test_foo.py"]
        result = inject_boundary_error_criteria(criteria, title="foo feature")
        texts = " ".join(result).lower()
        assert "boundary" in texts or "empty" in texts or "minimum" in texts or "zero" in texts
        assert "error" in texts or "exception" in texts or "invalid" in texts or "valueerror" in texts

    def test_does_not_duplicate_when_boundary_already_present(self):
        criteria = [
            "File exists: src/foo.py",
            "When given an empty input, the function returns None (boundary case)",
            "pytest: tests/test_foo.py — invalid input raises ValueError (error path)",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert len(result) == len(criteria), "Should not inject when both already present"

    def test_empty_list_does_not_raise(self):
        result = inject_boundary_error_criteria([], title="feature")
        assert isinstance(result, list)

    def test_raises_type_error_for_non_list(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria("not a list", title="foo")  # type: ignore[arg-type]

    def test_raises_for_none(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria(None, title="foo")  # type: ignore[arg-type]

    def test_raises_for_list_with_dict_items(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria([{"bad": "item"}], title="foo")  # type: ignore[arg-type]

    def test_returns_list_type(self):
        result = inject_boundary_error_criteria(["pytest: tests/test_x.py"], title="x")
        assert isinstance(result, list)
