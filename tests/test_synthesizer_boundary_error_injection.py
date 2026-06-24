"""Tests for inject_boundary_and_error_acs from bob.synthesizer.

Verifies that the synthesizer deterministically injects boundary-condition and
error-path ACs when the LLM-synthesized criteria lack them, ensuring the
composite spec_quality_score (weighted geometric mean) cannot be driven to 0.0
by missing boundary_coverage or error_path_coverage.
"""
from __future__ import annotations

import pytest
from bob.synthesizer import inject_boundary_and_error_acs


BOUNDARY_TOKENS = ["empty", "zero", "minimum", "maximum", "null", "boundary", "limit"]
ERROR_TOKENS = ["error", "exception", "invalid", "ValueError", "raises", "reject"]


class TestInjectBoundaryAndErrorAcs:
    """inject_boundary_and_error_acs must guarantee boundary + error coverage."""

    def test_injects_boundary_ac_when_absent(self):
        """Structural-only ACs get a boundary AC appended."""
        criteria = [
            "File exists: src/bob/synthesizer_boundary_error_injector.py",
            "pytest: tests/test_foo.py",
        ]
        result = inject_boundary_and_error_acs(criteria, title="my feature")
        joined = " ".join(result).lower()
        boundary_found = any(tok in joined for tok in BOUNDARY_TOKENS)
        assert boundary_found, f"No boundary token in result: {result}"

    def test_injects_error_ac_when_absent(self):
        """Structural-only ACs get an error-path AC appended."""
        criteria = [
            "File exists: src/bob/synthesizer_boundary_error_injector.py",
            "Function defined: bob.synthesizer.inject_boundary_and_error_criteria",
        ]
        result = inject_boundary_and_error_acs(criteria, title="my feature")
        joined = " ".join(result).lower()
        error_found = any(tok in joined for tok in ERROR_TOKENS)
        assert error_found, f"No error token in result: {result}"

    def test_injects_both_when_neither_present(self):
        """With no boundary or error tokens, both ACs are injected."""
        criteria = ["File exists: src/foo.py"]
        result = inject_boundary_and_error_acs(criteria, title="my feature")
        assert len(result) == 3  # 1 original + 2 injected

    def test_no_duplicate_boundary_when_already_present(self):
        """If LLM included a boundary AC, no second boundary AC is added."""
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py — empty input returns None (boundary case)",
        ]
        before_count = len(criteria)
        result = inject_boundary_and_error_acs(criteria, title="my feature")
        # Only error should be injected (1 new), not a second boundary
        assert len(result) == before_count + 1
        boundary_acs = [
            c for c in result
            if any(tok in c.lower() for tok in BOUNDARY_TOKENS)
        ]
        assert len(boundary_acs) == 1, f"Expected exactly 1 boundary AC, got: {boundary_acs}"

    def test_no_duplicate_error_when_already_present(self):
        """If LLM included an error-path AC, no second error AC is added."""
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError (error path)",
        ]
        before_count = len(criteria)
        result = inject_boundary_and_error_acs(criteria, title="my feature")
        # Only boundary should be injected (1 new), not a second error
        assert len(result) == before_count + 1
        error_acs = [
            c for c in result
            if any(tok in c.lower() for tok in ERROR_TOKENS)
        ]
        assert len(error_acs) == 1, f"Expected exactly 1 error AC, got: {error_acs}"

    def test_no_injection_when_both_already_present(self):
        """When LLM included both coverage types, no ACs are injected."""
        criteria = [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py — empty input returns None (boundary)",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError (error path)",
        ]
        result = inject_boundary_and_error_acs(criteria, title="my feature")
        assert result == criteria

    def test_result_is_superset_of_original(self):
        """All original criteria appear in the result."""
        criteria = [
            "File exists: src/bob/synthesizer_boundary_error_injector.py",
            "Function defined: bob.synthesizer.parse_criteria_response",
            "Function defined: bob.synthesizer.inject_boundary_and_error_criteria",
            "pytest: tests/test_synthesizer_parse_object_format.py",
            "pytest: tests/test_synthesizer_boundary_error_injection.py",
            "integration: bob.orchestrator",
        ]
        result = inject_boundary_and_error_acs(criteria, title="synthesizer feature")
        for original in criteria:
            assert original in result, f"Original AC dropped: {original!r}"

    def test_injected_acs_reference_feature_slug(self):
        """Injected ACs contain the feature slug (not generic boilerplate)."""
        criteria = ["File exists: src/foo.py"]
        result = inject_boundary_and_error_acs(criteria, title="my_cool_feature")
        injected = [c for c in result if c not in criteria]
        assert len(injected) == 2
        for ac in injected:
            assert "my_cool_feature" in ac, f"Injected AC missing feature slug: {ac!r}"

    def test_composite_score_improves_from_zero_after_injection(self):
        """Structural-only criteria go from boundary_coverage=0 to boundary_coverage>0."""
        structural_criteria = [
            "File exists: src/bob/synthesizer_boundary_error_injector.py",
            "Function defined: bob.synthesizer.parse_criteria_response",
            "Function defined: bob.synthesizer.inject_boundary_and_error_criteria",
            "pytest: tests/test_synthesizer_parse_object_format.py",
            "pytest: tests/test_synthesizer_boundary_error_injection.py",
            "integration: bob.orchestrator",
        ]
        result = inject_boundary_and_error_acs(structural_criteria, title="synthesizer feature")
        joined = " ".join(result).lower()
        boundary_found = any(tok in joined for tok in BOUNDARY_TOKENS)
        error_found = any(tok in joined for tok in ERROR_TOKENS)
        assert boundary_found, "No boundary coverage after injection"
        assert error_found, "No error coverage after injection"

    def test_non_list_raises_type_error(self):
        """Non-list input raises TypeError."""
        with pytest.raises(TypeError):
            inject_boundary_and_error_acs("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        """None input raises TypeError."""
        with pytest.raises(TypeError):
            inject_boundary_and_error_acs(None, title="foo")  # type: ignore[arg-type]

    def test_non_string_element_raises_value_error(self):
        """Non-string element in list raises an error (not silently succeeds)."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            inject_boundary_and_error_acs([{"bad": "dict"}], title="foo")  # type: ignore[arg-type]

    def test_empty_list_returns_two_injected_acs(self):
        """Empty list gets both boundary and error ACs injected."""
        result = inject_boundary_and_error_acs([], title="some feature")
        assert isinstance(result, list)
        assert len(result) == 2
        joined = " ".join(result).lower()
        assert any(tok in joined for tok in BOUNDARY_TOKENS)
        assert any(tok in joined for tok in ERROR_TOKENS)

    def test_returns_new_list_not_mutating_original(self):
        """The function must not mutate the input list."""
        criteria = ["File exists: src/foo.py"]
        original_len = len(criteria)
        inject_boundary_and_error_acs(criteria, title="foo")
        assert len(criteria) == original_len, "Input list was mutated"

    def test_typical_synthesizer_output_passes_after_injection(self):
        """Typical 4-AC structural-only output from LLM gets injected to pass score gate."""
        llm_output = [
            "File exists: src/bob/synthesizer_boundary_error_injector.py",
            "Function defined: bob.synthesizer.inject_boundary_and_error_criteria",
            "pytest: tests/test_synthesizer_parse_object_format.py",
            "integration: bob.orchestrator",
        ]
        result = inject_boundary_and_error_acs(llm_output, title="synthesizer boundary error")
        assert len(result) == 6  # 4 original + 2 injected
        joined = " ".join(result).lower()
        assert any(tok in joined for tok in BOUNDARY_TOKENS), "Missing boundary coverage"
        assert any(tok in joined for tok in ERROR_TOKENS), "Missing error coverage"
