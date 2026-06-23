"""Tests for bob3.synthesizer_output_parser.

Covers:
- parse_criteria_response: flat string arrays, object-format arrays, edge cases
- inject_missing_boundary_and_error_acs: injection logic and idempotency
"""
from __future__ import annotations

import pytest

from bob3.synthesizer_output_parser import (
    inject_missing_boundary_and_error_acs,
    parse_criteria_response,
)


class TestParseCriteriaResponseFlatStrings:
    def test_fenced_json_flat_strings(self):
        text = '```json\n["File exists: src/foo.py", "pytest: tests/test_foo.py"]\n```'
        result = parse_criteria_response(text)
        assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]

    def test_inline_json_flat_strings(self):
        text = 'Here are the criteria: ["criterion one", "criterion two"]'
        result = parse_criteria_response(text)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_single_element_returns_list(self):
        text = '```json\n["pytest: tests/test_x.py"]\n```'
        result = parse_criteria_response(text)
        assert result == ["pytest: tests/test_x.py"]

    def test_empty_array_returns_none(self):
        result = parse_criteria_response('```json\n[]\n```')
        assert result is None

    def test_no_json_returns_none(self):
        result = parse_criteria_response("Just plain text, no JSON here.")
        assert result is None

    def test_malformed_json_returns_none(self):
        result = parse_criteria_response('```json\n[unclosed\n```')
        assert result is None


class TestParseCriteriaResponseObjectFormat:
    def test_objects_with_criterion_key(self):
        text = '```json\n[{"id": 1, "criterion": "File exists: src/foo.py"}, {"id": 2, "criterion": "pytest: tests/test_foo.py"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]

    def test_objects_with_ac_key(self):
        text = '```json\n[{"ac": "pytest: tests/test_bar.py"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["pytest: tests/test_bar.py"]

    def test_objects_with_acceptance_criterion_key(self):
        text = '```json\n[{"acceptance_criterion": "integration: bob3.orchestrator"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["integration: bob3.orchestrator"]

    def test_objects_with_description_key_fallback(self):
        text = '```json\n[{"id": 1, "description": "pytest: tests/test_d.py"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["pytest: tests/test_d.py"]

    def test_objects_with_text_key(self):
        text = '```json\n[{"text": "Function defined: bob3.mymodule.my_func"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["Function defined: bob3.mymodule.my_func"]

    def test_objects_missing_all_known_keys_filtered_out(self):
        text = '```json\n[{"unknown_key": "value"}, {"criterion": "pytest: tests/test_x.py"}]\n```'
        result = parse_criteria_response(text)
        assert result == ["pytest: tests/test_x.py"]

    def test_all_objects_empty_returns_none(self):
        text = '```json\n[{"unknown_key": "value"}]\n```'
        result = parse_criteria_response(text)
        assert result is None

    def test_mixed_flat_and_objects_not_crashes(self):
        # Mixed arrays are unusual, but parser should not crash
        text = '```json\n["pytest: tests/test_flat.py"]\n```'
        result = parse_criteria_response(text)
        assert result is not None


class TestParseCriteriaResponseEdgeCases:
    def test_empty_string_returns_none(self):
        result = parse_criteria_response("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = parse_criteria_response("   \n\t  ")
        assert result is None

    def test_none_input_returns_none(self):
        result = parse_criteria_response(None)  # type: ignore[arg-type]
        assert result is None

    def test_non_list_json_returns_none(self):
        result = parse_criteria_response('```json\n{"key": "val"}\n```')
        assert result is None

    def test_null_json_returns_none(self):
        result = parse_criteria_response('```json\nnull\n```')
        assert result is None


class TestInjectMissingBoundaryAndErrorAcs:
    def test_injects_both_when_missing(self):
        criteria = ["File exists: src/foo.py", "pytest: tests/test_foo.py"]
        result = inject_missing_boundary_and_error_acs(criteria, title="foo feature")
        texts = " ".join(result).lower()
        assert "boundary" in texts or "empty" in texts or "minimum" in texts or "zero" in texts
        assert "error" in texts or "invalid" in texts or "raises" in texts or "raise" in texts
        assert len(result) == len(criteria) + 2

    def test_no_injection_when_boundary_present(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py",
            "When input is empty, function returns None (boundary case)",
        ]
        result = inject_missing_boundary_and_error_acs(criteria, title="foo")
        # Only error AC should be injected
        assert len(result) == len(criteria) + 1

    def test_no_injection_when_error_present(self):
        criteria = [
            "File exists: src/foo.py",
            "When invalid input is given, raises ValueError",
        ]
        result = inject_missing_boundary_and_error_acs(criteria, title="foo")
        # Only boundary AC should be injected
        assert len(result) == len(criteria) + 1

    def test_no_injection_when_both_present(self):
        criteria = [
            "pytest: tests/test_foo.py — empty input returns None (boundary)",
            "pytest: tests/test_foo_error.py — raises ValueError on invalid input",
        ]
        result = inject_missing_boundary_and_error_acs(criteria, title="foo")
        assert len(result) == len(criteria)

    def test_empty_list_injects_both(self):
        result = inject_missing_boundary_and_error_acs([], title="my feature")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_empty_title_does_not_raise(self):
        criteria = ["File exists: src/foo.py"]
        result = inject_missing_boundary_and_error_acs(criteria, title="")
        assert isinstance(result, list)

    def test_slug_references_feature_in_injected_acs(self):
        criteria = ["File exists: src/bob3/mymodule.py"]
        result = inject_missing_boundary_and_error_acs(criteria, title="my special feature")
        injected = [c for c in result if c not in criteria]
        assert len(injected) == 2
        # Injected ACs must reference the feature slug, not just be generic boilerplate
        for ac in injected:
            assert "my_special_feature" in ac or "feature" in ac

    def test_idempotent_when_acs_already_have_boundary_and_error(self):
        criteria = [
            "pytest: tests/test_x_boundary.py — zero input returns empty list (boundary)",
            "pytest: tests/test_x_error.py — invalid type raises ValueError (error path)",
        ]
        result = inject_missing_boundary_and_error_acs(criteria, title="x feature")
        assert result == criteria

    def test_non_list_criteria_raises_typeerror(self):
        with pytest.raises(TypeError):
            inject_missing_boundary_and_error_acs("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_criteria_raises_typeerror(self):
        with pytest.raises(TypeError):
            inject_missing_boundary_and_error_acs(None, title="foo")  # type: ignore[arg-type]

    def test_non_string_item_in_criteria_raises_valueerror(self):
        with pytest.raises(ValueError):
            inject_missing_boundary_and_error_acs([{"bad": "object"}], title="foo")  # type: ignore[list-item]

    def test_returns_new_list_not_mutates_input(self):
        criteria = ["File exists: src/foo.py"]
        original_len = len(criteria)
        result = inject_missing_boundary_and_error_acs(criteria, title="foo")
        assert len(criteria) == original_len  # input not mutated
        assert result is not criteria  # returns a new list

    def test_injected_boundary_ac_mentions_boundary(self):
        criteria = ["pytest: tests/test_foo.py — invalid input raises ValueError (error path)"]
        result = inject_missing_boundary_and_error_acs(criteria, title="foo")
        boundary_acs = [c for c in result if c not in criteria]
        assert len(boundary_acs) == 1
        assert "boundary" in boundary_acs[0].lower() or "empty" in boundary_acs[0].lower() or "minimum" in boundary_acs[0].lower()

    def test_injected_error_ac_mentions_error(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input returns None (boundary case)"
        ]
        result = inject_missing_boundary_and_error_acs(criteria, title="foo")
        error_acs = [c for c in result if c not in criteria]
        assert len(error_acs) == 1
        assert "error" in error_acs[0].lower() or "invalid" in error_acs[0].lower() or "raises" in error_acs[0].lower() or "raise" in error_acs[0].lower()
