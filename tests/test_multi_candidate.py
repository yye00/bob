"""Tests for bob.brownfield.multi_candidate (Feature 659807e6).

Covers the AC-required entry points that wrap the multi-candidate patch +
LLM-judge pipeline:
  - spawn_worker_candidates (input validation)
  - filter_regression_breaking (drop patches that break regressions)
  - rank_by_judge_vote (LLM-judge ranking)
  - judge_and_select (filter survivors, judge, return the winner)
"""

from __future__ import annotations

import pytest

from bob.brownfield.multi_candidate import (
    CandidatePatch,
    filter_regression_breaking,
    judge_and_select,
    rank_by_judge_vote,
    spawn_worker_candidates,
)


def _cand(idx, *, diff="", passes=0, fails=0, broke=False):
    return CandidatePatch(
        candidate_idx=idx,
        worktree_path=f"/tmp/wt{idx}",
        patch_diff=diff,
        test_pass_count=passes,
        test_fail_count=fails,
        broke_regression=broke,
    )


# ---------------------------------------------------------------------------
# filter_regression_breaking
# ---------------------------------------------------------------------------


class TestFilterRegressionBreaking:
    def test_drops_regression_breakers(self):
        cands = [
            _cand(0, broke=False),
            _cand(1, broke=True),
            _cand(2, broke=False),
        ]
        survivors = filter_regression_breaking(cands)
        assert {c.candidate_idx for c in survivors} == {0, 2}

    def test_all_broke_returns_fewest_failures_fallback(self):
        cands = [
            _cand(0, broke=True, fails=5),
            _cand(1, broke=True, fails=2),
        ]
        survivors = filter_regression_breaking(cands)
        assert len(survivors) == 1
        assert survivors[0].candidate_idx == 1

    def test_empty_list_returns_empty(self):
        assert filter_regression_breaking([]) == []

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_regression_breaking("not a list")


# ---------------------------------------------------------------------------
# rank_by_judge_vote
# ---------------------------------------------------------------------------


class TestRankByJudgeVote:
    def test_more_passing_tests_ranks_higher(self):
        low = _cand(0, diff="+a\n+b", passes=1)
        high = _cand(1, diff="+a\n+b", passes=10)
        ranked = rank_by_judge_vote([low, high])
        assert ranked[0].candidate_idx == 1
        assert ranked[0].score >= ranked[1].score

    def test_scores_are_populated(self):
        ranked = rank_by_judge_vote([_cand(0, diff="+x", passes=3)])
        assert ranked[0].judge_reason != ""
        assert ranked[0].score > 0

    def test_empty_list_returns_empty(self):
        assert rank_by_judge_vote([]) == []

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError):
            rank_by_judge_vote(42)


# ---------------------------------------------------------------------------
# judge_and_select
# ---------------------------------------------------------------------------


class TestJudgeAndSelect:
    def test_selects_best_non_regression_candidate(self):
        cands = [
            _cand(0, diff="+a\n+b", passes=2, broke=False),
            _cand(1, diff="+a\n+b", passes=9, broke=False),
            _cand(2, diff="+a\n+b", passes=100, broke=True),  # best but broke
        ]
        winner = judge_and_select(cands)
        assert winner is not None
        assert winner.candidate_idx == 1  # idx 2 filtered out as regression

    def test_empty_list_returns_none(self):
        assert judge_and_select([]) is None

    def test_ac_coverage_influences_score(self):
        covered = _cand(0, diff="+def widget(): pass", passes=1)
        uncovered = _cand(1, diff="+xyz", passes=1)
        winner = judge_and_select(
            [uncovered, covered],
            feature_description="add a widget",
            acceptance_criteria=["Function defined: widget"],
        )
        assert winner.candidate_idx == 0

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError):
            judge_and_select({"not": "a list"})


# ---------------------------------------------------------------------------
# spawn_worker_candidates input validation
# ---------------------------------------------------------------------------


class TestSpawnWorkerCandidates:
    def test_non_dict_feature_raises_value_error(self):
        with pytest.raises(ValueError):
            spawn_worker_candidates("not a dict")

    def test_uses_patch_generator_to_produce_candidates(self, tmp_path):
        feature = {
            "id": "feat-test",
            "description": "do a thing",
            "acceptance_criteria": [],
        }
        calls = []

        def gen(worktree, feat):
            calls.append(worktree)
            return "+patch line"

        cands = spawn_worker_candidates(
            feature,
            workspace=tmp_path,
            candidate_count=2,
            patch_generator=gen,
        )
        assert len(cands) == 2
        assert all(isinstance(c, CandidatePatch) for c in cands)
