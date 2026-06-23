"""Error-path tests: deterministic_fallback raises ValueError for invalid inputs.

AC: pytest: tests/test_deterministic_fallback_must_also_carry_boundary_er_error.py
    — invalid input raises ValueError and the function does not silently succeed
    (error path)
"""
from __future__ import annotations

import pytest

from bob3.spec_synthesizer import (
    _ensure_boundary_and_error_coverage,
    deterministic_fallback,
    deterministic_fallback_spec,
)


class TestErrorPaths:
    """Invalid inputs must raise ValueError; the function must never silently
    succeed with a weak or empty spec when given un-processable arguments."""

    # ── Empty / whitespace / punctuation-only titles ───────────────────────

    def test_empty_string_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback("", "Some description.")

    def test_whitespace_only_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback("   \t\n  ", "Some description.")

    def test_punctuation_only_title_raises_value_error(self):
        """'---' collapses to no usable tokens → ValueError, not a weak spec."""
        with pytest.raises(ValueError):
            deterministic_fallback("---", "")

    def test_all_stop_words_title_raises_value_error(self):
        """Stop-word-only title has no valid slug: must refuse."""
        with pytest.raises(ValueError):
            deterministic_fallback("the a an for to of", "")

    # ── Python reserved keyword titles ────────────────────────────────────

    @pytest.mark.parametrize("kw", ["class", "import", "from", "def", "return", "lambda"])
    def test_reserved_keyword_title_raises_or_safe(self, kw: str):
        """Reserved keywords cannot produce an importable symbol — the function
        must raise ValueError OR return a safe spec without an un-importable AC."""
        import keyword
        try:
            criteria = deterministic_fallback(kw, "Does a thing.")
        except ValueError:
            return  # correct: refuses instead of emitting illegal symbol
        # If it didn't raise, verify no illegal Function-defined AC was emitted.
        fn_acs = [c for c in criteria if c.lower().startswith("function defined:")]
        for ac in fn_acs:
            body = ac.split(":", 1)[1].strip()
            symbol = body.rpartition(".")[2]
            assert symbol.isidentifier() and not keyword.iskeyword(symbol), (
                f"Reserved keyword {kw!r} produced illegal symbol {symbol!r}: {criteria}"
            )

    # ── Numeric / leading-digit titles ────────────────────────────────────

    @pytest.mark.parametrize("title", ["123", "456 789", "9lives"])
    def test_numeric_title_raises_or_safe(self, title: str):
        """Leading-digit identifiers are un-importable — must refuse or be safe."""
        try:
            criteria = deterministic_fallback(title, "Does a thing.")
        except ValueError:
            return
        fn_acs = [c for c in criteria if c.lower().startswith("function defined:")]
        for ac in fn_acs:
            body = ac.split(":", 1)[1].strip()
            symbol = body.rpartition(".")[2]
            assert not symbol[:1].isdigit(), (
                f"Title {title!r} produced digit-leading symbol {symbol!r}"
            )
            assert symbol.isidentifier(), (
                f"Title {title!r} produced non-identifier {symbol!r}"
            )

    # ── Non-string title ──────────────────────────────────────────────────

    def test_none_title_raises(self):
        """None is not a valid feature name."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            deterministic_fallback(None, "description")  # type: ignore[arg-type]

    def test_integer_title_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            deterministic_fallback(42, "description")  # type: ignore[arg-type]

    # ── _ensure_boundary_and_error_coverage error paths ──────────────────

    def test_ensure_coverage_non_list_raises(self):
        """criteria must be a list; a non-list input must not silently succeed."""
        with pytest.raises((TypeError, AttributeError, ValueError)):
            _ensure_boundary_and_error_coverage("not a list", title="foo")  # type: ignore[arg-type]

    def test_ensure_coverage_none_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            _ensure_boundary_and_error_coverage(None, title="foo")  # type: ignore[arg-type]

    def test_ensure_coverage_criteria_with_non_string_elements_raises(self):
        """Non-string elements in the criteria list must not silently produce
        garbage output; the function must raise rather than succeed incorrectly."""
        with pytest.raises((TypeError, AttributeError)):
            _ensure_boundary_and_error_coverage([None, 42], title="foo")  # type: ignore[list-item]

    # ── deterministic_fallback_spec error paths ───────────────────────────

    def test_fallback_spec_empty_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback_spec("", "description")

    def test_fallback_spec_whitespace_title_raises_value_error(self):
        with pytest.raises(ValueError):
            deterministic_fallback_spec("   ", "description")

    # ── Result is never silently an empty list ────────────────────────────

    def test_valid_input_does_not_return_empty_list(self):
        """Sanity check: a valid input must not silently return [] — if it
        cannot produce criteria it must raise, not return an empty list."""
        result = deterministic_fallback("valid feature name", "A valid description.")
        assert len(result) > 0, (
            "deterministic_fallback returned an empty list for a valid input — "
            "must raise ValueError instead of silently succeeding with nothing."
        )

    def test_ensure_coverage_result_is_never_smaller_than_input(self):
        """The injector only adds ACs, never removes them; returning fewer
        elements than were passed in would be a silent data-loss bug."""
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob3.foo.foo",
        ]
        result = _ensure_boundary_and_error_coverage(criteria, title="foo")
        assert len(result) >= len(criteria), (
            f"Injector dropped criteria: got {len(result)} from {len(criteria)}: {result}"
        )
