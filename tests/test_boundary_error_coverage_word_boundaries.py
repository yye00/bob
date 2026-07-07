"""Word-boundary detection tests for bob.spec_synthesis._ensure_boundary_and_error_coverage.

The injector must detect existing boundary/error coverage with the composite
scorer's exact ``\\b`` word-boundary regexes, probing ONLY prose/behaviour ACs.
Naive substring matching over slugs false-tripped coverage (e.g. "failing"
matches "fail", a slug carrying "limit" matches the boundary token), so the AC
was skipped while the composite scorer still saw 0 coverage → composite 0.0 for
32/118 features. These tests pin the fix: injection and scoring must agree.
"""

from __future__ import annotations

import pytest

from bob.spec_synthesis import _ensure_boundary_and_error_coverage


class TestSlugFalsePositivesDoNotSuppressInjection:
    """A coverage token buried in a structural slug must NOT suppress injection."""

    def test_failing_slug_still_injects_error_ac(self):
        # "failing" contains "fail" — naive substring match would skip the error AC.
        criteria = [
            "File exists: src/bob/failing_tests_reporter.py",
            "Function defined: bob.failing_tests_reporter.report",
            "pytest: tests/test_failing_tests_reporter.py",
        ]
        out = _ensure_boundary_and_error_coverage(
            criteria, title="Failing tests reporter"
        )
        assert any("_error.py" in c for c in out)
        assert any("_boundary.py" in c for c in out)

    def test_limit_bearing_slug_still_injects_boundary_ac(self):
        # A slug carrying "limit" would false-trip the boundary detector under
        # naive substring matching, skipping the boundary AC.
        criteria = [
            "File exists: src/bob/rate_limiter.py",
            "Function defined: bob.rate_limiter.derive",
            "pytest: tests/test_rate_limiter.py",
        ]
        out = _ensure_boundary_and_error_coverage(
            criteria, title="Rate limiter module"
        )
        assert any("_boundary.py" in c for c in out)
        assert any("_error.py" in c for c in out)


class TestProseCoverageSuppressesInjection:
    """When a PROSE/behaviour AC carries a real coverage token, do not double-inject."""

    def test_prose_boundary_token_suppresses_boundary_injection(self):
        criteria = [
            "File exists: src/bob/x.py",
            "behavior: handles empty input gracefully",
        ]
        out = _ensure_boundary_and_error_coverage(criteria, title="x")
        assert not any("_boundary.py" in c for c in out)
        assert any("_error.py" in c for c in out)

    def test_prose_error_token_suppresses_error_injection(self):
        criteria = [
            "File exists: src/bob/x.py",
            "behavior: raises ValueError on invalid input",
        ]
        out = _ensure_boundary_and_error_coverage(criteria, title="x")
        assert not any("_error.py" in c for c in out)
        assert any("_boundary.py" in c for c in out)

    def test_both_prose_tokens_inject_nothing(self):
        criteria = [
            "File exists: src/bob/x.py",
            "behavior: handles empty input and raises on invalid data",
        ]
        out = _ensure_boundary_and_error_coverage(criteria, title="x")
        assert out == criteria

    def test_existing_pytest_boundary_ac_is_not_double_injected(self):
        criteria = [
            "File exists: src/bob/x.py",
            "pytest: tests/test_x_boundary.py — empty input returns a result",
            "pytest: tests/test_x_error.py — invalid input raises ValueError",
        ]
        out = _ensure_boundary_and_error_coverage(criteria, title="x")
        assert out == criteria


class TestInjectionShape:
    """Injected ACs use the pytest: structured form and embed the keyword."""

    def test_injected_acs_are_pytest_form(self):
        out = _ensure_boundary_and_error_coverage(
            ["File exists: src/bob/x.py"], title="My Feature"
        )
        injected = [c for c in out if c != "File exists: src/bob/x.py"]
        assert len(injected) == 2
        assert all(c.startswith("pytest: tests/") for c in injected)

    def test_returns_list_and_preserves_input_order(self):
        criteria = ["File exists: src/bob/x.py", "Function defined: bob.x.f"]
        out = _ensure_boundary_and_error_coverage(criteria, title="x")
        assert out[:2] == criteria
        assert isinstance(out, list)

    def test_does_not_mutate_input(self):
        criteria = ["File exists: src/bob/x.py"]
        copy = list(criteria)
        _ensure_boundary_and_error_coverage(criteria, title="x")
        assert criteria == copy


class TestBoundaryAndErrorInputs:
    def test_empty_list_injects_both(self):
        out = _ensure_boundary_and_error_coverage([], title="feature")
        assert any("_boundary.py" in c for c in out)
        assert any("_error.py" in c for c in out)
        assert len(out) == 2

    def test_non_list_raises(self):
        with pytest.raises((TypeError, ValueError)):
            _ensure_boundary_and_error_coverage("not a list", title="x")

    def test_none_raises(self):
        with pytest.raises((TypeError, ValueError)):
            _ensure_boundary_and_error_coverage(None, title="x")
