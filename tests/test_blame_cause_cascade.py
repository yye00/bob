"""Tests for blame_cause_cascade — charge only the breaking feature.

Feature b6bfd8c2-254e-49ce-8c96-6dd28ee30c8e

For each failing test, walk the AC table to find the feature whose ``pytest:``
AC owns that test path. Charge a refinement attempt to that feature only.
Features that merely ran during the same verification but don't own any
failing test stay at their pre-verification status.
"""

from __future__ import annotations

import pytest

from bob.blame_cause_cascade import charge_breaking_feature


def _feat(fid: str, pytest_paths: list[str], status: str = "executing") -> dict:
    return {
        "id": fid,
        "acceptance_criteria": [f"pytest: {p}" for p in pytest_paths],
        "status": status,
    }


def test_charges_only_the_owning_feature():
    charged: list[str] = []
    features = [
        _feat("breaking", ["tests/test_breaking.py"]),
        _feat("innocent", ["tests/test_innocent.py"]),
    ]
    result = charge_breaking_feature(
        failing_tests=["tests/test_breaking.py::test_x"],
        all_features=features,
        increment_fn=charged.append,
    )
    assert result == 1
    assert charged == ["breaking"]


def test_innocent_feature_not_charged():
    charged: list[str] = []
    features = [
        _feat("breaking", ["tests/test_breaking.py"]),
        _feat("innocent", ["tests/test_innocent.py"]),
    ]
    charge_breaking_feature(
        failing_tests=["tests/test_breaking.py::test_x"],
        all_features=features,
        increment_fn=charged.append,
    )
    assert "innocent" not in charged


def test_owner_charged_once_for_multiple_failing_tests():
    charged: list[str] = []
    features = [_feat("owner", ["tests/test_owner.py"])]
    result = charge_breaking_feature(
        failing_tests=[
            "tests/test_owner.py::test_a",
            "tests/test_owner.py::test_b",
        ],
        all_features=features,
        increment_fn=charged.append,
    )
    assert result == 1
    assert charged == ["owner"]


def test_multiple_owners_each_charged_once():
    charged: list[str] = []
    features = [
        _feat("feat-a", ["tests/test_a.py"]),
        _feat("feat-b", ["tests/test_b.py"]),
    ]
    result = charge_breaking_feature(
        failing_tests=[
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_two",
        ],
        all_features=features,
        increment_fn=charged.append,
    )
    assert result == 2
    assert set(charged) == {"feat-a", "feat-b"}


def test_unowned_failure_recorded():
    charged: list[str] = []
    events: list[dict] = []
    features = [_feat("feat-a", ["tests/test_a.py"])]
    result = charge_breaking_feature(
        failing_tests=["tests/test_orphan.py::test_x"],
        all_features=features,
        increment_fn=charged.append,
        unowned_record_fn=events.append,
    )
    assert result == 0
    assert charged == []
    assert events and events[0]["failing_test"] == "tests/test_orphan.py::test_x"


def test_invalid_failing_tests_raises_value_error():
    with pytest.raises(ValueError):
        charge_breaking_feature(
            failing_tests="tests/test_a.py::test_x",
            all_features=[],
            increment_fn=lambda x: None,
        )
