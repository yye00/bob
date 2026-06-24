"""Test: attribution requires file overlap between breaking commit and feature ownership.

Feature aaa5a7f7-74e2-4edc-b61c-ac822dfced4f
"""

from __future__ import annotations

import pytest


def _make_commit(commit_id: str, files_touched: list[str]):
    return {"commit_id": commit_id, "files_touched": files_touched}


class TestBuildOwnershipMap:
    """build_ownership_map returns dict[feature_id, set[file_path]]."""

    def test_importable(self):
        from bob3.orchestrator.regression_attribution import build_ownership_map
        assert callable(build_ownership_map)

    def test_empty_features_returns_empty_map(self):
        from bob3.orchestrator.regression_attribution import build_ownership_map
        result = build_ownership_map(features=[], recent_commits=[])
        assert result == {}

    def test_feature_with_no_commits_has_empty_file_set(self):
        from bob3.orchestrator.regression_attribution import build_ownership_map
        features = [{"id": "feat-A", "commit_ids": []}]
        result = build_ownership_map(features=features, recent_commits=[])
        assert result == {"feat-A": set()}

    def test_feature_accumulates_files_from_all_its_commits(self):
        from bob3.orchestrator.regression_attribution import build_ownership_map
        commits = [
            _make_commit("c1", ["src/foo.py", "src/bar.py"]),
            _make_commit("c2", ["src/baz.py"]),
        ]
        features = [{"id": "feat-A", "commit_ids": ["c1", "c2"]}]
        result = build_ownership_map(features=features, recent_commits=commits)
        assert result["feat-A"] == {"src/foo.py", "src/bar.py", "src/baz.py"}

    def test_two_features_have_independent_file_sets(self):
        from bob3.orchestrator.regression_attribution import build_ownership_map
        commits = [
            _make_commit("c1", ["src/foo.py"]),
            _make_commit("c2", ["src/bar.py"]),
        ]
        features = [
            {"id": "feat-A", "commit_ids": ["c1"]},
            {"id": "feat-B", "commit_ids": ["c2"]},
        ]
        result = build_ownership_map(features=features, recent_commits=commits)
        assert result["feat-A"] == {"src/foo.py"}
        assert result["feat-B"] == {"src/bar.py"}

    def test_commit_not_in_features_is_ignored(self):
        from bob3.orchestrator.regression_attribution import build_ownership_map
        commits = [_make_commit("c1", ["src/foo.py"])]
        # feat-A references c2 which does not exist in commits list
        features = [{"id": "feat-A", "commit_ids": ["c2"]}]
        result = build_ownership_map(features=features, recent_commits=commits)
        assert result["feat-A"] == set()

    def test_returns_dict_mapping_feature_id_to_set_of_paths(self):
        from bob3.orchestrator.regression_attribution import build_ownership_map
        commits = [_make_commit("c1", ["src/alpha.py"])]
        features = [{"id": "feat-X", "commit_ids": ["c1"]}]
        result = build_ownership_map(features=features, recent_commits=commits)
        assert isinstance(result, dict)
        assert isinstance(result["feat-X"], set)


class TestAttributeBreakageFileOverlap:
    """attribute_breakage requires file overlap to attribute a test failure."""

    def test_importable(self):
        from bob3.orchestrator.regression_attribution import attribute_breakage
        assert callable(attribute_breakage)

    def test_no_file_overlap_yields_no_attribution(self):
        from bob3.orchestrator.regression_attribution import attribute_breakage
        # feat-A owns src/foo.py; breaking commit only touched src/bar.py
        ownership_map = {"feat-A": {"src/foo.py"}}
        recent_commits = [_make_commit("c1", ["src/bar.py"])]
        result = attribute_breakage(
            failing_test_id="tests/test_foo.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )
        assert result["attributed_feature"] is None
        assert result["evidence"] == []
        assert result["confidence"] == 0.0

    def test_file_overlap_yields_attribution(self):
        from bob3.orchestrator.regression_attribution import attribute_breakage
        ownership_map = {"feat-A": {"src/foo.py"}}
        recent_commits = [_make_commit("c1", ["src/foo.py"])]
        result = attribute_breakage(
            failing_test_id="tests/test_foo.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )
        assert result["attributed_feature"] == "feat-A"
        assert len(result["evidence"]) > 0
        assert result["confidence"] > 0.0

    def test_output_shape_is_correct(self):
        from bob3.orchestrator.regression_attribution import attribute_breakage
        ownership_map = {}
        recent_commits = []
        result = attribute_breakage(
            failing_test_id="tests/test_something.py::test_x",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )
        assert "attributed_feature" in result
        assert "evidence" in result
        assert "confidence" in result
        assert isinstance(result["evidence"], list)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_confidence_is_between_0_and_1(self):
        from bob3.orchestrator.regression_attribution import attribute_breakage
        ownership_map = {"feat-A": {"src/shared.py", "src/other.py"}}
        recent_commits = [_make_commit("c1", ["src/shared.py"])]
        result = attribute_breakage(
            failing_test_id="tests/test_shared.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )
        assert 0.0 <= result["confidence"] <= 1.0
