"""Test: immunity — completed features with NO file in breaking commit set cannot be re-demoted.

Feature aaa5a7f7-74e2-4edc-b61c-ac822dfced4f
"""

from __future__ import annotations

import pytest


def _make_commit(commit_id: str, files_touched: list[str]):
    return {"commit_id": commit_id, "files_touched": files_touched}


class TestImmunityAfterClear:
    """Features with no file overlap with the breaking commit set are immune."""

    def test_feature_not_in_breaking_commit_is_immune(self):
        """A completed feature that did NOT touch any file in the breaking commit cannot be demoted."""
        from bob.orchestrator.regression_attribution import attribute_breakage

        # feat-A owns src/a.py; breaking commit only touched src/z.py
        ownership_map = {
            "feat-A": {"src/a.py"},
            "feat-Z": {"src/z.py"},
        }
        recent_commits = [_make_commit("c1", ["src/z.py"])]

        result = attribute_breakage(
            failing_test_id="tests/test_a.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        # feat-A has no file overlap with breaking commit — must be immune (None attribution)
        assert result["attributed_feature"] != "feat-A"

    def test_immunity_means_no_regression_status_change(self):
        """demote_with_evidence with no evidence leaves feature status untouched."""
        from bob.orchestrator.regression_attribution import demote_with_evidence
        demoted = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            pass

        demote_with_evidence(
            feature_id="feat-immune",
            evidence=[],  # no evidence — immune
            confidence=0.0,
            failing_test_id="tests/test_something.py::test_x",
            recent_commits=[_make_commit("c1", ["src/unrelated.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        # feat-immune must not be demoted to regression
        assert not any(f == "feat-immune" and s == "regression" for f, s in demoted)

    def test_immune_feature_with_evidence_below_threshold_stays_immune(self):
        """Even with minimal evidence, low confidence keeps feature immune."""
        from bob.orchestrator.regression_attribution import demote_with_evidence
        demoted = []

        def update_fn(feature_id, status):
            demoted.append((feature_id, status))

        def emit_fn(event_type, **kwargs):
            pass

        demote_with_evidence(
            feature_id="feat-A",
            evidence=["weak signal"],
            confidence=0.30,  # well below 0.60 threshold
            failing_test_id="tests/test_a.py::test_one",
            recent_commits=[_make_commit("c1", ["src/other.py"])],
            _update_feature_fn=update_fn,
            _emit_event_fn=emit_fn,
        )

        assert not any(f == "feat-A" and s == "regression" for f, s in demoted)

    def test_only_touched_feature_gets_demoted(self):
        """Only the feature whose files were touched gets attributed, not bystanders."""
        from bob.orchestrator.regression_attribution import attribute_breakage

        ownership_map = {
            "feat-touched": {"src/touched.py"},
            "feat-innocent-1": {"src/innocent1.py"},
            "feat-innocent-2": {"src/innocent2.py"},
        }
        recent_commits = [_make_commit("c1", ["src/touched.py"])]

        result = attribute_breakage(
            failing_test_id="tests/test_touched.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        # Only feat-touched should be attributed; innocents are immune
        assert result["attributed_feature"] == "feat-touched"
        assert result["attributed_feature"] != "feat-innocent-1"
        assert result["attributed_feature"] != "feat-innocent-2"

    def test_build_ownership_map_includes_all_features_even_no_commits(self):
        """Features not referenced in recent_commits still appear in ownership map."""
        from bob.orchestrator.regression_attribution import build_ownership_map

        features = [
            {"id": "feat-with-commits", "commit_ids": ["c1"]},
            {"id": "feat-no-commits", "commit_ids": []},
        ]
        commits = [{"commit_id": "c1", "files_touched": ["src/foo.py"]}]

        result = build_ownership_map(features=features, recent_commits=commits)

        assert "feat-with-commits" in result
        assert "feat-no-commits" in result
        assert result["feat-no-commits"] == set()

    def test_feature_with_empty_file_set_cannot_be_attributed(self):
        """A feature with no owned files has an empty file set and cannot be attributed."""
        from bob.orchestrator.regression_attribution import attribute_breakage

        ownership_map = {
            "feat-empty": set(),  # no files owned
        }
        recent_commits = [_make_commit("c1", ["src/anything.py"])]

        result = attribute_breakage(
            failing_test_id="tests/test_x.py::test_one",
            recent_commits=recent_commits,
            ownership_map=ownership_map,
        )

        # Empty ownership set — no possible overlap — should be None
        assert result["attributed_feature"] is None
