"""Tests for tests_pass_regression_vs_baseline_must_attribute_failures.

Feature b2d4c211-3236-4355-96dd-e2af73b60a7d

Verifies that the regression-vs-baseline gate correctly attributes failing
tests to their owning feature, so sibling-feature test stubs do not gate-block
the currently-verifying feature.
"""
from __future__ import annotations

import importlib

import pytest


MODULE_NAME = "bob.tests_pass_regression_vs_baseline_must_attribute_failures"
FUNCTION_NAME = "tests_pass_regression_vs_baseline_must_attribute_failures"

CURRENT_FEATURE = "b2d4c211-3236-4355-96dd-e2af73b60a7d"
SIBLING_FEATURE = "73879589-0000-0000-0000-000000000000"


def _get_fn():
    mod = importlib.import_module(MODULE_NAME)
    return getattr(mod, FUNCTION_NAME)


def test_tests_pass_regression_vs_baseline_must_attribute_failures():
    """Module importable and function callable — canonical AC."""
    fn = _get_fn()
    assert callable(fn)
    # Verify it returns a tuple of (attributable, non_attributable)
    attributable, non_attributable = fn(
        failing_tests=[],
        current_feature_id=CURRENT_FEATURE,
    )
    assert isinstance(attributable, list)
    assert isinstance(non_attributable, list)


class TestSiblingRegressionNotGating:
    """Sibling-feature failing tests must be excluded from the gate result."""

    def test_sibling_tests_not_counted_against_current(self):
        fn = _get_fn()
        sibling_tests = [
            f"tests/{SIBLING_FEATURE}/test_ac_12.py::test_stub",
            f"tests/{SIBLING_FEATURE}/test_broken.py::test_x",
        ]
        attributable, non_attributable = fn(
            failing_tests=sibling_tests,
            current_feature_id=CURRENT_FEATURE,
        )
        assert attributable == [], "Sibling tests must NOT be attributable to the current feature"
        assert sorted(non_attributable) == sorted(sibling_tests)

    def test_orphan_tests_not_counted_against_current(self):
        fn = _get_fn()
        orphan_tests = [
            "tests/test_contract_grammar_emits_runnable_decorators.py::test_foo",
            "tests/test_f061_create_lesson_from_bug.py::test_bar",
        ]
        attributable, non_attributable = fn(
            failing_tests=orphan_tests,
            current_feature_id=CURRENT_FEATURE,
        )
        assert attributable == []
        assert sorted(non_attributable) == sorted(orphan_tests)

    def test_own_tests_counted_against_current(self):
        fn = _get_fn()
        own_tests = [
            f"tests/{CURRENT_FEATURE}/test_ac_1.py::test_works",
        ]
        attributable, non_attributable = fn(
            failing_tests=own_tests,
            current_feature_id=CURRENT_FEATURE,
        )
        assert sorted(attributable) == sorted(own_tests)
        assert non_attributable == []

    def test_mixed_returns_only_own(self):
        fn = _get_fn()
        sibling_tests = [f"tests/{SIBLING_FEATURE}/test_broken.py::test_x"]
        own_tests = [f"tests/{CURRENT_FEATURE}/test_ac_1.py::test_works"]
        orphan_tests = ["tests/test_orphan.py::test_y"]
        all_failing = sibling_tests + own_tests + orphan_tests
        attributable, non_attributable = fn(
            failing_tests=all_failing,
            current_feature_id=CURRENT_FEATURE,
        )
        assert sorted(attributable) == sorted(own_tests)
        assert sorted(non_attributable) == sorted(sibling_tests + orphan_tests)

    def test_empty_failing_tests(self):
        fn = _get_fn()
        attributable, non_attributable = fn(
            failing_tests=[],
            current_feature_id=CURRENT_FEATURE,
        )
        assert attributable == []
        assert non_attributable == []

    def test_returns_tuple_of_two_lists(self):
        fn = _get_fn()
        result = fn(failing_tests=[], current_feature_id=CURRENT_FEATURE)
        assert isinstance(result, tuple)
        assert len(result) == 2
        attributable, non_attributable = result
        assert isinstance(attributable, list)
        assert isinstance(non_attributable, list)
