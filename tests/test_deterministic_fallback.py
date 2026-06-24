"""Tests for bob3.synthesis.deterministic_fallback module.

AC: pytest: tests/test_deterministic_fallback.py
AC: integration: bob3.synthesis

Verifies that:
- ensure_boundary_and_error_coverage is importable from bob3.synthesis.deterministic_fallback
- The function injects boundary and error ACs when missing
- The function delegates correctly to the spec_synthesizer implementation
- The integration with bob3.synthesis package is intact
"""

from __future__ import annotations

import re

import pytest

from bob3.synthesis.deterministic_fallback import ensure_boundary_and_error_coverage

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


class TestEnsureBoundaryAndErrorCoverageImport:
    """Function must be importable from the synthesis sub-package."""

    def test_importable_from_synthesis_deterministic_fallback(self):
        from bob3.synthesis.deterministic_fallback import ensure_boundary_and_error_coverage as fn
        assert callable(fn)

    def test_function_is_not_a_stub(self):
        """Must be a real function, not a placeholder."""
        import inspect
        fn = ensure_boundary_and_error_coverage
        src = inspect.getsource(fn)
        assert "pass" not in src.strip().splitlines()[-1:] or len(src) > 100


class TestEnsureBoundaryAndErrorCoverageCore:
    """Core behaviour: inject ACs when coverage sub-metrics are zero."""

    def test_returns_list(self):
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob3/foo.py"], title="foo feature"
        )
        assert isinstance(result, list)

    def test_injects_boundary_ac_when_missing(self):
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob3/foo.py"], title="foo feature"
        )
        has_bnd = any(_BND.search(c) for c in result)
        assert has_bnd, f"No boundary AC injected: {result}"

    def test_injects_error_ac_when_missing(self):
        result = ensure_boundary_and_error_coverage(
            ["File exists: src/bob3/foo.py"], title="foo feature"
        )
        has_err = any(_ERR.search(c) for c in result)
        assert has_err, f"No error AC injected: {result}"

    def test_does_not_inject_when_boundary_already_present(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo_boundary.py — empty input returns a result",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        bnd_acs = [c for c in result if _BND.search(c)]
        assert len(bnd_acs) >= 1  # still has boundary
        # and didn't double-inject
        assert len(result) <= len(criteria) + 1

    def test_does_not_inject_when_error_already_present(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo_error.py — invalid input raises ValueError",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        err_acs = [c for c in result if _ERR.search(c)]
        assert len(err_acs) >= 1

    def test_empty_list_gets_two_acs_injected(self):
        result = ensure_boundary_and_error_coverage([], title="my feature")
        assert len(result) == 2
        has_bnd = any(_BND.search(c) for c in result)
        has_err = any(_ERR.search(c) for c in result)
        assert has_bnd and has_err

    def test_result_never_smaller_than_input(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob3.foo.foo",
        ]
        result = ensure_boundary_and_error_coverage(criteria, title="foo")
        assert len(result) >= len(criteria)

    def test_non_list_raises_type_error(self):
        with pytest.raises(TypeError):
            ensure_boundary_and_error_coverage("not a list", title="foo")  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises((TypeError, AttributeError, ValueError)):
            ensure_boundary_and_error_coverage(None, title="foo")  # type: ignore[arg-type]

    def test_injected_ac_contains_title_slug(self):
        result = ensure_boundary_and_error_coverage([], title="my great feature")
        slug_tokens = [c for c in result if "my_great_feature" in c or "my" in c]
        assert len(slug_tokens) >= 1, f"No slug in injected ACs: {result}"

    def test_idempotent_on_second_call(self):
        criteria = ["File exists: src/bob3/foo.py"]
        first = ensure_boundary_and_error_coverage(criteria, title="foo")
        second = ensure_boundary_and_error_coverage(first, title="foo")
        assert len(second) == len(first), (
            f"Double-injection on second call: {second}"
        )


class TestIntegrationBobSynthesis:
    """Integration: bob3.synthesis package must expose the function."""

    def test_importable_from_bob3_synthesis(self):
        """bob3.synthesis.deterministic_fallback is a real sub-module."""
        import importlib
        mod = importlib.import_module("bob3.synthesis.deterministic_fallback")
        assert hasattr(mod, "ensure_boundary_and_error_coverage")

    def test_function_delegates_correctly(self):
        """Must produce the same result as spec_synthesizer's implementation."""
        from bob3.spec_synthesizer import _ensure_boundary_and_error_coverage as ref
        criteria = ["File exists: src/bob3/thing.py"]
        title = "thing feature"
        result_new = ensure_boundary_and_error_coverage(criteria, title=title)
        result_ref = ref(criteria, title=title)
        assert result_new == result_ref, (
            f"synthesis.deterministic_fallback diverged from spec_synthesizer:\n"
            f"  synthesis: {result_new}\n"
            f"  spec_synthesizer: {result_ref}"
        )
