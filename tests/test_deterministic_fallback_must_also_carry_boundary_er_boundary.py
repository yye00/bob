"""Boundary-case tests: deterministic_fallback with empty/zero/minimum inputs.

AC: pytest: tests/test_deterministic_fallback_must_also_carry_boundary_er_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising
    (boundary case)
"""
from __future__ import annotations

import re

import pytest

from bob.spec_synthesizer import (
    _ensure_boundary_and_error_coverage,
    deterministic_fallback,
    deterministic_fallback_spec,
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


class TestBoundaryCases:
    """Boundary inputs must return a well-defined result, never raise."""

    # ── deterministic_fallback with empty description ─────────────────────

    def test_empty_description_returns_list(self):
        """An empty description is a valid minimum input — must not raise."""
        result = deterministic_fallback("my feature", "")
        assert isinstance(result, list)

    def test_empty_description_produces_valid_criteria(self):
        result = deterministic_fallback("my feature", "")
        assert len(result) >= 3, result

    def test_empty_description_still_includes_boundary_ac(self):
        result = deterministic_fallback("my feature", "")
        has_bnd = any(_BND.search(c) for c in result)
        assert has_bnd, f"No boundary AC with empty description: {result}"

    def test_empty_description_still_includes_error_ac(self):
        result = deterministic_fallback("my feature", "")
        has_err = any(_ERR.search(c) for c in result)
        assert has_err, f"No error AC with empty description: {result}"

    # ── deterministic_fallback with whitespace-only description ───────────

    def test_whitespace_only_description_does_not_raise(self):
        result = deterministic_fallback("whitespace feature", "   \t\n  ")
        assert isinstance(result, list)
        assert len(result) >= 3

    # ── deterministic_fallback with single-word description ───────────────

    def test_single_word_description_does_not_raise(self):
        result = deterministic_fallback("tiny feature", "Short.")
        assert isinstance(result, list)
        assert len(result) >= 3

    # ── _ensure_boundary_and_error_coverage with empty list ───────────────

    def test_ensure_coverage_empty_list_does_not_raise(self):
        """Minimum input to the injector: empty criteria list."""
        result = _ensure_boundary_and_error_coverage([], title="some feature")
        assert isinstance(result, list)

    def test_ensure_coverage_empty_list_injects_both(self):
        result = _ensure_boundary_and_error_coverage([], title="some feature")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, f"No boundary AC injected for empty list: {result}"
        assert has_err, f"No error AC injected for empty list: {result}"

    def test_ensure_coverage_empty_title_does_not_raise(self):
        """Empty title is a boundary input; must not raise, must use fallback slug."""
        result = _ensure_boundary_and_error_coverage(
            ["File exists: src/bob/foo.py"],
            title="",
        )
        assert isinstance(result, list)

    def test_ensure_coverage_single_criterion_does_not_raise(self):
        """Minimum non-empty input: list with one AC."""
        result = _ensure_boundary_and_error_coverage(
            ["File exists: src/bob/thing.py"],
            title="thing",
        )
        assert isinstance(result, list)
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, result
        assert has_err, result

    # ── deterministic_fallback_spec boundary cases ─────────────────────────

    def test_fallback_spec_empty_description_does_not_raise(self):
        spec = deterministic_fallback_spec("spec feature", "")
        assert isinstance(spec, dict)
        assert "acceptance_criteria" in spec
        assert isinstance(spec["acceptance_criteria"], list)

    # ── Extra kwargs must be silently ignored ─────────────────────────────

    def test_extra_kwargs_are_accepted_without_raising(self):
        result = deterministic_fallback(
            "kwargs feature",
            "",
            workspace="/tmp",
            project_context="ctx",
            unknown_future_param="ignored",
        )
        assert isinstance(result, list)

    # ── All-stop-word title raises ValueError (known boundary refusal) ────

    def test_all_stopword_title_raises_value_error(self):
        """A title composed entirely of stop-words has no usable slug and
        must raise ValueError rather than emit a reward-hackable weak spec."""
        with pytest.raises(ValueError):
            deterministic_fallback("the a an for to of", "")

    def test_empty_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback("", "")

    def test_whitespace_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback("   \t\n  ", "Some description.")

    # ── Repeated calls are idempotent ─────────────────────────────────────

    def test_repeated_calls_return_same_result(self):
        first = deterministic_fallback("idempotent feature", "A stable feature.")
        second = deterministic_fallback("idempotent feature", "A stable feature.")
        assert first == second, f"Non-idempotent: {first} vs {second}"

    def test_ensure_coverage_repeated_calls_are_idempotent(self):
        criteria = ["File exists: src/bob/bar.py", "pytest: tests/test_bar.py"]
        first = _ensure_boundary_and_error_coverage(criteria, title="bar")
        second = _ensure_boundary_and_error_coverage(first, title="bar")
        # Applying again must not add duplicates — already has both ACs.
        assert len(second) == len(first), (
            f"Double-injection on second call: {second}"
        )
