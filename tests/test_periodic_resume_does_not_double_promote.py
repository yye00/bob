"""Tests that _resume_interrupted_work_periodic does not double-promote features.

If a feature is already in 'ready' status (promoted by a prior tick),
calling the periodic scan again must be idempotent — no duplicate updates.

The function queries 'interrupted' rows explicitly.  If a feature was
promoted to 'ready' on a prior tick, it will no longer appear in the
'interrupted' query, so the function will naturally skip it.  These tests
verify that invariant holds even when edge cases arise (e.g. the feature
appears in multiple queries).
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from bob.orchestrator.run_loop import _resume_interrupted_work_periodic


def _feature(fid: str, status: str) -> MagicMock:
    f = MagicMock()
    f.id = fid
    f.status = status
    f.name = f"feature-{fid[:8]}"
    return f


class TestPeriodicResumeDoesNotDoublePromote:
    def test_already_ready_feature_is_not_promoted_again(self):
        """Feature promoted to 'ready' on a prior tick is not in interrupted list → skipped."""
        feat = _feature("aaa00001-0000-0000-0000-000000000001", "ready")

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            # Simulates what DB returns after prior promotion: empty interrupted list
            mock_db.list_features.side_effect = lambda project_id, status: (
                [] if status == "interrupted" else [feat]
            )
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == []
        mock_db.update_feature.assert_not_called()

    def test_each_interrupted_feature_promoted_exactly_once(self):
        """Each interrupted feature results in exactly one update_feature call."""
        feats = [
            _feature(f"bbb{i:05d}-0000-0000-0000-000000000001", "interrupted")
            for i in range(4)
        ]
        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                feats if status == "interrupted" else []
            )
            result = _resume_interrupted_work_periodic("proj-1")

        assert len(result) == 4
        # Exactly one update_feature per feature
        assert mock_db.update_feature.call_count == 4
        promoted_ids = [c.args[0] for c in mock_db.update_feature.call_args_list]
        assert sorted(promoted_ids) == sorted(f.id for f in feats)

    def test_two_consecutive_calls_second_is_noop(self):
        """Simulating two ticks: second call returns empty (feature already promoted)."""
        feat = _feature("ccc00001-0000-0000-0000-000000000001", "interrupted")

        call_count = {"n": 0}

        def side_effect(project_id, status):
            # First call: return the interrupted feature; subsequent calls: empty
            if status != "interrupted":
                return []
            call_count["n"] += 1
            return [feat] if call_count["n"] == 1 else []

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = side_effect

            first = _resume_interrupted_work_periodic("proj-1")
            second = _resume_interrupted_work_periodic("proj-1")

        assert first == [feat.id]
        assert second == []
        # Only the first tick triggered an update
        assert mock_db.update_feature.call_count == 1

    def test_mixed_statuses_only_interrupted_promoted(self):
        """Only interrupted features are promoted; others are unchanged."""
        interrupted = _feature("ddd00001-0000-0000-0000-000000000001", "interrupted")
        ready = _feature("eee00001-0000-0000-0000-000000000001", "ready")

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.list_features.side_effect = lambda project_id, status: (
                [interrupted] if status == "interrupted" else []
            )
            result = _resume_interrupted_work_periodic("proj-1")

        assert result == [interrupted.id]
        assert mock_db.update_feature.call_count == 1
        assert mock_db.update_feature.call_args.args[0] == interrupted.id
