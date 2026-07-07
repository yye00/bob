"""AC tests for bob.deterministic_fallback boundary + error-path coverage.

Feature 6122be62: the deterministic fallback path MUST apply the same
_ensure_boundary_and_error_coverage guarantee the LLM synthesis path gets, so
EITHER path yields gate-passing ACs (composite spec_quality_score > 0.0).

ACs covered:
    File exists: src/bob/deterministic_fallback.py
    Function defined: bob.deterministic_fallback.deterministic_fallback
    Function defined: bob.deterministic_fallback._ensure_boundary_and_error_coverage
"""
from __future__ import annotations

import re

import pytest

import bob.deterministic_fallback as mod
from bob.deterministic_fallback import (
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


class TestSymbolsDefined:
    def test_deterministic_fallback_is_callable(self):
        assert callable(deterministic_fallback)

    def test_ensure_coverage_is_callable(self):
        assert callable(_ensure_boundary_and_error_coverage)

    def test_symbols_are_exported(self):
        assert "deterministic_fallback" in mod.__all__
        assert "_ensure_boundary_and_error_coverage" in mod.__all__


class TestFallbackCarriesBoundaryAndError:
    """The core behaviour: fallback ACs must include a boundary AC and an
    error-path AC so the composite geometric mean can exceed 0.0."""

    def test_fallback_includes_boundary_ac(self):
        result = deterministic_fallback("my feature", "Does something useful.")
        assert any(_BND.search(c) for c in result), f"No boundary AC: {result}"

    def test_fallback_includes_error_ac(self):
        result = deterministic_fallback("my feature", "Does something useful.")
        assert any(_ERR.search(c) for c in result), f"No error AC: {result}"

    def test_fallback_returns_at_least_three_criteria(self):
        result = deterministic_fallback("my feature", "Does something useful.")
        assert isinstance(result, list)
        assert len(result) >= 3, result

    def test_empty_description_still_carries_both(self):
        result = deterministic_fallback("empty desc feature", "")
        assert any(_BND.search(c) for c in result), result
        assert any(_ERR.search(c) for c in result), result


class TestEnsureCoverageInjectsBoth:
    def test_empty_list_injects_boundary_and_error(self):
        result = _ensure_boundary_and_error_coverage([], title="some feature")
        assert any(_BND.search(c) for c in result), result
        assert any(_ERR.search(c) for c in result), result

    def test_result_never_smaller_than_input(self):
        criteria = ["File exists: src/bob/foo.py", "pytest: tests/test_foo.py"]
        result = _ensure_boundary_and_error_coverage(criteria, title="foo")
        assert len(result) >= len(criteria), result

    def test_idempotent(self):
        criteria = ["File exists: src/bob/bar.py"]
        once = _ensure_boundary_and_error_coverage(criteria, title="bar")
        twice = _ensure_boundary_and_error_coverage(once, title="bar")
        assert len(twice) == len(once), (once, twice)


class TestErrorContract:
    def test_empty_title_raises(self):
        with pytest.raises(ValueError):
            deterministic_fallback("", "description")

    def test_non_string_title_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            deterministic_fallback(None, "description")  # type: ignore[arg-type]

    def test_ensure_coverage_non_list_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            _ensure_boundary_and_error_coverage("not a list", title="foo")  # type: ignore[arg-type]
