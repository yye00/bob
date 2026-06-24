"""Tests for bob.spec_synthesis.ensure_boundary_and_error_coverage.

Verifies that the public API in bob.spec_synthesis correctly delegates
to the deterministic fallback's boundary/error-coverage guarantee so that
EITHER path (live LLM synthesis or fallback) yields gate-passing ACs.

AC: pytest: tests/test_spec_synthesis_deterministic_fallback.py
"""
from __future__ import annotations

import re

import pytest

from bob.spec_synthesis import ensure_boundary_and_error_coverage

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
    """Public API in bob.spec_synthesis must match spec_synthesizer behaviour."""

    def test_importable_from_spec_synthesis(self):
        """Function must be importable from bob.spec_synthesis (not just spec_synthesizer)."""
        from bob.spec_synthesis import ensure_boundary_and_error_coverage as fn
        assert callable(fn)

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

    def test_injects_nothing_when_boundary_already_present(self):
        criteria = [
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo_boundary.py — empty input returns empty list (boundary case)",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError (error path)",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo feature")
        assert len(result) == len(criteria), (
            f"Expected no injection when both already present, got extras: {result}"
        )

    def test_empty_criteria_list_injects_both(self):
        result = ensure_boundary_and_error_coverage([], title="empty feature")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd, f"No boundary AC for empty input: {result}"
        assert has_err, f"No error AC for empty input: {result}"

    def test_original_criteria_preserved(self):
        original = [
            "File exists: src/bob/foo.py",
            "Function defined: bob.foo.do_thing",
            "pytest: tests/test_foo.py",
        ]
        result = ensure_boundary_and_error_coverage(original, title="foo")
        for ac in original:
            assert ac in result, f"Original AC dropped: {ac!r} not in {result}"

    def test_result_never_smaller_than_input(self):
        criteria = [
            "File exists: src/bob/bar.py",
            "pytest: tests/test_bar.py",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="bar")
        assert len(result) >= len(criteria), (
            f"Injector dropped criteria: {len(result)} < {len(criteria)}: {result}"
        )

    def test_repeated_calls_are_idempotent(self):
        criteria = ["File exists: src/bob/baz.py", "pytest: tests/test_baz.py"]
        first = ensure_boundary_and_error_coverage(criteria, title="baz")
        second = ensure_boundary_and_error_coverage(first, title="baz")
        assert len(second) == len(first), (
            f"Double-injection on second call: {second}"
        )

    def test_empty_title_does_not_raise(self):
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob/thing.py"], title=""
        )
        assert isinstance(result, list)

    def test_non_list_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            ensure_boundary_and_error_coverage("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            ensure_boundary_and_error_coverage(None, title="foo")  # type: ignore[arg-type]

    def test_composite_would_pass_gate(self):
        """After injection the criteria list contains at least one boundary AC and
        one error-path AC — both sub-metrics in the geometric mean are non-zero,
        which is the gate-passing condition this feature guarantees."""
        criteria = [
            "File exists: src/bob/widget.py",
            "Function defined: bob.widget.process",
            "pytest: tests/test_widget.py",
            "integration: bob.widget",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="widget")
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd and has_err, (
            f"Gate would still be 0.0: bnd={has_bnd}, err={has_err}, result={result}"
        )

    def test_injected_acs_use_pytest_form(self):
        """Injected ACs must use the pytest: structured form (not prose behavior: ACs)
        so they raise spec_executability, traceability, and predicate_coverage too."""
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob/foo.py"], title="foo feature"
        )
        injected = [c for c in result if "boundary case" in c or "error path" in c]
        for ac in injected:
            assert ac.strip().lower().startswith("pytest:"), (
                f"Injected AC is not in pytest: form: {ac!r}"
            )
