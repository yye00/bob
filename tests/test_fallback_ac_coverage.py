"""Tests for bob3.fallback_ac_coverage.ensure_boundary_and_error_coverage.

This module tests the canonical boundary/error coverage enforcement function
that guarantees ANY AC list — whether from LLM synthesis or deterministic
fallback — contains at least one boundary-condition AC and one error-path AC,
preventing composite spec_quality_score 0.0 from stranding rate-limited
features at the 0.85 gate.
"""
from __future__ import annotations

import re

import pytest

from bob3.fallback_ac_coverage import ensure_boundary_and_error_coverage

_BND = re.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
    r"boundary|edge case|corner case|overflow|underflow|limit|"
    r"threshold|floor|ceiling)\b",
    re.IGNORECASE,
)

_ERR = re.compile(
    r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
    r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
    r"TypeError|RuntimeError)\b",
    re.IGNORECASE,
)


class TestEnsureBoundaryAndErrorCoverage:
    """Core injection tests."""

    def test_empty_list_injects_both(self):
        """Empty input gets both ACs injected."""
        result = ensure_boundary_and_error_coverage([], title="my feature")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, f"No boundary AC injected: {result}"
        assert has_err, f"No error AC injected: {result}"

    def test_empty_list_returns_list(self):
        result = ensure_boundary_and_error_coverage([], title="my feature")
        assert isinstance(result, list)

    def test_structural_acs_only_gets_both_injected(self):
        """Structural-only criteria have no prose, so both ACs must be injected."""
        criteria = [
            "File exists: src/bob3/foo.py",
            "Function defined: bob3.foo.bar",
            "pytest: tests/test_foo.py",
            "integration: bob3.orchestrator",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo feature")
        assert len(result) > len(criteria)
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, f"No boundary AC: {result}"
        assert has_err, f"No error AC: {result}"

    def test_already_has_boundary_and_error_no_injection(self):
        """When both coverages exist, no AC is injected."""
        criteria = [
            "File exists: src/bob3/foo.py",
            "The function returns empty list for zero input (boundary case).",
            "The function raises ValueError on invalid input (error path).",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        assert result == criteria, f"Unexpected injection: {result}"

    def test_already_has_boundary_only_injects_error(self):
        """When only boundary coverage exists, inject error AC only."""
        criteria = [
            "File exists: src/bob3/foo.py",
            "Returns empty list for zero-length input.",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, result
        assert has_err, result
        # Length increased by exactly 1 (error AC added)
        assert len(result) == len(criteria) + 1, result

    def test_already_has_error_only_injects_boundary(self):
        """When only error coverage exists, inject boundary AC only."""
        criteria = [
            "File exists: src/bob3/foo.py",
            "Raises ValueError on invalid input.",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, result
        assert has_err, result
        assert len(result) == len(criteria) + 1, result

    def test_injected_acs_use_pytest_form(self):
        """Injected ACs must be in pytest: structured form."""
        result = ensure_boundary_and_error_coverage([], title="my feature")
        injected = [c for c in result if c.startswith("pytest:")]
        assert len(injected) >= 2, f"Expected 2 pytest: ACs, got: {result}"

    def test_slug_derived_from_title(self):
        """Injected AC file names contain a slug derived from the title."""
        result = ensure_boundary_and_error_coverage([], title="my test feature")
        combined = " ".join(result)
        assert "my_test_feature" in combined or "test_feature" in combined, (
            f"Slug not in injected ACs: {result}"
        )

    def test_empty_title_uses_feature_slug(self):
        """Empty title falls back to 'feature' slug, does not raise."""
        result = ensure_boundary_and_error_coverage([], title="")
        assert isinstance(result, list)
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, result
        assert has_err, result

    def test_result_never_smaller_than_input(self):
        """Injection only adds ACs, never removes them."""
        criteria = ["File exists: src/bob3/x.py", "pytest: tests/test_x.py"]
        result = ensure_boundary_and_error_coverage(criteria, title="x")
        assert len(result) >= len(criteria), (
            f"Dropped criteria: {len(result)} < {len(criteria)}"
        )

    def test_original_criteria_preserved_in_output(self):
        """All original criteria appear in the result."""
        criteria = ["File exists: src/bob3/x.py", "pytest: tests/test_x.py"]
        result = ensure_boundary_and_error_coverage(criteria, title="x")
        for c in criteria:
            assert c in result, f"Original criterion lost: {c!r}"

    def test_idempotent_when_both_present(self):
        """Applying coverage twice yields the same result as applying once."""
        criteria = ["File exists: src/bob3/x.py", "pytest: tests/test_x.py"]
        first = ensure_boundary_and_error_coverage(criteria, title="x")
        second = ensure_boundary_and_error_coverage(first, title="x")
        assert len(second) == len(first), (
            f"Double-injection on second call: {second}"
        )

    def test_slug_false_positive_prevention(self):
        """Slug tokens like 'failing' or 'min-heap' must NOT satisfy coverage.

        A feature whose slug contains a boundary/error keyword (e.g. 'failing',
        'length-capped') must still get ACs injected because the injector uses
        word-boundary regexes over prose-only ACs, not naive substring over slugs.
        """
        # The slug "failing-feature" contains "fail" but only in a structural AC.
        criteria = [
            "File exists: src/bob3/failing_feature.py",
            "Function defined: bob3.failing_feature.main",
            "pytest: tests/test_failing_feature.py",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="failing feature")
        # Must inject error AC because structural ACs are not probed for keywords.
        assert len(result) > len(criteria), (
            f"Slug false-positive: no injection despite structural-only ACs: {result}"
        )

    def test_tuple_input_accepted(self):
        """Tuple input is accepted (not just list)."""
        criteria = ("File exists: src/bob3/foo.py",)
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        assert isinstance(result, list)
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, result
        assert has_err, result


class TestEnsureBoundaryAndErrorCoverageErrors:
    """Error-path tests for ensure_boundary_and_error_coverage."""

    def test_string_input_raises_type_error(self):
        """A plain string is not a sequence of criteria; must raise."""
        with pytest.raises((TypeError, AttributeError)):
            ensure_boundary_and_error_coverage("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_input_raises_type_error(self):
        with pytest.raises((TypeError, AttributeError)):
            ensure_boundary_and_error_coverage(None, title="foo")  # type: ignore[arg-type]

    def test_int_input_raises_type_error(self):
        with pytest.raises((TypeError, AttributeError)):
            ensure_boundary_and_error_coverage(42, title="foo")  # type: ignore[arg-type]

    def test_non_string_element_raises(self):
        """Non-string elements in the criteria list must raise."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            ensure_boundary_and_error_coverage([None, 42], title="foo")  # type: ignore[list-item]


class TestIntegrationWithOrchestrator:
    """Integration smoke-test: verify the module is importable from bob3."""

    def test_importable_from_bob3(self):
        """ensure_boundary_and_error_coverage must be importable from bob3.fallback_ac_coverage."""
        from bob3.fallback_ac_coverage import ensure_boundary_and_error_coverage as fn
        assert callable(fn)

    def test_orchestrator_module_importable(self):
        """bob3.orchestrator package must be importable (integration AC)."""
        import importlib
        mod = importlib.import_module("bob3.orchestrator")
        assert mod is not None

    def test_deterministic_fallback_output_passes_coverage(self):
        """Output of spec_synthesizer.deterministic_fallback passes our coverage check."""
        from bob3.spec_synthesizer import deterministic_fallback
        criteria = deterministic_fallback("rate limited feature", "A rate-limited feature.")
        result = ensure_boundary_and_error_coverage(criteria, title="rate limited feature")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, f"deterministic_fallback output lacks boundary: {criteria}"
        assert has_err, f"deterministic_fallback output lacks error: {criteria}"

    def test_composite_score_nonzero_after_coverage(self):
        """After ensure_boundary_and_error_coverage, a spec should not score 0.0.

        This is the key regression the feature closes: a rate-limited feature
        falling back to deterministic_fallback must NOT produce composite=0.0.
        """
        from bob3.spec_synthesizer import deterministic_fallback
        criteria = deterministic_fallback("rate limited feature x", "Some description.")
        result = ensure_boundary_and_error_coverage(criteria, title="rate limited feature x")
        # Must have both boundary and error ACs so composite geometric mean can exceed 0.0
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd and has_err, (
            f"Composite would be 0.0 — missing coverage in: {result}"
        )
