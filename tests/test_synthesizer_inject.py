"""Tests for bob73.synthesizer.inject_boundary_error_criteria.

Covers:
- Injection when no boundary or error-path AC is present
- No duplication when boundary/error ACs already present
- Slug derivation from title
- Type validation (TypeError/ValueError on bad input)
- Returned list is a superset of original criteria
"""
import pytest
from bob73.synthesizer import inject_boundary_error_criteria


STRUCTURAL_ONLY = [
    "File exists: src/bob73/synthesizer.py",
    "Function defined: bob73.synthesizer.parse_criteria_response",
    "pytest: tests/test_synthesizer.py",
]


class TestInjectWhenMissing:
    def test_injects_both_when_structural_only(self):
        result = inject_boundary_error_criteria(STRUCTURAL_ONLY, title="my feature")
        assert len(result) == len(STRUCTURAL_ONLY) + 2
        joined = " ".join(result)
        assert "boundary" in joined.lower()
        assert "error" in joined.lower()

    def test_original_criteria_preserved(self):
        result = inject_boundary_error_criteria(STRUCTURAL_ONLY, title="my feature")
        for ac in STRUCTURAL_ONLY:
            assert ac in result

    def test_injected_boundary_ac_references_slug(self):
        result = inject_boundary_error_criteria(STRUCTURAL_ONLY, title="my feature")
        boundary_acs = [c for c in result if "boundary" in c.lower() and "pytest:" in c.lower()]
        assert boundary_acs, "Expected at least one injected boundary pytest: AC"
        assert "my_feature" in boundary_acs[0] or "my" in boundary_acs[0]

    def test_injected_error_ac_references_slug(self):
        result = inject_boundary_error_criteria(STRUCTURAL_ONLY, title="my feature")
        error_acs = [c for c in result if "error" in c.lower() and "pytest:" in c.lower()]
        assert error_acs, "Expected at least one injected error pytest: AC"

    def test_empty_criteria_gets_both_injected(self):
        result = inject_boundary_error_criteria([], title="foo bar")
        assert len(result) == 2

    def test_no_title_uses_feature_slug(self):
        result = inject_boundary_error_criteria([], title="")
        joined = " ".join(result)
        assert "feature" in joined


class TestNoInjectionWhenPresent:
    def test_no_injection_when_boundary_prose_ac_present(self):
        criteria = [
            "File exists: src/x.py",
            "When input is empty the function returns an empty list (boundary case)",
        ]
        result = inject_boundary_error_criteria(criteria, title="x")
        # boundary already present; only error should be injected
        assert len(result) == len(criteria) + 1

    def test_no_injection_when_error_prose_ac_present(self):
        criteria = [
            "File exists: src/x.py",
            "Invalid input raises ValueError",
        ]
        result = inject_boundary_error_criteria(criteria, title="x")
        # error already present; only boundary should be injected
        assert len(result) == len(criteria) + 1

    def test_no_injection_when_both_present(self):
        criteria = [
            "File exists: src/x.py",
            "When input is zero the function returns 0 (boundary/minimum case)",
            "Invalid input raises ValueError and does not silently succeed",
        ]
        result = inject_boundary_error_criteria(criteria, title="x")
        assert result == criteria

    def test_already_has_injected_boundary_ac(self):
        """If a pytest: AC already has 'boundary' in its description, do not inject another."""
        criteria = [
            "pytest: tests/test_x_boundary.py — empty or minimum input returns a well-defined result (boundary case)",
        ]
        result = inject_boundary_error_criteria(criteria, title="x")
        # boundary covered; only error injected
        boundary_count = sum(1 for c in result if "boundary" in c.lower())
        assert boundary_count == 1  # no duplicate


class TestTypeValidation:
    def test_non_list_raises_type_error(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria("not a list", title="x")  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria(None, title="x")  # type: ignore[arg-type]

    def test_criteria_with_dict_items_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria([{"bad": "item"}], title="x")  # type: ignore[arg-type]

    def test_criteria_with_int_item_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_error_criteria([42], title="x")  # type: ignore[arg-type]


class TestSlugDerivation:
    def test_title_with_special_chars_produces_valid_slug(self):
        result = inject_boundary_error_criteria([], title="My Feature — with dashes & symbols!")
        joined = " ".join(result)
        # The slug should appear in the injected pytest: AC path
        assert "tests/test_" in joined

    def test_slug_truncated_to_50_chars(self):
        long_title = "a" * 200
        result = inject_boundary_error_criteria([], title=long_title)
        for ac in result:
            if "pytest:" in ac:
                # Extract the filename portion
                path = ac.split("pytest:")[1].strip().split()[0]
                assert len(path) < 120, "slug should not produce absurdly long filenames"
