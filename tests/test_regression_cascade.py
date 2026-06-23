"""Tests for blame-the-cause regression cascade — charge the breaking feature.

Feature e935afb1-e29b-42ce-a39d-8cec684f239a

For each failing test, the AC table is walked to find the feature whose
``pytest:`` AC owns that test path. Refinement attempts are charged only to
that owning feature. Features that merely ran during the same verification
but don't own any failing test stay at their pre-verification status.
"""

from __future__ import annotations

import pytest

from test_regression import blame_the_cause, charge_refinement_attempt, OrphanTestError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_feature_set():
    return [
        {
            "id": "feat-alpha",
            "acceptance_criteria": [
                "pytest: tests/test_alpha.py",
                "Function defined: src/alpha.py",
            ],
            "status": "in_progress",
        },
        {
            "id": "feat-beta",
            "acceptance_criteria": [
                "pytest: tests/test_beta.py",
            ],
            "status": "in_progress",
        },
    ]


@pytest.fixture
def multi_feature_set():
    return [
        {
            "id": "feat-a",
            "acceptance_criteria": ["pytest: tests/test_a.py"],
            "status": "completed",
        },
        {
            "id": "feat-b",
            "acceptance_criteria": ["pytest: tests/test_b.py"],
            "status": "in_progress",
        },
        {
            "id": "feat-c",
            "acceptance_criteria": ["File exists: src/c.py"],
            "status": "in_progress",
        },
    ]


# ---------------------------------------------------------------------------
# blame_the_cause — basic attribution
# ---------------------------------------------------------------------------

class TestBlameTheCause:
    def test_returns_owning_feature_id(self, two_feature_set):
        result = blame_the_cause(
            failing_test="tests/test_alpha.py::test_one",
            all_features=two_feature_set,
        )
        assert result == "feat-alpha"

    def test_returns_none_when_no_owner(self, two_feature_set):
        result = blame_the_cause(
            failing_test="tests/test_orphan.py::test_x",
            all_features=two_feature_set,
        )
        assert result is None

    def test_matches_second_feature(self, two_feature_set):
        result = blame_the_cause(
            failing_test="tests/test_beta.py::test_two",
            all_features=two_feature_set,
        )
        assert result == "feat-beta"

    def test_ignores_non_pytest_acs(self, multi_feature_set):
        # feat-c has only a "File exists" AC, so any test should return None
        result = blame_the_cause(
            failing_test="tests/test_c.py::test_something",
            all_features=multi_feature_set,
        )
        assert result is None

    def test_strict_raises_orphan_error(self, two_feature_set):
        with pytest.raises(OrphanTestError):
            blame_the_cause(
                failing_test="tests/test_unowned.py::test_x",
                all_features=two_feature_set,
                strict=True,
            )

    def test_strict_does_not_raise_when_owner_found(self, two_feature_set):
        result = blame_the_cause(
            failing_test="tests/test_alpha.py::test_one",
            all_features=two_feature_set,
            strict=True,
        )
        assert result == "feat-alpha"

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            blame_the_cause(failing_test="", all_features=[])

    def test_whitespace_string_raises_value_error(self):
        with pytest.raises(ValueError):
            blame_the_cause(failing_test="   ", all_features=[])

    def test_empty_features_returns_none(self):
        result = blame_the_cause(
            failing_test="tests/test_a.py::test_x",
            all_features=[],
        )
        assert result is None


# ---------------------------------------------------------------------------
# charge_refinement_attempt — charging owning features
# ---------------------------------------------------------------------------

class TestChargeRefinementAttempt:
    def test_charges_owning_feature_once(self, two_feature_set):
        charged = []
        count = charge_refinement_attempt(
            failing_tests=["tests/test_alpha.py::test_one"],
            all_features=two_feature_set,
            increment_fn=charged.append,
        )
        assert count == 1
        assert charged == ["feat-alpha"]

    def test_does_not_charge_innocent_features(self, two_feature_set):
        charged = []
        count = charge_refinement_attempt(
            failing_tests=["tests/test_alpha.py::test_one"],
            all_features=two_feature_set,
            increment_fn=charged.append,
        )
        assert "feat-beta" not in charged
        assert count == 1

    def test_charges_each_unique_owner_once(self, two_feature_set):
        charged = []
        count = charge_refinement_attempt(
            failing_tests=[
                "tests/test_alpha.py::test_one",
                "tests/test_alpha.py::test_two",
                "tests/test_beta.py::test_three",
            ],
            all_features=two_feature_set,
            increment_fn=charged.append,
        )
        assert count == 2
        assert sorted(charged) == ["feat-alpha", "feat-beta"]

    def test_multiple_failing_tests_same_owner_charged_once(self, two_feature_set):
        charged = []
        count = charge_refinement_attempt(
            failing_tests=[
                "tests/test_alpha.py::test_one",
                "tests/test_alpha.py::test_two",
                "tests/test_alpha.py::test_three",
            ],
            all_features=two_feature_set,
            increment_fn=charged.append,
        )
        assert count == 1
        assert charged == ["feat-alpha"]

    def test_empty_failing_tests_charges_nothing(self, two_feature_set):
        charged = []
        count = charge_refinement_attempt(
            failing_tests=[],
            all_features=two_feature_set,
            increment_fn=charged.append,
        )
        assert count == 0
        assert charged == []

    def test_unowned_test_calls_unowned_record_fn(self, two_feature_set):
        orphans = []
        charge_refinement_attempt(
            failing_tests=["tests/test_orphan.py::test_x"],
            all_features=two_feature_set,
            increment_fn=lambda x: None,
            unowned_record_fn=orphans.append,
        )
        assert len(orphans) == 1
        assert orphans[0]["type"] == "unattributed_failure"
        assert orphans[0]["failing_test"] == "tests/test_orphan.py::test_x"

    def test_non_list_failing_tests_raises_value_error(self):
        with pytest.raises(ValueError):
            charge_refinement_attempt(
                failing_tests="tests/test_a.py::test_x",
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_none_failing_tests_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            charge_refinement_attempt(
                failing_tests=None,
                all_features=[],
                increment_fn=lambda x: None,
            )

    def test_empty_features_charges_nothing(self):
        charged = []
        count = charge_refinement_attempt(
            failing_tests=["tests/test_a.py::test_x"],
            all_features=[],
            increment_fn=charged.append,
        )
        assert count == 0
        assert charged == []

    def test_completed_feature_status_preserved_when_innocent(self, multi_feature_set):
        # feat-b's test is failing; feat-a (completed) owns different test — not charged
        charged = []
        count = charge_refinement_attempt(
            failing_tests=["tests/test_b.py::test_x"],
            all_features=multi_feature_set,
            increment_fn=charged.append,
        )
        assert count == 1
        assert "feat-a" not in charged
        assert "feat-c" not in charged

    def test_mixed_owned_and_unowned_tests(self, two_feature_set):
        orphans = []
        charged = []
        count = charge_refinement_attempt(
            failing_tests=[
                "tests/test_alpha.py::test_owned",
                "tests/test_unowned.py::test_orphan",
            ],
            all_features=two_feature_set,
            increment_fn=charged.append,
            unowned_record_fn=orphans.append,
        )
        assert count == 1
        assert charged == ["feat-alpha"]
        assert len(orphans) == 1
