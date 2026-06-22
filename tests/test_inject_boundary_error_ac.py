"""Tests for synthesizer.inject_boundary_error_ac.inject_missing_acs."""
import pytest
from synthesizer.inject_boundary_error_ac import inject_missing_acs


class TestInjectMissingAcsBasicBehavior:
    def test_returns_list(self):
        result = inject_missing_acs(["File exists: src/foo.py"], title="foo feature")
        assert isinstance(result, list)

    def test_no_injection_when_boundary_and_error_present(self):
        criteria = [
            "File exists: src/foo.py",
            "The function returns empty list on null input (boundary case)",
            "The function raises ValueError on invalid input (error path)",
        ]
        result = inject_missing_acs(criteria, title="foo")
        assert len(result) == len(criteria)

    def test_injects_boundary_when_missing(self):
        criteria = [
            "File exists: src/foo.py",
            "The function raises ValueError on invalid input (error path)",
        ]
        result = inject_missing_acs(criteria, title="foo feature")
        boundary_acs = [ac for ac in result if "boundary" in ac.lower() or "empty" in ac.lower() or "zero" in ac.lower() or "minimum" in ac.lower()]
        assert boundary_acs, "Expected at least one boundary AC to be injected"

    def test_injects_error_when_missing(self):
        criteria = [
            "File exists: src/foo.py",
            "The function returns empty list on null input (boundary case)",
        ]
        result = inject_missing_acs(criteria, title="foo feature")
        error_acs = [ac for ac in result if "error" in ac.lower() or "raises" in ac.lower() or "invalid" in ac.lower() or "valueerror" in ac.lower()]
        assert error_acs, "Expected at least one error-path AC to be injected"

    def test_injects_both_when_structural_only(self):
        criteria = [
            "File exists: src/foo.py",
            "Function defined: foo.bar",
            "pytest: tests/test_foo.py",
        ]
        result = inject_missing_acs(criteria, title="foo feature")
        assert len(result) > len(criteria), "Expected injected ACs appended"

    def test_injected_acs_reference_feature_slug(self):
        criteria = ["File exists: src/unique_module.py"]
        result = inject_missing_acs(criteria, title="unique module feature")
        new_acs = result[len(criteria):]
        for ac in new_acs:
            assert "unique_module_feature" in ac or "feature" in ac.lower()

    def test_does_not_modify_original_list(self):
        criteria = ["File exists: src/foo.py"]
        original = list(criteria)
        inject_missing_acs(criteria, title="foo")
        assert criteria == original


class TestInjectMissingAcsErrorPaths:
    def test_non_list_raises_typeerror(self):
        with pytest.raises(TypeError):
            inject_missing_acs("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises_typeerror(self):
        with pytest.raises(TypeError):
            inject_missing_acs(None, title="foo")  # type: ignore[arg-type]

    def test_non_string_item_raises_valueerror(self):
        with pytest.raises((TypeError, ValueError)):
            inject_missing_acs([{"not": "a string"}], title="foo")  # type: ignore[arg-type]

    def test_integer_item_raises_valueerror(self):
        with pytest.raises((TypeError, ValueError)):
            inject_missing_acs([42], title="foo")  # type: ignore[arg-type]


class TestInjectMissingAcsBoundaryInputs:
    def test_empty_list_returns_list(self):
        result = inject_missing_acs([], title="foo")
        assert isinstance(result, list)
        assert len(result) >= 2  # both boundary and error injected

    def test_empty_title_does_not_raise(self):
        result = inject_missing_acs(["File exists: src/foo.py"], title="")
        assert isinstance(result, list)

    def test_whitespace_only_strings_handled(self):
        criteria = ["", "  ", "pytest: tests/test_foo.py"]
        result = inject_missing_acs(criteria, title="foo")
        assert isinstance(result, list)
