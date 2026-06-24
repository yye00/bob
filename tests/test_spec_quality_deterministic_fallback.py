"""Tests for ensure_boundary_and_error_coverage via bob.spec_quality.

AC: pytest: tests/test_spec_quality_deterministic_fallback.py
AC: integration: bob.spec_synthesis

Verifies that:
- ensure_boundary_and_error_coverage is importable from bob.spec_quality
- The function injects boundary and error ACs when missing
- The integration with bob.spec_synthesis is intact
- deterministic_fallback via spec_quality carries the same guarantees
"""

from __future__ import annotations

import re

import pytest

from bob.spec_quality import ensure_boundary_and_error_coverage

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


class TestSpecQualityImport:
    """ensure_boundary_and_error_coverage must be importable from bob.spec_quality."""

    def test_importable_from_spec_quality(self):
        from bob.spec_quality import ensure_boundary_and_error_coverage as fn
        assert callable(fn)

    def test_function_is_not_stub(self):
        import inspect
        fn = ensure_boundary_and_error_coverage
        src = inspect.getsource(fn)
        assert len(src.strip()) > 100, "Function appears to be a stub"


class TestSpecSynthesisIntegration:
    """Integration: bob.spec_synthesis exposes the same guarantee."""

    def test_spec_synthesis_has_ensure_boundary_and_error_coverage(self):
        import bob.spec_synthesis as ss
        assert hasattr(ss, "ensure_boundary_and_error_coverage"), (
            "bob.spec_synthesis must export ensure_boundary_and_error_coverage"
        )
        assert callable(ss.ensure_boundary_and_error_coverage)

    def test_spec_synthesis_deterministic_fallback_carries_boundary_ac(self):
        from bob.spec_synthesis import deterministic_fallback
        result = deterministic_fallback("my integration feature", "A description.")
        assert isinstance(result, list)
        has_bnd = any(_BND.search(c) for c in result)
        assert has_bnd, f"deterministic_fallback missing boundary AC: {result}"

    def test_spec_synthesis_deterministic_fallback_carries_error_ac(self):
        from bob.spec_synthesis import deterministic_fallback
        result = deterministic_fallback("my integration feature", "A description.")
        has_err = any(_ERR.search(c) for c in result)
        assert has_err, f"deterministic_fallback missing error AC: {result}"


class TestEnsureBoundaryAndErrorCoverage:
    """Core behavior of ensure_boundary_and_error_coverage from bob.spec_quality."""

    def test_returns_list(self):
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob/foo.py"], title="foo feature"
        )
        assert isinstance(result, list)

    def test_injects_boundary_ac_when_missing(self):
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob/foo.py"], title="foo feature"
        )
        has_bnd = any(_BND.search(c) for c in result)
        assert has_bnd, f"No boundary AC injected: {result}"

    def test_injects_error_ac_when_missing(self):
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob/foo.py"], title="foo feature"
        )
        has_err = any(_ERR.search(c) for c in result)
        assert has_err, f"No error AC injected: {result}"

    def test_empty_list_gets_two_acs_injected(self):
        result = ensure_boundary_and_error_coverage([], title="my feature")
        assert len(result) == 2
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd and has_err

    def test_result_never_smaller_than_input(self):
        criteria = [
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        assert len(result) >= len(criteria)

    def test_non_list_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            ensure_boundary_and_error_coverage("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            ensure_boundary_and_error_coverage(None, title="foo")  # type: ignore[arg-type]

    def test_idempotent_when_both_present(self):
        criteria = [
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo_boundary.py — empty input returns a well-defined result",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
        ]
        first = ensure_boundary_and_error_coverage(criteria, title="foo")
        second = ensure_boundary_and_error_coverage(first, title="foo")
        assert len(second) == len(first), f"Double-injection: {second}"

    def test_does_not_inject_boundary_when_already_present(self):
        criteria = [
            "pytest: tests/test_foo_boundary.py — empty input returns a result",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        bnd_count = sum(1 for c in result if _BND.search(c))
        assert bnd_count >= 1
        # at most one additional AC may be added (for error path)
        assert len(result) <= len(criteria) + 1

    def test_does_not_inject_error_when_already_present(self):
        criteria = [
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        err_count = sum(1 for c in result if _ERR.search(c))
        assert err_count >= 1
        # at most one additional AC may be added (for boundary path)
        assert len(result) <= len(criteria) + 1


class TestDeterministicFallbackCompositeGuarantee:
    """WHEN fallback is used THEN result must enable composite > 0.0."""

    def test_fallback_result_has_boundary_and_error_acs(self):
        """Verifies the root cause fix: fallback must not produce composite=0.0."""
        result = ensure_boundary_and_error_coverage(
            [
                "File exists: src/bob/rate_limited.py",
                "pytest: tests/test_rate_limited.py",
                "Function defined: bob.rate_limited.process",
            ],
            title="rate limited feature",
        )
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, f"Composite would be 0.0 — no boundary AC: {result}"
        assert has_err, f"Composite would be 0.0 — no error AC: {result}"

    def test_all_structural_acs_with_no_coverage_get_both_injected(self):
        """Structural-only ACs (file/function/pytest path) yield composite=0.0.
        The injector must detect zero coverage and add exactly two ACs."""
        structural = [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.run",
            "pytest: tests/test_foo.py",
        ]
        result = ensure_boundary_and_error_coverage(structural, title="foo")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, result
        assert has_err, result
        assert len(result) == len(structural) + 2, (
            f"Expected {len(structural) + 2} ACs, got {len(result)}: {result}"
        )
