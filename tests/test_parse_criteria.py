"""Tests for synthesizer.parse_criteria module.

Verifies parse_criteria_response (object + flat string parsing) and
inject_missing_boundary_error_acs (boundary/error coverage guarantee).
"""
import pytest
from synthesizer.parse_criteria import (
    parse_criteria_response,
    inject_missing_boundary_error_acs,
    extract_criteria_from_response,
    inject_boundary_error_criteria,
)


class TestParseCriteriaResponse:
    def test_flat_string_array_fenced(self):
        response = '```json\n["pytest: tests/test_foo.py", "File exists: src/foo.py"]\n```'
        result = parse_criteria_response(response)
        assert result == ["pytest: tests/test_foo.py", "File exists: src/foo.py"]

    def test_flat_string_bare_inline(self):
        response = 'Some text. ["pytest: tests/test_foo.py"] more text.'
        result = parse_criteria_response(response)
        assert result == ["pytest: tests/test_foo.py"]

    def test_object_criterion_key(self):
        response = '```json\n[{"id": 1, "criterion": "pytest: tests/test_x.py"}]\n```'
        result = parse_criteria_response(response)
        assert result == ["pytest: tests/test_x.py"]

    def test_object_ac_key(self):
        response = '```json\n[{"ac": "File exists: src/module.py"}]\n```'
        result = parse_criteria_response(response)
        assert result == ["File exists: src/module.py"]

    def test_object_acceptance_criterion_key(self):
        response = '```json\n[{"acceptance_criterion": "Function defined: module.func"}]\n```'
        result = parse_criteria_response(response)
        assert result == ["Function defined: module.func"]

    def test_object_text_key(self):
        response = '```json\n[{"text": "File exists: src/x.py"}]\n```'
        result = parse_criteria_response(response)
        assert result == ["File exists: src/x.py"]

    def test_object_description_key(self):
        response = '```json\n[{"description": "File exists: src/desc.py"}]\n```'
        result = parse_criteria_response(response)
        assert result == ["File exists: src/desc.py"]

    def test_mixed_objects_and_strings(self):
        response = '```json\n[{"criterion": "File exists: src/a.py"}, "pytest: tests/test_b.py"]\n```'
        result = parse_criteria_response(response)
        assert result is not None
        assert "File exists: src/a.py" in result
        assert "pytest: tests/test_b.py" in result
        assert len(result) == 2

    def test_empty_string_returns_none(self):
        assert parse_criteria_response("") is None

    def test_no_json_returns_none(self):
        assert parse_criteria_response("no json here") is None

    def test_empty_array_returns_none(self):
        assert parse_criteria_response('```json\n[]\n```') is None

    def test_null_json_returns_none(self):
        assert parse_criteria_response('```json\nnull\n```') is None

    def test_malformed_json_returns_none(self):
        assert parse_criteria_response('```json\n[not valid json\n```') is None

    def test_non_string_input_returns_none(self):
        assert parse_criteria_response(None) is None  # type: ignore[arg-type]

    def test_integer_input_returns_none(self):
        assert parse_criteria_response(42) is None  # type: ignore[arg-type]

    def test_objects_without_known_keys_dropped(self):
        response = '```json\n[{"unknown_key": "pytest: tests/x.py"}, "File exists: src/y.py"]\n```'
        result = parse_criteria_response(response)
        assert result == ["File exists: src/y.py"]

    def test_whitespace_stripped_from_strings(self):
        result = parse_criteria_response('```json\n["  File exists: src/foo.py  "]\n```')
        assert result == ["File exists: src/foo.py"]

    def test_empty_strings_are_dropped(self):
        result = parse_criteria_response('```json\n["", "File exists: src/foo.py", ""]\n```')
        assert result == ["File exists: src/foo.py"]


class TestInjectMissingBoundaryErrorAcs:
    def test_structural_only_gets_both_injected(self):
        criteria = [
            "File exists: src/foo.py",
            "Function defined: foo.bar",
            "pytest: tests/test_foo.py",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="my feature")
        lower = [c.lower() for c in result]
        has_boundary = any(
            any(tok in c for tok in ("empty", "zero", "minimum", "boundary", "limit"))
            for c in lower
        )
        has_error = any(
            any(tok in c for tok in ("error", "invalid", "fail", "raise", "does not", "must not"))
            for c in lower
        )
        assert has_boundary
        assert has_error

    def test_boundary_present_only_error_injected(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo_boundary.py — empty input returns defined result (boundary)",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        lower = [c.lower() for c in result]
        has_error = any(
            any(tok in c for tok in ("error", "invalid", "fail", "raise", "does not"))
            for c in lower
        )
        assert has_error
        assert len(result) == len(criteria) + 1

    def test_error_present_only_boundary_injected(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError (error path)",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        lower = [c.lower() for c in result]
        has_boundary = any(
            any(tok in c for tok in ("empty", "zero", "minimum", "boundary", "limit"))
            for c in lower
        )
        assert has_boundary
        assert len(result) == len(criteria) + 1

    def test_both_present_no_injection(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input returns a defined result",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        assert len(result) == len(criteria)

    def test_empty_criteria_gets_both_injected(self):
        result = inject_missing_boundary_error_acs([], title="some feature")
        assert len(result) == 2
        lower = [c.lower() for c in result]
        has_boundary = any("empty" in c or "minimum" in c or "boundary" in c for c in lower)
        has_error = any("error" in c or "invalid" in c or "fail" in c for c in lower)
        assert has_boundary
        assert has_error

    def test_injected_acs_use_pytest_prefix(self):
        result = inject_missing_boundary_error_acs(["File exists: src/foo.py"], title="foo feature")
        injected = result[1:]
        for ac in injected:
            assert ac.startswith("pytest:")

    def test_injected_acs_reference_feature_slug(self):
        result = inject_missing_boundary_error_acs(
            ["File exists: src/foo.py"], title="my cool feature"
        )
        injected = result[1:]
        for ac in injected:
            assert "feature" not in ac.lower() or "my_cool" in ac.lower()

    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            inject_missing_boundary_error_acs("not a list")  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            inject_missing_boundary_error_acs(None)  # type: ignore[arg-type]

    def test_non_string_items_raises_value_error(self):
        with pytest.raises(ValueError):
            inject_missing_boundary_error_acs([{"bad": "object"}])  # type: ignore[arg-type]


class TestAliases:
    def test_extract_criteria_from_response_alias(self):
        """extract_criteria_from_response must be an alias for parse_criteria_response."""
        response = '```json\n["File exists: src/foo.py"]\n```'
        assert extract_criteria_from_response(response) == parse_criteria_response(response)

    def test_inject_boundary_error_criteria_alias(self):
        """inject_boundary_error_criteria must be an alias for inject_missing_boundary_error_acs."""
        criteria = ["File exists: src/foo.py"]
        assert inject_boundary_error_criteria(criteria, title="foo") == inject_missing_boundary_error_acs(criteria, title="foo")
