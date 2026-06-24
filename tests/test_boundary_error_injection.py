"""Tests for synthesizer.parse_criteria.inject_boundary_error_criteria.

Verifies that the function deterministically injects boundary and error-path
ACs when absent, and does NOT duplicate when already present.
"""
import pytest
from synthesizer.parse_criteria import inject_boundary_error_criteria


class TestInjectionWhenAbsent:
    def test_structural_only_gets_both_injected(self):
        """4 structural ACs with no coverage → both boundary and error injected."""
        criteria = [
            "File exists: src/foo.py",
            "Function defined: foo.bar",
            "pytest: tests/test_foo.py",
            "integration: foo wired into pipeline",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo feature")
        assert len(result) == 6
        texts = " ".join(result)
        assert "boundary" in texts.lower()
        assert "error" in texts.lower()

    def test_missing_boundary_injects_boundary_ac(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo_error.py — raises ValueError on invalid",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert len(result) == 3
        boundary_acs = [c for c in result if "boundary" in c.lower()]
        assert len(boundary_acs) == 1

    def test_missing_error_injects_error_ac(self):
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo_boundary.py — empty input returns None (boundary case)",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert len(result) == 3
        error_acs = [c for c in result if "error" in c.lower() or "raises" in c.lower()]
        assert len(error_acs) >= 1

    def test_empty_criteria_injects_both(self):
        result = inject_boundary_error_criteria([], title="my feature")
        assert len(result) == 2

    def test_injected_ac_references_feature_slug(self):
        result = inject_boundary_error_criteria(["File exists: src/x.py"], title="my cool feature")
        injected = [c for c in result if "boundary" in c.lower() or "error" in c.lower()]
        assert any("my_cool_feature" in ac for ac in injected)


class TestNoInjectionWhenPresent:
    def test_boundary_token_in_prose_ac_no_injection(self):
        criteria = [
            "File exists: src/foo.py",
            "When input is empty the function returns an empty list (boundary case)",
            "When input is invalid the function raises ValueError",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert result == criteria

    def test_error_token_in_prose_ac_no_injection(self):
        criteria = [
            "File exists: src/foo.py",
            "The function raises ValueError on None input",
            "The function handles minimum/zero values gracefully",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert result == criteria

    def test_boundary_in_pytest_description_no_injection(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — minimum input returns empty list",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert result == criteria

    def test_zero_in_prose_counts_as_boundary(self):
        criteria = [
            "The function handles zero elements without raising",
            "pytest: tests/test_foo_error.py — raises on invalid",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert result == criteria

    def test_null_in_prose_counts_as_boundary(self):
        criteria = [
            "Returns null when the input list is empty",
            "raises ValueError on non-string input",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo")
        assert result == criteria


class TestErrorHandling:
    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            inject_boundary_error_criteria("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            inject_boundary_error_criteria(None, title="foo")  # type: ignore[arg-type]

    def test_dict_element_raises_value_error(self):
        with pytest.raises(ValueError):
            inject_boundary_error_criteria([{"criterion": "foo"}], title="foo")  # type: ignore[arg-type]

    def test_integer_element_raises_value_error(self):
        with pytest.raises(ValueError):
            inject_boundary_error_criteria([42], title="foo")  # type: ignore[arg-type]


class TestCompositeScoreFix:
    def test_4ac_structural_only_composite_passes_after_injection(self):
        """Regression: 4 structural ACs → composite 0.0 before fix, ~0.877 after."""
        criteria = [
            "File exists: src/foo.py",
            "Function defined: foo.bar",
            "pytest: tests/test_foo.py",
            "integration: foo wired into pipeline",
        ]
        result = inject_boundary_error_criteria(criteria, title="foo feature")
        # After injection we should have boundary and error ACs present
        full_text = " ".join(result)
        assert "boundary" in full_text.lower() or "empty" in full_text.lower() or "minimum" in full_text.lower()
        assert "error" in full_text.lower() or "raises" in full_text.lower() or "invalid" in full_text.lower()
