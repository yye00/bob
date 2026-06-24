"""Tests for bob.ownership_evidenced_regression.

Feature 50afa15a-a140-4e8a-8012-d10fe14fecbd: Ownership-evidenced regression
detection — no scapegoat without proof.

Covers:
- file_touched_in_commit: primitive causal-link check
- detect_regression_with_ownership: end-to-end pipeline
- No-scapegoat invariant: features without evidence are never demoted
- regression_unattributed events emitted for non-evidenced failures
"""

from __future__ import annotations

import pytest

from bob.ownership_evidenced_regression import (
    detect_regression_with_ownership,
    file_touched_in_commit,
)


# ---------------------------------------------------------------------------
# Tests for file_touched_in_commit
# ---------------------------------------------------------------------------

class TestFileTouchedInCommit:
    def test_file_in_touched_set_returns_true(self):
        assert file_touched_in_commit("src/foo.py", {"src/foo.py", "src/bar.py"}) is True

    def test_file_not_in_touched_set_returns_false(self):
        assert file_touched_in_commit("src/foo.py", {"src/bar.py"}) is False

    def test_empty_touched_set_returns_false(self):
        assert file_touched_in_commit("src/foo.py", set()) is False

    def test_frozenset_accepted(self):
        assert file_touched_in_commit("src/foo.py", frozenset({"src/foo.py"})) is True

    def test_none_file_path_raises_type_error(self):
        with pytest.raises(TypeError, match="file_path"):
            file_touched_in_commit(None, {"src/foo.py"})

    def test_empty_file_path_raises_value_error(self):
        with pytest.raises(ValueError):
            file_touched_in_commit("", {"src/foo.py"})

    def test_whitespace_only_file_path_raises_value_error(self):
        with pytest.raises(ValueError):
            file_touched_in_commit("   ", {"src/foo.py"})

    def test_none_touched_files_raises_type_error(self):
        with pytest.raises(TypeError, match="touched_files"):
            file_touched_in_commit("src/foo.py", None)

    def test_list_touched_files_raises_value_error(self):
        with pytest.raises(ValueError, match="touched_files"):
            file_touched_in_commit("src/foo.py", ["src/foo.py"])

    def test_non_string_file_path_raises_type_error(self):
        with pytest.raises(TypeError):
            file_touched_in_commit(42, {"src/foo.py"})


# ---------------------------------------------------------------------------
# Tests for detect_regression_with_ownership
# ---------------------------------------------------------------------------

class TestDetectRegressionWithOwnership:
    """Core behavior tests."""

    def _base_args(self, **overrides):
        defaults = dict(
            before_results={},
            after_results={},
            test_to_feature_map={},
            ownership_map={},
            breaking_files=set(),
        )
        defaults.update(overrides)
        return defaults

    def test_no_newly_failing_tests_returns_empty_demoted(self):
        result = detect_regression_with_ownership(
            before_results={"tests/test_a.py::test_x": True},
            after_results={"tests/test_a.py::test_x": True},
            test_to_feature_map={},
            ownership_map={},
            breaking_files=set(),
        )
        assert result["demoted"] == {}
        assert result["unattributed"]["no_owner"] == []

    def test_owned_test_with_file_evidence_demotes_feature(self):
        demoted = []
        events = []

        result = detect_regression_with_ownership(
            before_results={"tests/test_feat.py::test_main": True},
            after_results={"tests/test_feat.py::test_main": False},
            test_to_feature_map={"tests/test_feat.py::test_main": "feat-abc"},
            ownership_map={"feat-abc": {"src/feat_abc.py"}},
            breaking_files={"src/feat_abc.py"},
            _update_feature_fn=lambda fid, status: demoted.append((fid, status)),
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )

        assert "feat-abc" in result["demoted"]
        assert result["demoted"]["feat-abc"]["tests"] == ["tests/test_feat.py::test_main"]
        assert len(result["demoted"]["feat-abc"]["evidence"]) >= 1
        assert ("feat-abc", "regression") in demoted

    def test_owned_test_without_file_evidence_is_unattributed_not_demoted(self):
        demoted = []
        events = []

        result = detect_regression_with_ownership(
            before_results={"tests/test_feat.py::test_main": True},
            after_results={"tests/test_feat.py::test_main": False},
            test_to_feature_map={"tests/test_feat.py::test_main": "feat-innocent"},
            ownership_map={"feat-innocent": {"src/innocent.py"}},
            breaking_files={"src/completely_different.py"},
            _update_feature_fn=lambda fid, status: demoted.append((fid, status)),
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )

        assert result["demoted"] == {}
        assert demoted == []
        assert "feat-innocent" in result["unattributed"]["no_evidence"]
        regression_events = [e for e in events if e[0] == "regression_unattributed"]
        assert len(regression_events) >= 1

    def test_unowned_test_goes_to_no_owner_bucket(self):
        events = []

        result = detect_regression_with_ownership(
            before_results={"tests/test_orphan.py::test_x": True},
            after_results={"tests/test_orphan.py::test_x": False},
            test_to_feature_map={},
            ownership_map={},
            breaking_files={"src/anything.py"},
            _emit_event_fn=lambda evt, **kw: events.append((evt, kw)),
        )

        assert result["demoted"] == {}
        assert "tests/test_orphan.py::test_x" in result["unattributed"]["no_owner"]
        unattributed_events = [e for e in events if e[0] == "regression_unattributed"]
        assert len(unattributed_events) >= 1

    def test_transitive_dependency_counts_as_evidence(self):
        demoted = []

        result = detect_regression_with_ownership(
            before_results={"tests/test_feat.py::test_x": True},
            after_results={"tests/test_feat.py::test_x": False},
            test_to_feature_map={"tests/test_feat.py::test_x": "feat-transitive"},
            ownership_map={"feat-transitive": {"src/owned.py"}},
            breaking_files={"src/imported_dep.py"},
            transitive_deps={"src/owned.py": {"src/imported_dep.py"}},
            _update_feature_fn=lambda fid, status: demoted.append((fid, status)),
        )

        assert "feat-transitive" in result["demoted"]
        assert ("feat-transitive", "regression") in demoted

    def test_no_transitive_link_means_no_evidence(self):
        demoted = []

        result = detect_regression_with_ownership(
            before_results={"tests/test_feat.py::test_x": True},
            after_results={"tests/test_feat.py::test_x": False},
            test_to_feature_map={"tests/test_feat.py::test_x": "feat-no-link"},
            ownership_map={"feat-no-link": {"src/owned.py"}},
            breaking_files={"src/unrelated.py"},
            transitive_deps={"src/owned.py": {"src/other.py"}},
            _update_feature_fn=lambda fid, status: demoted.append((fid, status)),
        )

        assert result["demoted"] == {}
        assert demoted == []

    def test_test_passing_before_and_after_not_newly_failing(self):
        result = detect_regression_with_ownership(
            before_results={"tests/test_a.py::test_x": True},
            after_results={"tests/test_a.py::test_x": True},
            test_to_feature_map={"tests/test_a.py::test_x": "feat-stable"},
            ownership_map={"feat-stable": {"src/stable.py"}},
            breaking_files={"src/stable.py"},
        )
        assert result["demoted"] == {}

    def test_test_was_failing_before_not_newly_failing(self):
        result = detect_regression_with_ownership(
            before_results={"tests/test_a.py::test_x": False},
            after_results={"tests/test_a.py::test_x": False},
            test_to_feature_map={"tests/test_a.py::test_x": "feat-broken"},
            ownership_map={"feat-broken": {"src/broken.py"}},
            breaking_files={"src/broken.py"},
        )
        assert result["demoted"] == {}

    def test_two_features_only_evidenced_one_demoted(self):
        demoted = []

        result = detect_regression_with_ownership(
            before_results={
                "tests/test_a.py::test_x": True,
                "tests/test_b.py::test_y": True,
            },
            after_results={
                "tests/test_a.py::test_x": False,
                "tests/test_b.py::test_y": False,
            },
            test_to_feature_map={
                "tests/test_a.py::test_x": "feat-guilty",
                "tests/test_b.py::test_y": "feat-innocent",
            },
            ownership_map={
                "feat-guilty": {"src/guilty.py"},
                "feat-innocent": {"src/innocent.py"},
            },
            breaking_files={"src/guilty.py"},
            _update_feature_fn=lambda fid, status: demoted.append((fid, status)),
        )

        assert "feat-guilty" in result["demoted"]
        assert "feat-innocent" not in result["demoted"]
        assert "feat-innocent" in result["unattributed"]["no_evidence"]
        assert ("feat-guilty", "regression") in demoted
        assert ("feat-innocent", "regression") not in demoted

    def test_result_structure_always_present(self):
        result = detect_regression_with_ownership(
            before_results={},
            after_results={},
            test_to_feature_map={},
            ownership_map={},
            breaking_files=set(),
        )
        assert "demoted" in result
        assert "unattributed" in result
        assert "no_owner" in result["unattributed"]
        assert "no_evidence" in result["unattributed"]


# ---------------------------------------------------------------------------
# Tests for integration: bob.detect_regression exposes the new function
# ---------------------------------------------------------------------------

class TestIntegrationDetectRegression:
    def test_importable_from_detect_regression(self):
        from bob.detect_regression import detect_regression_with_ownership as fn
        assert callable(fn)

    def test_file_touched_in_commit_importable_from_detect_regression(self):
        from bob.detect_regression import file_touched_in_commit as fn
        assert callable(fn)
