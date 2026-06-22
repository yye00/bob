"""Tests for regression_attribution_requires_test_ownership_map_no.

Feature c9e7a68a-9c5f-4505-83a5-b537d810b481

Verifies:
- No feature is demoted without evidence that its own tests newly fail.
- Unowned failing tests go to the "unattributed" sentinel, never scapegoated.
- build_test_ownership_map correctly parses pytest: ACs.
- Only features whose tests are in newly_failing_tests get demote=True.
"""

from __future__ import annotations

import json
import pytest

from bob3.regression_attribution_requires_test_ownership_map_no import (
    UNATTRIBUTED_KEY,
    build_test_ownership_map,
    regression_attribution_requires_test_ownership_map_no,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(fid: str, pytest_acs: list[str], extra_acs: list[str] | None = None):
    all_acs = [f"pytest: {t}" for t in pytest_acs] + (extra_acs or [])
    return {"id": fid, "acceptance_criteria": json.dumps(all_acs)}


# ---------------------------------------------------------------------------
# Top-level canonical AC test (required by AC)
# ---------------------------------------------------------------------------

def test_regression_attribution_requires_test_ownership_map_no():
    """No feature is demoted without owned-test evidence."""
    ownership = {
        "tests/test_alpha.py::test_one": "feat-alpha",
        "tests/test_beta.py::test_two": "feat-beta",
    }
    newly_failing = ["tests/test_alpha.py::test_one", "tests/test_orphan.py::test_x"]

    result = regression_attribution_requires_test_ownership_map_no(
        newly_failing_tests=newly_failing,
        test_ownership_map=ownership,
    )

    # feat-alpha owns a failing test → demoted
    assert "feat-alpha" in result
    assert result["feat-alpha"]["demote"] is True
    assert "tests/test_alpha.py::test_one" in result["feat-alpha"]["tests"]

    # feat-beta owns no failing test → NOT in result at all (no scapegoating)
    assert "feat-beta" not in result

    # Orphan test → unattributed sentinel, not scapegoated to any feature
    assert UNATTRIBUTED_KEY in result
    assert result[UNATTRIBUTED_KEY]["demote"] is False
    assert "tests/test_orphan.py::test_x" in result[UNATTRIBUTED_KEY]["tests"]


# ---------------------------------------------------------------------------
# build_test_ownership_map
# ---------------------------------------------------------------------------

class TestBuildTestOwnershipMap:
    def test_parses_pytest_ac_lines(self):
        features = [
            _make_feature("feat-1", ["tests/test_foo.py::test_bar"]),
            _make_feature("feat-2", ["tests/test_baz.py::test_qux"]),
        ]
        result = build_test_ownership_map(features)
        assert result["tests/test_foo.py::test_bar"] == "feat-1"
        assert result["tests/test_baz.py::test_qux"] == "feat-2"

    def test_ignores_non_pytest_acs(self):
        features = [
            _make_feature(
                "feat-1",
                ["tests/test_foo.py::test_bar"],
                extra_acs=["File exists: src/foo.py", "Function defined: foo.bar"],
            )
        ]
        result = build_test_ownership_map(features)
        assert "src/foo.py" not in result
        assert result["tests/test_foo.py::test_bar"] == "feat-1"

    def test_empty_features_returns_empty_map(self):
        assert build_test_ownership_map([]) == {}

    def test_feature_with_no_pytest_acs_contributes_nothing(self):
        features = [{"id": "feat-x", "acceptance_criteria": json.dumps(["File exists: src/x.py"])}]
        result = build_test_ownership_map(features)
        assert result == {}

    def test_handles_already_decoded_ac_list(self):
        features = [{"id": "feat-z", "acceptance_criteria": ["pytest: tests/test_z.py::test_z"]}]
        result = build_test_ownership_map(features)
        assert result["tests/test_z.py::test_z"] == "feat-z"

    def test_multiple_pytest_acs_per_feature(self):
        features = [
            _make_feature("feat-m", ["tests/test_a.py::test_1", "tests/test_b.py::test_2"])
        ]
        result = build_test_ownership_map(features)
        assert result["tests/test_a.py::test_1"] == "feat-m"
        assert result["tests/test_b.py::test_2"] == "feat-m"


# ---------------------------------------------------------------------------
# regression_attribution_requires_test_ownership_map_no
# ---------------------------------------------------------------------------

class TestRegressionAttributionNoScapegoats:
    def test_owned_failing_test_marks_feature_for_demotion(self):
        ownership = {"tests/test_x.py::test_fail": "feat-owner"}
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=["tests/test_x.py::test_fail"],
            test_ownership_map=ownership,
        )
        assert "feat-owner" in result
        assert result["feat-owner"]["demote"] is True
        assert result["feat-owner"]["tests"] == ["tests/test_x.py::test_fail"]

    def test_unowned_test_goes_to_unattributed_sentinel(self):
        ownership = {}
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=["tests/test_orphan.py::test_orphan"],
            test_ownership_map=ownership,
        )
        assert UNATTRIBUTED_KEY in result
        assert result[UNATTRIBUTED_KEY]["demote"] is False
        assert "tests/test_orphan.py::test_orphan" in result[UNATTRIBUTED_KEY]["tests"]

    def test_innocent_feature_never_in_result(self):
        """A feature with no newly-failing owned tests must not appear in result."""
        ownership = {
            "tests/test_a.py::test_owned": "feat-a",
            "tests/test_b.py::test_innocent": "feat-b",
        }
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=["tests/test_a.py::test_owned"],
            test_ownership_map=ownership,
        )
        assert "feat-a" in result
        assert "feat-b" not in result  # no scapegoating

    def test_no_failing_tests_returns_empty_result(self):
        ownership = {"tests/test_x.py::test_foo": "feat-x"}
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=[],
            test_ownership_map=ownership,
        )
        assert result == {}

    def test_multiple_owners_each_get_their_tests(self):
        ownership = {
            "tests/test_a.py::test_1": "feat-alpha",
            "tests/test_a.py::test_2": "feat-alpha",
            "tests/test_b.py::test_3": "feat-beta",
        }
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=[
                "tests/test_a.py::test_1",
                "tests/test_a.py::test_2",
                "tests/test_b.py::test_3",
            ],
            test_ownership_map=ownership,
        )
        assert set(result["feat-alpha"]["tests"]) == {
            "tests/test_a.py::test_1",
            "tests/test_a.py::test_2",
        }
        assert result["feat-alpha"]["demote"] is True
        assert result["feat-beta"]["tests"] == ["tests/test_b.py::test_3"]
        assert result["feat-beta"]["demote"] is True
        assert UNATTRIBUTED_KEY not in result

    def test_unattributed_demote_is_always_false(self):
        """Unattributed bucket must never have demote=True — that's scapegoating."""
        ownership = {}
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=["tests/test_x.py::test_x", "tests/test_y.py::test_y"],
            test_ownership_map=ownership,
        )
        assert result[UNATTRIBUTED_KEY]["demote"] is False

    def test_test_lists_are_sorted_deterministically(self):
        ownership = {
            "tests/test_z.py::test_z": "feat-x",
            "tests/test_a.py::test_a": "feat-x",
        }
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=["tests/test_z.py::test_z", "tests/test_a.py::test_a"],
            test_ownership_map=ownership,
        )
        assert result["feat-x"]["tests"] == sorted(result["feat-x"]["tests"])

    def test_empty_ownership_map_all_unattributed(self):
        result = regression_attribution_requires_test_ownership_map_no(
            newly_failing_tests=["tests/test_a.py::test_1", "tests/test_b.py::test_2"],
            test_ownership_map={},
        )
        assert list(result.keys()) == [UNATTRIBUTED_KEY]
        assert len(result[UNATTRIBUTED_KEY]["tests"]) == 2
        assert result[UNATTRIBUTED_KEY]["demote"] is False
