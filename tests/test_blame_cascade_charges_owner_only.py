"""Tests: charge_refinement charges the owner of a failing test only."""

import pytest
from bob.orchestrator.blame_cascade import (
    find_owner_feature,
    charge_refinement,
)


def _make_feature(fid: str, pytest_paths: list[str]) -> dict:
    acs = [f"pytest: {p}" for p in pytest_paths] + ["File exists: src/foo.py"]
    return {"id": fid, "acceptance_criteria": acs}


class TestFindOwnerFeature:
    def test_finds_owner_for_exact_file_match(self):
        features = [
            _make_feature("feat-a", ["tests/test_alpha.py"]),
            _make_feature("feat-b", ["tests/test_beta.py"]),
        ]
        owner = find_owner_feature(
            failing_test="tests/test_alpha.py::test_something",
            all_features=features,
        )
        assert owner == "feat-a"

    def test_finds_owner_for_second_feature(self):
        features = [
            _make_feature("feat-a", ["tests/test_alpha.py"]),
            _make_feature("feat-b", ["tests/test_beta.py"]),
        ]
        owner = find_owner_feature(
            failing_test="tests/test_beta.py::test_something",
            all_features=features,
        )
        assert owner == "feat-b"

    def test_finds_owner_by_exact_nodeid(self):
        features = [
            _make_feature("feat-x", ["tests/test_x.py::test_exact"]),
        ]
        owner = find_owner_feature(
            failing_test="tests/test_x.py::test_exact",
            all_features=features,
        )
        assert owner == "feat-x"

    def test_exact_nodeid_does_not_match_different_test_in_same_file(self):
        features = [
            _make_feature("feat-x", ["tests/test_x.py::test_exact"]),
        ]
        owner = find_owner_feature(
            failing_test="tests/test_x.py::test_other",
            all_features=features,
        )
        assert owner is None

    def test_returns_none_when_no_owner(self):
        features = [
            _make_feature("feat-a", ["tests/test_alpha.py"]),
        ]
        owner = find_owner_feature(
            failing_test="tests/test_unrelated.py::test_x",
            all_features=features,
        )
        assert owner is None


class TestChargeRefinement:
    def test_charges_owner_feature_once(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_alpha.py"])]
        result = charge_refinement(
            failing_tests=["tests/test_alpha.py::test_one"],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged == ["feat-a"]
        assert result == 1

    def test_charges_each_unique_owner_once(self):
        charged = []
        features = [
            _make_feature("feat-a", ["tests/test_alpha.py"]),
            _make_feature("feat-b", ["tests/test_beta.py"]),
        ]
        result = charge_refinement(
            failing_tests=[
                "tests/test_alpha.py::test_one",
                "tests/test_alpha.py::test_two",
                "tests/test_beta.py::test_one",
            ],
            all_features=features,
            increment_fn=charged.append,
        )
        assert sorted(charged) == ["feat-a", "feat-b"]
        assert result == 2

    def test_does_not_charge_feature_multiple_times_for_multiple_failing_tests(self):
        charged = []
        features = [_make_feature("feat-a", ["tests/test_alpha.py"])]
        charge_refinement(
            failing_tests=[
                "tests/test_alpha.py::test_one",
                "tests/test_alpha.py::test_two",
                "tests/test_alpha.py::test_three",
            ],
            all_features=features,
            increment_fn=charged.append,
        )
        assert charged.count("feat-a") == 1
