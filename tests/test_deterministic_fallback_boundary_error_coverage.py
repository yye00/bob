"""Coverage tests: deterministic_fallback carries boundary + error-path ACs.

Feature 46066ada: a rate-limited feature falls back to deterministic_fallback.
That path MUST apply the same _ensure_boundary_and_error_coverage guarantee the
LLM path gets, so the composite spec_quality_score (a weighted geometric mean)
cannot be zeroed by boundary_coverage=0 AND error_path_coverage=0.

AC: pytest: tests/test_deterministic_fallback_boundary_error_coverage.py
AC: Function defined: bob.synthesizer.deterministic_fallback
AC: Function defined: bob.synthesizer._ensure_boundary_and_error_coverage
AC: integration: bob.synthesizer
"""
from __future__ import annotations

import re

import pytest

import bob.synthesizer as synthesizer
from bob.synthesizer import (
    _ensure_boundary_and_error_coverage,
    deterministic_fallback,
)

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


def _has_boundary(criteria: list[str]) -> bool:
    return any(_BND.search(c) for c in criteria)


def _has_error(criteria: list[str]) -> bool:
    return any(_ERR.search(c) for c in criteria)


class TestFunctionsExported:
    """AC: both symbols must be reachable from bob.synthesizer."""

    def test_deterministic_fallback_is_callable(self):
        assert callable(synthesizer.deterministic_fallback)

    def test_ensure_coverage_is_callable(self):
        assert callable(synthesizer._ensure_boundary_and_error_coverage)


class TestFallbackCarriesCoverage:
    """The deterministic fallback path must not emit a composite-0.0 spec."""

    def test_fallback_includes_boundary_ac(self):
        result = deterministic_fallback("my great feature", "does a thing")
        assert _has_boundary(result), result

    def test_fallback_includes_error_ac(self):
        result = deterministic_fallback("my great feature", "does a thing")
        assert _has_error(result), result

    def test_fallback_includes_both_even_with_empty_description(self):
        result = deterministic_fallback("standalone feature", "")
        assert _has_boundary(result) and _has_error(result), result

    def test_fallback_returns_at_least_three_criteria(self):
        result = deterministic_fallback("standalone feature", "")
        assert len(result) >= 3, result

    def test_fallback_criteria_are_all_strings(self):
        result = deterministic_fallback("standalone feature", "does a thing")
        assert all(isinstance(c, str) for c in result)


class TestEnsureCoverageGuarantee:
    """_ensure_boundary_and_error_coverage injects missing coverage, is
    idempotent, and never removes existing criteria."""

    def test_empty_list_gets_both_injected(self):
        out = _ensure_boundary_and_error_coverage([], title="feature x")
        assert _has_boundary(out) and _has_error(out), out

    def test_never_shrinks_input(self):
        base = ["File exists: src/x.py", "pytest: tests/test_x.py"]
        out = _ensure_boundary_and_error_coverage(base, title="feature x")
        assert len(out) >= len(base)

    def test_idempotent(self):
        base = ["File exists: src/x.py"]
        once = _ensure_boundary_and_error_coverage(base, title="feature x")
        twice = _ensure_boundary_and_error_coverage(once, title="feature x")
        assert once == twice

    def test_does_not_double_inject_when_present(self):
        base = [
            "pytest: tests/test_x_boundary.py — empty input returns a "
            "well-defined result (boundary case)",
            "pytest: tests/test_x_error.py — invalid input raises ValueError "
            "(error path)",
        ]
        out = _ensure_boundary_and_error_coverage(base, title="feature x")
        assert out == base

    def test_preserves_existing_criteria(self):
        base = ["File exists: src/x.py", "integration: bob.x"]
        out = _ensure_boundary_and_error_coverage(base, title="feature x")
        for c in base:
            assert c in out

    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            _ensure_boundary_and_error_coverage("not a list", title="x")


class TestFallbackErrorContract:
    """Degenerate titles must raise rather than emit a reward-hackable spec."""

    def test_empty_title_raises(self):
        with pytest.raises(ValueError):
            deterministic_fallback("", "desc")

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError):
            deterministic_fallback("   ", "desc")

    def test_non_string_title_raises(self):
        with pytest.raises(TypeError):
            deterministic_fallback(None, "desc")  # type: ignore[arg-type]
