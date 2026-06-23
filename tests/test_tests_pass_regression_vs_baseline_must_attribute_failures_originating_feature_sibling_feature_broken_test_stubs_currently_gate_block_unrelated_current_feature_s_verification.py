"""Tests for tests_pass_regression_vs_baseline_must_attribute_failures_originating_feature
regression attribution — sibling-feature stubs must not gate-block the current feature.

Feature a3c427e8-cc9d-447f-b7c4-5715abe95580

Verifies the canonical entry point that wraps the regression-vs-baseline gate so
failing tests belonging to sibling features (or orphan tests with no UUID subdir)
are excluded from the current feature's gate result.
"""
from __future__ import annotations

import importlib

import pytest


MODULE_NAME = (
    "bob3."
    "tests_pass_regression_vs_baseline_must_attribute_failures_originating_feature"
    "_sibling_feature_broken_test_stubs_currently_gate_block_unrelated_current"
    "_feature_s_verification"
)
FUNCTION_NAME = (
    "tests_pass_regression_vs_baseline_must_attribute_failures_originating_feature"
    "_sibling_feature_broken_test_stubs_currently_gate_block_unrelated_current"
    "_feature_s_verification"
)

CURRENT_FEATURE = "a3c427e8-cc9d-447f-b7c4-5715abe95580"
SIBLING_FEATURE = "73879589-0000-0000-0000-000000000000"


def _get_fn():
    mod = importlib.import_module(MODULE_NAME)
    return getattr(mod, FUNCTION_NAME)


def test_tests_pass_regression_vs_baseline_must_attribute_failures_originating_feature_sibling_feature_broken_test_stubs_currently_gate_block_unrelated_current_feature_s_verification():
    """Module importable and function callable — canonical AC."""
    fn = _get_fn()
    assert callable(fn)


class TestModuleAndFunction:
    """Module-level sanity checks."""

    def test_module_importable(self):
        mod = importlib.import_module(MODULE_NAME)
        assert mod is not None

    def test_function_defined(self):
        fn = _get_fn()
        assert callable(fn)


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
        assert attributable == [], (
            "Sibling tests must NOT be attributable to the current feature"
        )
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

    def test_exact_bug_scenario_9b2e1060_not_blocked(self):
        """Reproduce: 9b2e1060 NH-demoted because 73879589 stubs regressed."""
        fn = _get_fn()
        sibling_id = "9b2e1060-0000-0000-0000-000000000000"
        failing = [
            f"tests/{SIBLING_FEATURE}/test_ac_12_pytest_tests_test_contract_grammar_blame.py::test_stub",
            "tests/test_contract_grammar_emits_runnable_decorators.py::test_foo",
            "tests/test_f061_create_lesson_from_bug.py::test_bar",
        ]
        attributable, non_attributable = fn(
            failing_tests=failing,
            current_feature_id=sibling_id,
        )
        assert len(attributable) == 0, (
            "9b2e1060 must have zero attributable failures when all 7 belong to sibling/orphan"
        )

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

    def test_emit_fn_called_for_non_attributable(self):
        fn = _get_fn()
        events = []

        def emit(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        sibling_tests = [f"tests/{SIBLING_FEATURE}/test_broken.py::test_x"]
        fn(
            failing_tests=sibling_tests,
            current_feature_id=CURRENT_FEATURE,
            _emit_event_fn=emit,
        )
        assert len(events) > 0, "An event must be emitted for non-attributable tests"

    def test_all_features_kwarg_accepted(self):
        """all_features kwarg must be accepted for pytest-prefix AC strategy."""
        fn = _get_fn()
        features = [
            {
                "id": CURRENT_FEATURE,
                "acceptance_criteria": '["pytest: tests/special_test.py::test_special"]',
                "status": "executing",
            }
        ]
        own_tests = ["tests/special_test.py::test_special"]
        attributable, non_attributable = fn(
            failing_tests=own_tests,
            current_feature_id=CURRENT_FEATURE,
            all_features=features,
        )
        assert sorted(attributable) == sorted(own_tests)
        assert non_attributable == []
