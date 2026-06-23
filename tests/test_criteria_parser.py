"""Tests for bob3.criteria_parser — parse_criteria_response and inject_missing_boundary_error_acs."""
import pytest
from bob3.criteria_parser import parse_criteria_response, inject_missing_boundary_error_acs


class TestParseCriteriaResponseFlatStrings:
    def test_fenced_json_flat_strings(self):
        text = '```json\n["File exists: src/foo.py", "pytest: tests/test_foo.py"]\n```'
        result = parse_criteria_response(text)
        assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]

    def test_bare_inline_json_array(self):
        text = '["pytest: tests/test_x.py"]'
        result = parse_criteria_response(text)
        assert result == ["pytest: tests/test_x.py"]

    def test_empty_string_returns_none(self):
        assert parse_criteria_response("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_criteria_response("   \n\t  ") is None

    def test_empty_json_array_returns_none(self):
        result = parse_criteria_response("```json\n[]\n```")
        assert result is None

    def test_null_json_returns_none(self):
        result = parse_criteria_response("```json\nnull\n```")
        assert result is None

    def test_non_string_input_returns_none(self):
        assert parse_criteria_response(None) is None  # type: ignore[arg-type]
        assert parse_criteria_response(42) is None    # type: ignore[arg-type]


class TestParseCriteriaResponseObjectFormat:
    def test_objects_with_criterion_key(self):
        text = '```json\n[{"id":1,"criterion":"pytest: tests/test_foo.py","description":"run tests"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["pytest: tests/test_foo.py"]

    def test_objects_with_ac_key(self):
        text = '```json\n[{"ac": "File exists: src/bar.py"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["File exists: src/bar.py"]

    def test_objects_with_acceptance_criterion_key(self):
        text = '```json\n[{"acceptance_criterion": "Function defined: bob3.foo.bar"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["Function defined: bob3.foo.bar"]

    def test_objects_with_text_key(self):
        text = '```json\n[{"text": "integration: bob3.synthesizer"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["integration: bob3.synthesizer"]

    def test_objects_with_description_key(self):
        text = '```json\n[{"description": "pytest: tests/test_d.py"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["pytest: tests/test_d.py"]

    def test_mixed_strings_and_objects(self):
        text = '```json\n["File exists: src/x.py", {"criterion": "pytest: tests/test_x.py"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["File exists: src/x.py", "pytest: tests/test_x.py"]

    def test_single_object_min_input(self):
        text = '```json\n[{"criterion": "pytest: tests/test_x.py"}]\n```'
        result = parse_criteria_response(text)
        assert isinstance(result, list)
        assert len(result) == 1


class TestInjectMissingBoundaryErrorAcs:
    def test_injects_both_when_absent(self):
        criteria = ["File exists: src/foo.py", "pytest: tests/test_foo.py"]
        result = inject_missing_boundary_error_acs(criteria, title="my feature")
        texts = " ".join(result)
        assert any("boundary" in c.lower() for c in result)
        assert any("error" in c.lower() or "invalid" in c.lower() or "ValueError" in c for c in result)

    def test_does_not_inject_when_boundary_present(self):
        criteria = [
            "pytest: tests/test_foo.py — empty input returns None (boundary)",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        assert result == criteria

    def test_injects_only_error_when_boundary_present(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input returns None (boundary case)",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        assert len(result) == 2
        error_ac = result[-1]
        assert "error" in error_ac.lower() or "invalid" in error_ac.lower() or "ValueError" in error_ac

    def test_injects_only_boundary_when_error_present(self):
        criteria = [
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        assert len(result) == 2
        boundary_ac = result[-1]
        assert "boundary" in boundary_ac.lower() or "empty" in boundary_ac.lower() or "minimum" in boundary_ac.lower()

    def test_empty_list_returns_list_not_raises(self):
        result = inject_missing_boundary_error_acs([], title="some feature")
        assert isinstance(result, list)

    def test_empty_title_does_not_raise(self):
        criteria = ["File exists: src/foo.py"]
        result = inject_missing_boundary_error_acs(criteria, title="")
        assert isinstance(result, list)

    def test_slug_references_feature_title(self):
        criteria = ["File exists: src/foo.py"]
        result = inject_missing_boundary_error_acs(criteria, title="My Feature")
        injected = [c for c in result if "boundary" in c or "error" in c]
        assert any("my_feature" in c for c in injected)

    def test_no_duplicate_injection_when_both_present(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input (boundary case)",
            "pytest: tests/test_foo_error.py — raises ValueError (error path)",
        ]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        assert len(result) == 2

    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            inject_missing_boundary_error_acs("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            inject_missing_boundary_error_acs(None, title="foo")  # type: ignore[arg-type]

    def test_list_with_non_string_raises_value_error(self):
        with pytest.raises((TypeError, ValueError)):
            inject_missing_boundary_error_acs([{"bad": "object"}], title="foo")  # type: ignore[arg-type]

    def test_criteria_with_whitespace_strings(self):
        criteria = ["", "  ", "pytest: tests/test_foo.py"]
        result = inject_missing_boundary_error_acs(criteria, title="foo")
        assert isinstance(result, list)

    def test_injected_acs_are_pytest_structured(self):
        criteria = ["File exists: src/foo.py"]
        result = inject_missing_boundary_error_acs(criteria, title="foo feature")
        injected = [c for c in result if c not in criteria]
        for ac in injected:
            assert ac.startswith("pytest:"), f"Expected pytest: prefix, got: {ac!r}"


class TestIntegrationWithSynthesizer:
    def test_parse_then_inject_pipeline(self):
        """Simulate the full synthesizer pipeline: parse → inject."""
        raw = '```json\n[{"criterion":"File exists: src/foo.py"},{"criterion":"pytest: tests/test_foo.py"}]\n```'
        parsed = parse_criteria_response(raw)
        assert parsed is not None
        result = inject_missing_boundary_error_acs(parsed, title="foo feature")
        assert len(result) >= 4  # 2 parsed + 2 injected
        assert any("boundary" in c for c in result)
        assert any("error" in c or "invalid" in c for c in result)
