"""Tests for bob3.synthesizer_parse_fix.

Covers parse_criteria_response (object-format LLM output parsing) and
inject_boundary_error_acs (deterministic boundary + error-path AC injection).
"""
import pytest
from bob3.synthesizer_parse_fix import (
    inject_boundary_error_acs,
    parse_criteria_response,
)


class TestParseCriteriaResponseFlatStrings:
    def test_flat_string_array_in_fenced_block(self):
        raw = '```json\n["pytest: tests/test_x.py", "File exists: src/foo.py"]\n```'
        result = parse_criteria_response(raw)
        assert result == ["pytest: tests/test_x.py", "File exists: src/foo.py"]

    def test_flat_string_array_no_fence(self):
        raw = '["pytest: tests/test_x.py"]'
        result = parse_criteria_response(raw)
        assert isinstance(result, list)
        assert "pytest: tests/test_x.py" in result

    def test_empty_string_returns_none(self):
        assert parse_criteria_response("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_criteria_response("   \n  ") is None

    def test_empty_array_returns_none(self):
        assert parse_criteria_response("```json\n[]\n```") is None

    def test_null_json_returns_none(self):
        assert parse_criteria_response("```json\nnull\n```") is None

    def test_invalid_json_returns_none(self):
        assert parse_criteria_response("```json\n{bad json\n```") is None


class TestParseCriteriaResponseObjectFormat:
    def test_object_with_criterion_key(self):
        raw = '```json\n[{"criterion": "pytest: tests/test_x.py", "description": "runs x"}]\n```'
        result = parse_criteria_response(raw)
        assert result == ["pytest: tests/test_x.py"]

    def test_object_with_ac_key(self):
        raw = '```json\n[{"ac": "File exists: src/foo.py"}]\n```'
        result = parse_criteria_response(raw)
        assert result == ["File exists: src/foo.py"]

    def test_object_with_acceptance_criterion_key(self):
        raw = '```json\n[{"acceptance_criterion": "Function defined: bob3.foo.bar"}]\n```'
        result = parse_criteria_response(raw)
        assert result == ["Function defined: bob3.foo.bar"]

    def test_object_with_text_key(self):
        raw = '```json\n[{"text": "integration: bob3.synthesizer"}]\n```'
        result = parse_criteria_response(raw)
        assert result == ["integration: bob3.synthesizer"]

    def test_object_with_description_key(self):
        raw = '```json\n[{"id": 1, "description": "pytest: tests/test_boundary.py"}]\n```'
        result = parse_criteria_response(raw)
        assert result == ["pytest: tests/test_boundary.py"]

    def test_mixed_objects_with_multiple_keys_prefers_criterion(self):
        raw = '```json\n[{"criterion": "pytest: tests/test_x.py", "description": "runs x", "id": 1}]\n```'
        result = parse_criteria_response(raw)
        assert result == ["pytest: tests/test_x.py"]

    def test_multiple_objects_returned(self):
        raw = '```json\n[{"criterion": "pytest: tests/test_a.py"}, {"criterion": "File exists: src/b.py"}]\n```'
        result = parse_criteria_response(raw)
        assert result is not None
        assert len(result) == 2
        assert "pytest: tests/test_a.py" in result
        assert "File exists: src/b.py" in result

    def test_object_without_known_keys_filtered_out(self):
        raw = '```json\n[{"unknown_key": "something"}, {"criterion": "pytest: tests/test_x.py"}]\n```'
        result = parse_criteria_response(raw)
        assert result == ["pytest: tests/test_x.py"]

    def test_all_objects_without_known_keys_returns_none(self):
        raw = '```json\n[{"unknown_key": "something"}]\n```'
        result = parse_criteria_response(raw)
        assert result is None


class TestInjectBoundaryErrorAcsInjection:
    def test_structural_only_acs_get_both_injected(self):
        criteria = ["File exists: src/foo.py", "Function defined: bob3.foo.bar"]
        result = inject_boundary_error_acs(criteria, title="foo feature")
        texts = " ".join(result)
        assert any("boundary" in c.lower() for c in result)
        assert any("error" in c.lower() or "invalid" in c.lower() for c in result)
        assert len(result) == len(criteria) + 2

    def test_existing_boundary_ac_not_duplicated(self):
        criteria = [
            "File exists: src/foo.py",
            "The function handles empty input returning None (boundary case)",
        ]
        result = inject_boundary_error_acs(criteria, title="foo feature")
        boundary_count = sum(1 for c in result if "boundary" in c.lower() or "empty" in c.lower())
        assert boundary_count >= 1
        assert any("error" in c.lower() or "invalid" in c.lower() for c in result)

    def test_existing_error_ac_not_duplicated(self):
        criteria = [
            "File exists: src/foo.py",
            "The function raises ValueError on invalid input (error path)",
        ]
        result = inject_boundary_error_acs(criteria, title="foo feature")
        assert any("boundary" in c.lower() or "empty" in c.lower() or "minimum" in c.lower() for c in result)
        error_count = sum(1 for c in result if "ValueError" in c or "invalid" in c.lower())
        assert error_count >= 1

    def test_already_has_both_types_no_injection(self):
        criteria = [
            "File exists: src/foo.py",
            "Empty list returns None (boundary case)",
            "None input raises ValueError (error path)",
        ]
        result = inject_boundary_error_acs(criteria, title="foo feature")
        assert len(result) == len(criteria)

    def test_empty_list_gets_both_injected(self):
        result = inject_boundary_error_acs([], title="my feature")
        assert len(result) == 2
        assert any("boundary" in c.lower() for c in result)
        assert any("error" in c.lower() or "invalid" in c.lower() for c in result)

    def test_injected_acs_reference_feature_slug(self):
        result = inject_boundary_error_acs([], title="synthesizer parse fix")
        for ac in result:
            assert "synthesizer_parse_fix" in ac or "feature" in ac

    def test_empty_title_uses_fallback_slug(self):
        result = inject_boundary_error_acs([], title="")
        assert all(isinstance(c, str) for c in result)
        assert len(result) == 2

    def test_returns_new_list_not_mutating(self):
        original = ["File exists: src/foo.py"]
        result = inject_boundary_error_acs(original, title="foo")
        assert result is not original
        assert len(original) == 1

    def test_injected_pytest_acs_reference_test_files(self):
        result = inject_boundary_error_acs([], title="my module")
        for ac in result:
            assert ac.startswith("pytest: tests/test_")

    def test_non_list_raises_typeerror(self):
        with pytest.raises(TypeError):
            inject_boundary_error_acs("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises_typeerror(self):
        with pytest.raises(TypeError):
            inject_boundary_error_acs(None, title="foo")  # type: ignore[arg-type]

    def test_criteria_with_non_string_items_raises_valueerror(self):
        with pytest.raises((TypeError, ValueError)):
            inject_boundary_error_acs([42], title="foo")  # type: ignore[arg-type]
