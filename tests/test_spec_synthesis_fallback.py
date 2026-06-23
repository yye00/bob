"""Tests for bob3.spec_synthesis.deterministic_fallback and
bob3.spec_synthesis.ensure_boundary_and_error_coverage.

AC: pytest: tests/test_spec_synthesis_fallback.py
    integration: bob3.spec_synthesis
"""
from __future__ import annotations

import re

import pytest

from bob3.spec_synthesis import (
    deterministic_fallback,
    ensure_boundary_and_error_coverage,
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


class TestDeterministicFallbackViaSpecSynthesis:
    """deterministic_fallback is accessible via bob3.spec_synthesis and works correctly."""

    def test_import_deterministic_fallback(self):
        """Function is importable from bob3.spec_synthesis."""
        from bob3.spec_synthesis import deterministic_fallback as df
        assert callable(df)

    def test_returns_list(self):
        result = deterministic_fallback("my feature", "does a thing")
        assert isinstance(result, list)

    def test_returns_at_least_three_criteria(self):
        result = deterministic_fallback("my feature", "does a thing")
        assert len(result) >= 3, result

    def test_includes_boundary_ac(self):
        result = deterministic_fallback("my feature", "does a thing")
        assert any(_BND.search(c) for c in result), (
            f"No boundary AC in fallback result: {result}"
        )

    def test_includes_error_ac(self):
        result = deterministic_fallback("my feature", "does a thing")
        assert any(_ERR.search(c) for c in result), (
            f"No error-path AC in fallback result: {result}"
        )

    def test_composite_cannot_be_zero(self):
        """Both boundary and error ACs must be present so the geometric mean > 0."""
        result = deterministic_fallback("my feature", "does a thing")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd and has_err, (
            f"Missing sub-metric coverage — boundary={has_bnd} error={has_err}: {result}"
        )

    def test_empty_description_still_produces_boundary_and_error(self):
        result = deterministic_fallback("empty desc feature", "")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, f"No boundary AC with empty description: {result}"
        assert has_err, f"No error AC with empty description: {result}"

    def test_idempotent(self):
        first = deterministic_fallback("idempotent feature", "A stable thing.")
        second = deterministic_fallback("idempotent feature", "A stable thing.")
        assert first == second

    def test_empty_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback("", "description")

    def test_whitespace_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback("   ", "description")

    def test_none_title_raises(self):
        with pytest.raises((TypeError, ValueError)):
            deterministic_fallback(None, "description")  # type: ignore[arg-type]

    def test_extra_kwargs_silently_ignored(self):
        result = deterministic_fallback(
            "kwargs feature", "", workspace="/tmp", project_context="ctx"
        )
        assert isinstance(result, list)
        assert len(result) >= 3


class TestEnsureBoundaryAndErrorCoverageViaSpecSynthesis:
    """ensure_boundary_and_error_coverage is accessible via bob3.spec_synthesis."""

    def test_import_ensure_boundary_and_error_coverage(self):
        from bob3.spec_synthesis import ensure_boundary_and_error_coverage as fn
        assert callable(fn)

    def test_injects_boundary_when_missing(self):
        criteria = ["File exists: src/bob3/thing.py", "pytest: tests/test_thing.py"]
        result = ensure_boundary_and_error_coverage(criteria, title="thing")
        assert any(_BND.search(c) for c in result), (
            f"No boundary AC injected: {result}"
        )

    def test_injects_error_when_missing(self):
        criteria = ["File exists: src/bob3/thing.py", "pytest: tests/test_thing.py"]
        result = ensure_boundary_and_error_coverage(criteria, title="thing")
        assert any(_ERR.search(c) for c in result), (
            f"No error AC injected: {result}"
        )

    def test_does_not_shrink_criteria(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob3.foo.foo",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        assert len(result) >= len(criteria)

    def test_idempotent_on_already_covered_criteria(self):
        criteria = ["File exists: src/bob3/bar.py", "pytest: tests/test_bar.py"]
        first = ensure_boundary_and_error_coverage(criteria, title="bar")
        second = ensure_boundary_and_error_coverage(first, title="bar")
        assert len(second) == len(first), (
            f"Double-injection on second call: {second}"
        )

    def test_empty_list_injects_both(self):
        result = ensure_boundary_and_error_coverage([], title="some feature")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd and has_err, f"Missing coverage on empty list: {result}"

    def test_non_list_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            ensure_boundary_and_error_coverage("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            ensure_boundary_and_error_coverage(None, title="foo")  # type: ignore[arg-type]
