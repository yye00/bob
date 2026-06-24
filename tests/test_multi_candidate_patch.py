"""Tests for bob.brownfield.multi_candidate_patch (Feature 5c5826d3).

Tests the multi-candidate patch + LLM-judge vote pattern:
  - CandidatePatch dataclass
  - MultiCandidateResult dataclass
  - is_hard_feature detection
  - judge_candidates LLM-judge heuristic
  - run_multi_candidate orchestration
  - maybe_run_multi_candidate gate
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bob.brownfield.multi_candidate_patch import (
    CANDIDATE_COUNT,
    HARD_ATTEMPTS_THRESHOLD,
    HARD_DIFFICULTY_THRESHOLD,
    TELEMETRY_EVENT_MULTI_CANDIDATE_WIN,
    CandidatePatch,
    MultiCandidateResult,
    _archive_losers,
    is_hard_feature,
    judge_candidates,
    maybe_run_multi_candidate,
    run_multi_candidate,
)


# ---------------------------------------------------------------------------
# CandidatePatch tests
# ---------------------------------------------------------------------------


class TestCandidatePatch:
    def test_to_dict_contains_all_fields(self):
        patch = CandidatePatch(
            candidate_idx=0,
            worktree_path="/tmp/wt",
            patch_diff="--- a/f.py\n+++ b/f.py\n@@ @@\n+x = 1",
            test_pass_count=10,
            test_fail_count=0,
            broke_regression=False,
            score=0.85,
            judge_reason="good",
        )
        d = patch.to_dict()
        assert d["candidate_idx"] == 0
        assert d["worktree_path"] == "/tmp/wt"
        assert d["patch_diff"] == "--- a/f.py\n+++ b/f.py\n@@ @@\n+x = 1"
        assert d["test_pass_count"] == 10
        assert d["test_fail_count"] == 0
        assert d["broke_regression"] is False
        assert d["score"] == 0.85
        assert d["judge_reason"] == "good"

    def test_to_dict_keys(self):
        patch = CandidatePatch(candidate_idx=1, worktree_path="/tmp")
        d = patch.to_dict()
        required = {
            "candidate_idx", "worktree_path", "patch_diff",
            "test_pass_count", "test_fail_count", "broke_regression",
            "score", "judge_reason",
        }
        assert set(d.keys()) == required

    def test_default_values(self):
        patch = CandidatePatch(candidate_idx=2, worktree_path="/x")
        assert patch.patch_diff == ""
        assert patch.test_pass_count == 0
        assert patch.test_fail_count == 0
        assert patch.broke_regression is False
        assert patch.score == 0.0
        assert patch.judge_reason == ""


# ---------------------------------------------------------------------------
# MultiCandidateResult tests
# ---------------------------------------------------------------------------


class TestMultiCandidateResult:
    def test_attributes(self):
        winner = CandidatePatch(candidate_idx=0, worktree_path="/wt", score=0.9)
        result = MultiCandidateResult(
            feature_id="feat-123",
            winner_idx=0,
            winner_patch=winner,
            all_candidates=[winner],
            losers_dir="/losers",
            telemetry={"event": "WIN"},
        )
        assert result.feature_id == "feat-123"
        assert result.winner_idx == 0
        assert result.winner_patch is winner
        assert len(result.all_candidates) == 1
        assert result.losers_dir == "/losers"
        assert result.telemetry["event"] == "WIN"

    def test_default_fields(self):
        result = MultiCandidateResult(feature_id="f", winner_idx=-1, winner_patch=None)
        assert result.all_candidates == []
        assert result.losers_dir == ""
        assert result.telemetry == {}


# ---------------------------------------------------------------------------
# is_hard_feature tests
# ---------------------------------------------------------------------------


class TestIsHardFeature:
    def _feature(self, difficulty="easy", refinement_attempts=0, spec_quality_score=None):
        f = {
            "id": "test-id",
            "difficulty": difficulty,
            "refinement_attempts": refinement_attempts,
        }
        if spec_quality_score is not None:
            f["spec_quality_score"] = spec_quality_score
        return f

    def test_easy_feature_not_hard(self):
        assert not is_hard_feature(self._feature("easy", 0))

    def test_medium_feature_not_hard(self):
        assert not is_hard_feature(self._feature("medium", 0))

    def test_hard_difficulty_is_hard(self):
        assert is_hard_feature(self._feature("hard", 0))

    def test_very_hard_difficulty_is_hard(self):
        assert is_hard_feature(self._feature("very_hard", 0))

    def test_extreme_difficulty_is_hard(self):
        assert is_hard_feature(self._feature("extreme", 0))

    def test_refinement_attempts_threshold_triggers_hard(self):
        assert is_hard_feature(self._feature("easy", HARD_ATTEMPTS_THRESHOLD))

    def test_refinement_attempts_below_threshold_not_hard(self):
        assert not is_hard_feature(self._feature("easy", HARD_ATTEMPTS_THRESHOLD - 1))

    def test_low_spec_quality_score_is_hard(self):
        assert is_hard_feature(self._feature("easy", 0, spec_quality_score=0.5))

    def test_high_spec_quality_score_not_hard(self):
        assert not is_hard_feature(self._feature("easy", 0, spec_quality_score=0.8))

    def test_difficulty_threshold_constant_is_hard(self):
        assert HARD_DIFFICULTY_THRESHOLD == "hard"

    def test_none_difficulty_not_hard(self):
        f = {"id": "x", "difficulty": None, "refinement_attempts": 0}
        assert not is_hard_feature(f)

    def test_missing_fields_not_hard(self):
        assert not is_hard_feature({})


# ---------------------------------------------------------------------------
# judge_candidates tests
# ---------------------------------------------------------------------------


class TestJudgeCandidates:
    def _make_candidate(self, idx, pass_count=10, diff="", broke=False):
        return CandidatePatch(
            candidate_idx=idx,
            worktree_path=f"/wt/{idx}",
            patch_diff=diff,
            test_pass_count=pass_count,
            broke_regression=broke,
        )

    def test_returns_sorted_by_score_descending(self):
        candidates = [
            self._make_candidate(0, pass_count=5),
            self._make_candidate(1, pass_count=20),
            self._make_candidate(2, pass_count=1),
        ]
        ranked = judge_candidates(candidates)
        assert ranked[0].candidate_idx == 1  # highest pass count

    def test_score_populated(self):
        candidates = [self._make_candidate(0, pass_count=10)]
        ranked = judge_candidates(candidates)
        assert ranked[0].score > 0.0

    def test_judge_reason_populated(self):
        candidates = [self._make_candidate(0, pass_count=5)]
        ranked = judge_candidates(candidates)
        assert ranked[0].judge_reason != ""

    def test_empty_candidates_returns_empty(self):
        assert judge_candidates([]) == []

    def test_score_in_valid_range(self):
        candidates = [self._make_candidate(i, pass_count=10 * i) for i in range(5)]
        ranked = judge_candidates(candidates)
        for c in ranked:
            assert 0.0 <= c.score <= 1.0

    def test_ac_coverage_boosts_score(self):
        diff_with_ac = "+def spawn_search_subagent():\n+    pass"
        diff_without_ac = "+x = 1"
        c1 = self._make_candidate(0, pass_count=10, diff=diff_with_ac)
        c2 = self._make_candidate(1, pass_count=10, diff=diff_without_ac)
        ranked = judge_candidates(
            [c1, c2],
            acceptance_criteria=["spawn_search_subagent"],
        )
        # c1 should score higher due to AC coverage
        assert ranked[0].candidate_idx == 0

    def test_minimal_diff_boosts_score(self):
        short_diff = "+x = 1"
        long_diff = "\n".join(f"+line_{i}" for i in range(100))
        c1 = self._make_candidate(0, pass_count=10, diff=short_diff)
        c2 = self._make_candidate(1, pass_count=10, diff=long_diff)
        ranked = judge_candidates([c1, c2])
        # shorter diff should rank higher when pass counts are equal
        assert ranked[0].candidate_idx == 0


# ---------------------------------------------------------------------------
# _archive_losers tests
# ---------------------------------------------------------------------------


class TestArchiveLosers:
    def test_creates_losers_dir(self, tmp_path):
        losers = [CandidatePatch(candidate_idx=0, worktree_path="/wt", patch_diff="---")]
        losers_dir = _archive_losers("feat-id", losers, workspace=tmp_path)
        assert Path(losers_dir).exists()

    def test_writes_json_per_loser(self, tmp_path):
        losers = [
            CandidatePatch(candidate_idx=0, worktree_path="/wt0", patch_diff="diff0"),
            CandidatePatch(candidate_idx=1, worktree_path="/wt1", patch_diff="diff1"),
        ]
        losers_dir = _archive_losers("feat-id", losers, workspace=tmp_path)
        ldir = Path(losers_dir)
        assert (ldir / "candidate_0.json").exists()
        assert (ldir / "candidate_1.json").exists()

    def test_writes_diff_file(self, tmp_path):
        losers = [CandidatePatch(candidate_idx=2, worktree_path="/wt2", patch_diff="some diff")]
        losers_dir = _archive_losers("feat-id", losers, workspace=tmp_path)
        diff_file = Path(losers_dir) / "candidate_2.diff"
        assert diff_file.exists()
        assert diff_file.read_text() == "some diff"

    def test_empty_losers_no_files(self, tmp_path):
        losers_dir = _archive_losers("feat-id", [], workspace=tmp_path)
        ldir = Path(losers_dir)
        assert ldir.exists()
        assert list(ldir.iterdir()) == []


# ---------------------------------------------------------------------------
# run_multi_candidate tests (non-git workspace)
# ---------------------------------------------------------------------------


class TestRunMultiCandidate:
    def _feature(self, **kwargs):
        defaults = {
            "id": "test-feature-id",
            "description": "Test feature",
            "acceptance_criteria": ["Function defined: test_func"],
            "refinement_attempts": 0,
            "difficulty": "easy",
        }
        defaults.update(kwargs)
        return defaults

    def test_returns_multi_candidate_result(self, tmp_path):
        feature = self._feature()
        result = run_multi_candidate(feature, workspace=tmp_path)
        assert isinstance(result, MultiCandidateResult)

    def test_result_has_feature_id(self, tmp_path):
        feature = self._feature(id="feat-abc")
        result = run_multi_candidate(feature, workspace=tmp_path)
        assert result.feature_id == "feat-abc"

    def test_winner_selected(self, tmp_path):
        feature = self._feature()
        result = run_multi_candidate(feature, workspace=tmp_path)
        # winner_idx should be valid (0-based or -1 if no survivors)
        assert result.winner_idx >= -1

    def test_telemetry_event_emitted(self, tmp_path):
        feature = self._feature()
        result = run_multi_candidate(feature, workspace=tmp_path)
        assert result.telemetry["event"] == TELEMETRY_EVENT_MULTI_CANDIDATE_WIN

    def test_telemetry_has_feature_id(self, tmp_path):
        feature = self._feature(id="feat-xyz")
        result = run_multi_candidate(feature, workspace=tmp_path)
        assert result.telemetry["feature_id"] == "feat-xyz"

    def test_all_candidates_count(self, tmp_path):
        feature = self._feature()
        result = run_multi_candidate(feature, workspace=tmp_path, candidate_count=3)
        assert len(result.all_candidates) == 3

    def test_losers_dir_set(self, tmp_path):
        feature = self._feature()
        result = run_multi_candidate(feature, workspace=tmp_path)
        assert result.losers_dir != ""

    def test_losers_dir_exists(self, tmp_path):
        feature = self._feature()
        result = run_multi_candidate(feature, workspace=tmp_path)
        assert Path(result.losers_dir).exists()

    def test_custom_patch_generator(self, tmp_path):
        feature = self._feature()
        patches_generated = []

        def my_generator(worktree_path, feat):
            patches_generated.append(worktree_path)
            return "+# generated patch"

        result = run_multi_candidate(feature, workspace=tmp_path, patch_generator=my_generator)
        assert len(patches_generated) == CANDIDATE_COUNT

    def test_telemetry_winner_idx_in_result(self, tmp_path):
        feature = self._feature()
        result = run_multi_candidate(feature, workspace=tmp_path)
        assert "winner_idx" in result.telemetry

    def test_telemetry_event_name_constant(self):
        assert TELEMETRY_EVENT_MULTI_CANDIDATE_WIN == "MULTI_CANDIDATE_WIN"


# ---------------------------------------------------------------------------
# maybe_run_multi_candidate tests
# ---------------------------------------------------------------------------


class TestMaybeRunMultiCandidate:
    def _easy_feature(self):
        return {
            "id": "easy-id",
            "description": "easy feature",
            "acceptance_criteria": [],
            "refinement_attempts": 0,
            "difficulty": "easy",
        }

    def _hard_feature(self):
        return {
            "id": "hard-id",
            "description": "hard feature",
            "acceptance_criteria": [],
            "refinement_attempts": HARD_ATTEMPTS_THRESHOLD,
            "difficulty": "easy",
        }

    def test_easy_feature_returns_none(self, tmp_path):
        result = maybe_run_multi_candidate(self._easy_feature(), workspace=tmp_path)
        assert result is None

    def test_hard_feature_returns_result(self, tmp_path):
        feature = self._hard_feature()
        result = maybe_run_multi_candidate(feature, workspace=tmp_path)
        assert isinstance(result, MultiCandidateResult)

    def test_hard_feature_telemetry_present(self, tmp_path):
        feature = self._hard_feature()
        result = maybe_run_multi_candidate(feature, workspace=tmp_path)
        assert result is not None
        assert result.telemetry["event"] == TELEMETRY_EVENT_MULTI_CANDIDATE_WIN

    def test_gate_checks_is_hard_feature(self, tmp_path):
        easy = self._easy_feature()
        hard = self._hard_feature()
        assert maybe_run_multi_candidate(easy, workspace=tmp_path) is None
        assert maybe_run_multi_candidate(hard, workspace=tmp_path) is not None
