"""Tests that sibling-feature regressions do NOT gate-block the current feature.

AC-12: asserts current feature 9b2e1060 NOT gate-blocked when sibling 73879589's
test stubs regress.

This reproduces the exact failure mode described in feature 8add91fb:
Feature 9b2e1060 was demoted to NH because the regression-vs-baseline check
counted 7 failing tests from sibling feature 73879589 against it.
"""
from __future__ import annotations

import pytest

from bob3.verification.regression_attribution import (
    filter_attributable_failures,
    is_attributable_to_current_feature,
    owning_feature_for_test,
)

# Real feature IDs from the bug report
CURRENT_FEATURE = "9b2e1060-0000-0000-0000-000000000000"
SIBLING_FEATURE = "73879589-0000-0000-0000-000000000000"

# Sibling's test stubs that were regressing (uses the directory convention)
SIBLING_TESTS = [
    f"tests/{SIBLING_FEATURE}/test_ac_12_pytest_tests_test_contract_grammar_blame.py::test_stub",
    f"tests/{SIBLING_FEATURE}/test_contract_grammar_blame_attribution.py::test_broken",
]

# Top-level tests from prior features (no UUID subdir — orphan tests)
ORPHAN_TESTS = [
    "tests/test_contract_grammar_emits_runnable_decorators.py::test_foo",
    "tests/test_f061_create_lesson_from_bug.py::test_bar",
]

# Current feature's own tests
OWN_TESTS = [
    f"tests/{CURRENT_FEATURE}/test_ac_1.py::test_works",
]


class TestSiblingTestsNotAttributableToCurrent:
    """is_attributable_to_current_feature returns False for sibling tests."""

    def test_sibling_subtree_test_not_attributable(self):
        for test_path in SIBLING_TESTS:
            result = is_attributable_to_current_feature(test_path, CURRENT_FEATURE)
            assert result is False, (
                f"Sibling test {test_path!r} must NOT be attributable to current feature"
            )

    def test_orphan_top_level_test_not_attributable(self):
        for test_path in ORPHAN_TESTS:
            result = is_attributable_to_current_feature(test_path, CURRENT_FEATURE)
            assert result is False, (
                f"Orphan test {test_path!r} must NOT be attributable to current feature"
            )

    def test_own_tests_are_attributable(self):
        for test_path in OWN_TESTS:
            result = is_attributable_to_current_feature(test_path, CURRENT_FEATURE)
            assert result is True, (
                f"Own test {test_path!r} MUST be attributable to current feature"
            )


class TestFilterAttributableFailures:
    """filter_attributable_failures removes sibling and orphan failures."""

    def test_sibling_failures_are_filtered_out(self):
        failing = SIBLING_TESTS + OWN_TESTS
        events = []

        def emit(event_type, **kwargs):
            events.append({"type": event_type, **kwargs})

        result = filter_attributable_failures(
            failing,
            CURRENT_FEATURE,
            _emit_event_fn=emit,
        )
        assert result == OWN_TESTS, (
            "Sibling-feature tests must be removed from the gate result"
        )

    def test_orphan_failures_are_filtered_out(self):
        failing = ORPHAN_TESTS + OWN_TESTS
        result = filter_attributable_failures(failing, CURRENT_FEATURE)
        assert result == OWN_TESTS

    def test_all_sibling_orphan_no_own_failures_yields_empty(self):
        """If ALL failing tests are siblings/orphans, current feature is NOT gate-blocked."""
        failing = SIBLING_TESTS + ORPHAN_TESTS
        result = filter_attributable_failures(failing, CURRENT_FEATURE)
        assert result == [], (
            "When no failing test belongs to the current feature, "
            "it must not be gate-blocked"
        )

    def test_exact_bug_scenario_9b2e1060_not_blocked_by_73879589(self):
        """Reproduce the exact bug: 9b2e1060 NH-demoted because of 73879589 stubs."""
        all_failing = SIBLING_TESTS + ORPHAN_TESTS
        result = filter_attributable_failures(all_failing, CURRENT_FEATURE)
        assert len(result) == 0, (
            "9b2e1060 must have zero attributable failures — "
            "all 7 failing tests belong to sibling/orphan"
        )

    def test_mixed_returns_only_own(self):
        all_failing = SIBLING_TESTS + ORPHAN_TESTS + OWN_TESTS
        result = filter_attributable_failures(all_failing, CURRENT_FEATURE)
        assert sorted(result) == sorted(OWN_TESTS)


class TestOwnerResolutionForSiblingTests:
    """owning_feature_for_test correctly resolves sibling tests to sibling feature."""

    def test_sibling_test_resolves_to_sibling_id(self):
        for test_path in SIBLING_TESTS:
            owner = owning_feature_for_test(test_path)
            assert owner == SIBLING_FEATURE, (
                f"Test {test_path!r} must resolve to sibling feature {SIBLING_FEATURE}"
            )

    def test_own_test_resolves_to_current_feature(self):
        for test_path in OWN_TESTS:
            owner = owning_feature_for_test(test_path)
            assert owner == CURRENT_FEATURE
