"""Tests for bob3.test_ownership_map — build_test_ownership_map and verify_regression_owner.

Feature a931dca6-d0fe-4f61-bbd4-40140e4a5f60:
Regression attribution requires test-ownership map (no scapegoats).
"""

from __future__ import annotations

import pytest

from bob3.test_ownership_map import build_test_ownership_map, verify_regression_owner


class TestBuildTestOwnershipMap:
    """Tests for build_test_ownership_map."""

    def test_empty_list_returns_empty_dict(self):
        result = build_test_ownership_map([])
        assert result == {}

    def test_single_feature_with_pytest_ac(self):
        features = [
            {
                "id": "feat-abc",
                "acceptance_criteria": '["pytest: tests/test_abc.py"]',
            }
        ]
        result = build_test_ownership_map(features)
        assert result.get("tests/test_abc.py") == "feat-abc"

    def test_multiple_features_each_own_their_tests(self):
        features = [
            {
                "id": "feat-a",
                "acceptance_criteria": '["pytest: tests/test_a.py"]',
            },
            {
                "id": "feat-b",
                "acceptance_criteria": '["pytest: tests/test_b.py"]',
            },
        ]
        result = build_test_ownership_map(features)
        assert result.get("tests/test_a.py") == "feat-a"
        assert result.get("tests/test_b.py") == "feat-b"

    def test_first_writer_wins_for_duplicate_claim(self):
        features = [
            {
                "id": "feat-first",
                "acceptance_criteria": '["pytest: tests/test_shared.py"]',
            },
            {
                "id": "feat-second",
                "acceptance_criteria": '["pytest: tests/test_shared.py"]',
            },
        ]
        result = build_test_ownership_map(features)
        assert result.get("tests/test_shared.py") == "feat-first"

    def test_non_pytest_acs_are_ignored(self):
        features = [
            {
                "id": "feat-x",
                "acceptance_criteria": '["File exists: src/bob3/x.py", "Function defined: bob3.x.my_fn"]',
            }
        ]
        result = build_test_ownership_map(features)
        assert result == {}

    def test_feature_with_mixed_acs_only_extracts_pytest(self):
        features = [
            {
                "id": "feat-mixed",
                "acceptance_criteria": (
                    '["File exists: src/bob3/mixed.py",'
                    ' "pytest: tests/test_mixed.py",'
                    ' "integration: bob3.evaluator"]'
                ),
            }
        ]
        result = build_test_ownership_map(features)
        assert "tests/test_mixed.py" in result
        assert result["tests/test_mixed.py"] == "feat-mixed"
        assert len(result) == 1

    def test_feature_with_list_acs(self):
        features = [
            {
                "id": "feat-list",
                "acceptance_criteria": [
                    "pytest: tests/test_list.py",
                    "File exists: src/bob3/list.py",
                ],
            }
        ]
        result = build_test_ownership_map(features)
        assert result.get("tests/test_list.py") == "feat-list"

    def test_feature_with_annotated_pytest_ac(self):
        features = [
            {
                "id": "feat-ann",
                "acceptance_criteria": [
                    "pytest: tests/test_ann.py — boundary case for empty input",
                ],
            }
        ]
        result = build_test_ownership_map(features)
        assert result.get("tests/test_ann.py") == "feat-ann"

    def test_none_features_raises_type_error(self):
        with pytest.raises(TypeError):
            build_test_ownership_map(None)

    def test_feature_with_none_id_raises(self):
        with pytest.raises((TypeError, ValueError)):
            build_test_ownership_map([{"id": None, "acceptance_criteria": []}])

    def test_feature_with_empty_id_raises(self):
        with pytest.raises(ValueError):
            build_test_ownership_map([{"id": "", "acceptance_criteria": []}])

    def test_object_features_use_attribute_access(self):
        class FakeFeature:
            def __init__(self, fid, acs):
                self.id = fid
                self.acceptance_criteria = acs

        features = [FakeFeature("feat-obj", ["pytest: tests/test_obj.py"])]
        result = build_test_ownership_map(features)
        assert result.get("tests/test_obj.py") == "feat-obj"

    def test_feature_with_no_acceptance_criteria_returns_empty(self):
        features = [{"id": "feat-empty", "acceptance_criteria": None}]
        result = build_test_ownership_map(features)
        assert result == {}


class TestVerifyRegressionOwner:
    """Tests for verify_regression_owner."""

    def test_owned_test_returns_demote_verdict(self):
        ownership_map = {"tests/test_foo.py::test_bar": "feat-alpha"}
        result = verify_regression_owner(
            newly_failing_tests=["tests/test_foo.py::test_bar"],
            ownership_map=ownership_map,
            candidate_feature_id="feat-alpha",
        )
        assert result["verdict"] == "demote"
        assert result["may_demote"] is True
        assert "tests/test_foo.py::test_bar" in result["owned_failing_tests"]

    def test_unowned_test_returns_no_evidence_verdict(self):
        ownership_map = {}
        result = verify_regression_owner(
            newly_failing_tests=["tests/test_orphan.py::test_mystery"],
            ownership_map=ownership_map,
            candidate_feature_id="feat-alpha",
        )
        assert result["verdict"] == "no_evidence"
        assert result["may_demote"] is False
        assert result["owned_failing_tests"] == []

    def test_empty_newly_failing_returns_no_evidence(self):
        ownership_map = {"tests/test_foo.py::test_bar": "feat-alpha"}
        result = verify_regression_owner(
            newly_failing_tests=[],
            ownership_map=ownership_map,
            candidate_feature_id="feat-alpha",
        )
        assert result["verdict"] == "no_evidence"
        assert result["may_demote"] is False

    def test_file_level_ownership_matches_nodeid(self):
        ownership_map = {"tests/test_foo.py": "feat-file"}
        result = verify_regression_owner(
            newly_failing_tests=["tests/test_foo.py::test_specific"],
            ownership_map=ownership_map,
            candidate_feature_id="feat-file",
        )
        assert result["verdict"] == "demote"
        assert result["may_demote"] is True

    def test_different_feature_not_blamed(self):
        ownership_map = {"tests/test_foo.py::test_bar": "feat-other"}
        result = verify_regression_owner(
            newly_failing_tests=["tests/test_foo.py::test_bar"],
            ownership_map=ownership_map,
            candidate_feature_id="feat-different",
        )
        assert result["verdict"] == "no_evidence"
        assert result["may_demote"] is False

    def test_owned_failing_tests_are_sorted(self):
        ownership_map = {
            "tests/test_b.py::test_z": "feat-alpha",
            "tests/test_a.py::test_x": "feat-alpha",
        }
        result = verify_regression_owner(
            newly_failing_tests=[
                "tests/test_b.py::test_z",
                "tests/test_a.py::test_x",
            ],
            ownership_map=ownership_map,
            candidate_feature_id="feat-alpha",
        )
        assert result["owned_failing_tests"] == sorted(result["owned_failing_tests"])

    def test_none_newly_failing_raises_type_error(self):
        with pytest.raises(TypeError):
            verify_regression_owner(
                newly_failing_tests=None,
                ownership_map={},
                candidate_feature_id="feat-x",
            )

    def test_non_list_newly_failing_raises_type_error(self):
        with pytest.raises(TypeError):
            verify_regression_owner(
                newly_failing_tests="tests/test_foo.py::test_bar",
                ownership_map={},
                candidate_feature_id="feat-x",
            )

    def test_none_ownership_map_raises_type_error(self):
        with pytest.raises(TypeError):
            verify_regression_owner(
                newly_failing_tests=[],
                ownership_map=None,
                candidate_feature_id="feat-x",
            )

    def test_non_dict_ownership_map_raises_type_error(self):
        with pytest.raises(TypeError):
            verify_regression_owner(
                newly_failing_tests=[],
                ownership_map=["tests/test_a.py::test_x"],
                candidate_feature_id="feat-x",
            )

    def test_non_string_candidate_feature_id_raises_type_error(self):
        with pytest.raises(TypeError):
            verify_regression_owner(
                newly_failing_tests=[],
                ownership_map={},
                candidate_feature_id=42,
            )

    def test_empty_candidate_feature_id_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_regression_owner(
                newly_failing_tests=[],
                ownership_map={},
                candidate_feature_id="",
            )

    def test_result_has_required_keys(self):
        result = verify_regression_owner(
            newly_failing_tests=[],
            ownership_map={},
            candidate_feature_id="feat-x",
        )
        assert "verdict" in result
        assert "owned_failing_tests" in result
        assert "may_demote" in result

    def test_multiple_owned_and_unowned_tests(self):
        ownership_map = {
            "tests/test_foo.py::test_owned": "feat-alpha",
            "tests/test_bar.py::test_other": "feat-beta",
        }
        result = verify_regression_owner(
            newly_failing_tests=[
                "tests/test_foo.py::test_owned",
                "tests/test_orphan.py::test_x",
                "tests/test_bar.py::test_other",
            ],
            ownership_map=ownership_map,
            candidate_feature_id="feat-alpha",
        )
        assert result["verdict"] == "demote"
        assert "tests/test_foo.py::test_owned" in result["owned_failing_tests"]
        assert "tests/test_orphan.py::test_x" not in result["owned_failing_tests"]
        assert "tests/test_bar.py::test_other" not in result["owned_failing_tests"]
