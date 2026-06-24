"""Tests for bob.synthesizer_boundary_error_ac_injector.

Covers both inject_boundary_and_error_acs and
extract_criterion_text_from_object_format.
"""
from __future__ import annotations

import pytest
from bob.synthesizer_boundary_error_ac_injector import (
    inject_boundary_and_error_acs,
    extract_criterion_text_from_object_format,
)


class TestExtractCriterionTextFromObjectFormat:
    def test_criterion_key(self):
        obj = {"id": 1, "criterion": "pytest: tests/test_foo.py", "description": "..."}
        assert extract_criterion_text_from_object_format(obj) == "pytest: tests/test_foo.py"

    def test_ac_key(self):
        obj = {"ac": "File exists: src/foo.py"}
        assert extract_criterion_text_from_object_format(obj) == "File exists: src/foo.py"

    def test_acceptance_criterion_key(self):
        obj = {"acceptance_criterion": "Function defined: foo.bar"}
        assert extract_criterion_text_from_object_format(obj) == "Function defined: foo.bar"

    def test_text_key(self):
        obj = {"text": "integration: bob.synthesizer"}
        assert extract_criterion_text_from_object_format(obj) == "integration: bob.synthesizer"

    def test_criteria_key(self):
        obj = {"criteria": "pytest: tests/test_x.py"}
        assert extract_criterion_text_from_object_format(obj) == "pytest: tests/test_x.py"

    def test_value_key(self):
        obj = {"value": "File exists: src/bar.py"}
        assert extract_criterion_text_from_object_format(obj) == "File exists: src/bar.py"

    def test_description_key_fallback(self):
        obj = {"description": "pytest: tests/test_desc.py"}
        assert extract_criterion_text_from_object_format(obj) == "pytest: tests/test_desc.py"

    def test_no_known_key_returns_empty_string(self):
        obj = {"unknown_key": "something"}
        assert extract_criterion_text_from_object_format(obj) == ""

    def test_empty_dict_returns_empty_string(self):
        assert extract_criterion_text_from_object_format({}) == ""

    def test_whitespace_only_value_skipped(self):
        obj = {"criterion": "   ", "description": "real value"}
        assert extract_criterion_text_from_object_format(obj) == "real value"

    def test_non_dict_raises_type_error(self):
        with pytest.raises(TypeError, match="expected dict"):
            extract_criterion_text_from_object_format("not a dict")  # type: ignore[arg-type]

    def test_list_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_criterion_text_from_object_format(["a", "b"])  # type: ignore[arg-type]

    def test_strips_whitespace(self):
        obj = {"criterion": "  pytest: tests/test_foo.py  "}
        assert extract_criterion_text_from_object_format(obj) == "pytest: tests/test_foo.py"

    def test_criterion_key_priority_over_description(self):
        obj = {"criterion": "pytest: tests/test_a.py", "description": "pytest: tests/test_b.py"}
        assert extract_criterion_text_from_object_format(obj) == "pytest: tests/test_a.py"


class TestInjectBoundaryAndErrorAcs:
    def test_injects_boundary_when_absent(self):
        criteria = ["File exists: src/foo.py", "Function defined: foo.bar"]
        result = inject_boundary_and_error_acs(criteria, title="foo feature")
        boundary_acs = [c for c in result if "boundary" in c.lower() or "empty" in c.lower() or "zero" in c.lower()]
        assert len(boundary_acs) >= 1

    def test_injects_error_when_absent(self):
        criteria = ["File exists: src/foo.py", "Function defined: foo.bar"]
        result = inject_boundary_and_error_acs(criteria, title="foo feature")
        error_acs = [c for c in result if "error" in c.lower() or "invalid" in c.lower() or "raises" in c.lower() or "ValueError" in c]
        assert len(error_acs) >= 1

    def test_no_duplicate_when_boundary_already_present(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py — empty input returns None (boundary case)",
        ]
        result = inject_boundary_and_error_acs(criteria, title="foo")
        # Count boundary-indicating ACs — should not be more than original + 0
        boundary_count = sum(1 for c in result if "boundary" in c.lower() or "empty" in c.lower())
        original_boundary = sum(1 for c in criteria if "boundary" in c.lower() or "empty" in c.lower())
        assert boundary_count == original_boundary

    def test_no_duplicate_when_error_already_present(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py — invalid input raises ValueError (error path)",
        ]
        result = inject_boundary_and_error_acs(criteria, title="foo")
        error_count = sum(1 for c in result if "raises valueerror" in c.lower() or "invalid input" in c.lower())
        original_error = sum(1 for c in criteria if "raises valueerror" in c.lower() or "invalid input" in c.lower())
        assert error_count == original_error

    def test_no_injection_when_both_present(self):
        criteria = [
            "pytest: tests/test_foo.py — empty input returns None (boundary)",
            "pytest: tests/test_foo.py — raises ValueError on invalid input (error path)",
        ]
        result = inject_boundary_and_error_acs(criteria, title="foo")
        assert result == criteria

    def test_returns_superset_of_criteria(self):
        criteria = ["File exists: src/foo.py", "Function defined: foo.bar"]
        result = inject_boundary_and_error_acs(criteria, title="foo")
        assert len(result) >= len(criteria)
        for c in criteria:
            assert c in result

    def test_title_used_in_injected_slug(self):
        criteria = ["File exists: src/foo.py"]
        result = inject_boundary_and_error_acs(criteria, title="my cool feature")
        injected = [c for c in result if c not in criteria]
        assert any("my_cool_feature" in c or "my" in c for c in injected)

    def test_non_list_criteria_raises_type_error(self):
        with pytest.raises(TypeError, match="must be a list"):
            inject_boundary_and_error_acs("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_criteria_raises_type_error(self):
        with pytest.raises(TypeError):
            inject_boundary_and_error_acs(None, title="foo")  # type: ignore[arg-type]

    def test_non_string_item_raises_value_error(self):
        with pytest.raises(ValueError):
            inject_boundary_and_error_acs([123, "valid"], title="foo")  # type: ignore[arg-type]

    def test_dict_item_raises_value_error(self):
        with pytest.raises(ValueError):
            inject_boundary_and_error_acs([{"criterion": "pytest: tests/test.py"}], title="foo")  # type: ignore[arg-type]

    def test_empty_list_injects_both(self):
        result = inject_boundary_and_error_acs([], title="feature name")
        assert len(result) == 2

    def test_pytest_ac_with_boundary_description_not_duplicated(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty, zero, or minimum input returns a well-defined result rather than raising (boundary case)"
        ]
        result = inject_boundary_and_error_acs(criteria, title="foo")
        # Should only inject error, not boundary
        injected = [c for c in result if c not in criteria]
        assert not any("boundary" in c.lower() for c in injected)

    def test_returns_new_list_not_mutating_original(self):
        criteria = ["File exists: src/foo.py"]
        original_len = len(criteria)
        result = inject_boundary_and_error_acs(criteria, title="foo")
        assert len(criteria) == original_len  # original not mutated
        assert result is not criteria


class TestIntegrationWithBobSynthesizer:
    def test_importable_from_bob_synthesizer(self):
        from bob.synthesizer import inject_boundary_and_error_acs as fn
        assert callable(fn)

    def test_extract_importable_from_bob_synthesizer(self):
        from bob.synthesizer import extract_criterion_text_from_object_format as fn
        assert callable(fn)

    def test_inject_from_synthesizer_produces_correct_output(self):
        from bob.synthesizer import inject_boundary_and_error_acs
        result = inject_boundary_and_error_acs(["File exists: src/foo.py"], title="test feature")
        assert len(result) >= 3  # original + boundary + error

    def test_extract_from_synthesizer_handles_object(self):
        from bob.synthesizer import extract_criterion_text_from_object_format
        result = extract_criterion_text_from_object_format({"criterion": "pytest: tests/test_x.py"})
        assert result == "pytest: tests/test_x.py"
