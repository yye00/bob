"""Boundary tests for search_subagent and multi_candidate_patch.

Tests that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.brownfield.search_subagent import (
    SearchResult,
    _grep_candidates,
    _group_matches_into_spans,
    _score_match,
    search_results_to_edit_sites,
    should_use_search_subagent,
    spawn_search_subagent,
)
from bob3.brownfield.multi_candidate_patch import (
    CandidatePatch,
    judge_candidates,
    is_hard_feature,
    run_multi_candidate,
    maybe_run_multi_candidate,
    _archive_losers,
)


# ---------------------------------------------------------------------------
# spawn_search_subagent boundary cases
# ---------------------------------------------------------------------------


class TestSpawnSearchSubagentBoundary:
    def test_empty_intent_returns_list(self, tmp_path):
        result = spawn_search_subagent({}, workspace=tmp_path)
        assert isinstance(result, list)

    def test_empty_intent_returns_empty_not_raises(self, tmp_path):
        result = spawn_search_subagent({}, workspace=tmp_path)
        assert result == []

    def test_empty_keywords_returns_empty(self, tmp_path):
        result = spawn_search_subagent({"capability": "", "keywords": []}, workspace=tmp_path)
        assert isinstance(result, list)
        assert result == []

    def test_nonexistent_workspace_returns_empty(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        result = spawn_search_subagent({"capability": "something", "keywords": ["something"]}, workspace=nonexistent)
        assert isinstance(result, list)

    def test_empty_workspace_dir_returns_empty(self, tmp_path):
        # Empty directory — no Python files to search
        result = spawn_search_subagent({"capability": "func", "keywords": ["func"]}, workspace=tmp_path)
        assert isinstance(result, list)
        assert result == []

    def test_single_keyword_minimum_input(self, tmp_path):
        (tmp_path / "foo.py").write_text("def myfunc(): pass\n")
        result = spawn_search_subagent({"capability": "myfunc", "keywords": ["myfunc"]}, workspace=tmp_path)
        assert isinstance(result, list)

    def test_max_candidates_zero_returns_empty(self, tmp_path):
        (tmp_path / "foo.py").write_text("def myfunc(): pass\n")
        result = spawn_search_subagent(
            {"capability": "myfunc", "keywords": ["myfunc"]},
            workspace=tmp_path,
            max_candidates=0,
        )
        assert isinstance(result, list)
        assert result == []

    def test_max_candidates_one_returns_at_most_one(self, tmp_path):
        for i in range(5):
            (tmp_path / f"file_{i}.py").write_text(f"def myfunc_{i}(): pass\nmyfunc_base()\n")
        result = spawn_search_subagent(
            {"capability": "myfunc", "keywords": ["myfunc_base"]},
            workspace=tmp_path,
            max_candidates=1,
        )
        assert isinstance(result, list)
        assert len(result) <= 1


# ---------------------------------------------------------------------------
# _grep_candidates boundary cases
# ---------------------------------------------------------------------------


class TestGrepCandidatesBoundary:
    def test_empty_keywords_returns_empty(self, tmp_path):
        (tmp_path / "foo.py").write_text("def foo(): pass\n")
        result = _grep_candidates([], tmp_path)
        assert result == []

    def test_no_matching_files_returns_empty(self, tmp_path):
        (tmp_path / "foo.py").write_text("x = 1\n")
        result = _grep_candidates(["zzz_not_present_xyz"], tmp_path)
        assert isinstance(result, list)
        assert result == []

    def test_empty_directory_returns_empty(self, tmp_path):
        result = _grep_candidates(["something"], tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _group_matches_into_spans boundary cases
# ---------------------------------------------------------------------------


class TestGroupMatchesIntoSpansBoundary:
    def test_empty_matches_returns_empty(self):
        result = _group_matches_into_spans([], {}, [])
        assert result == []

    def test_empty_keywords_with_matches(self):
        matches = [{"path": "foo.py", "line_number": 10, "text": "def foo(): pass"}]
        result = _group_matches_into_spans(matches, {}, [])
        # May be empty (score below threshold) or have results; must not raise
        assert isinstance(result, list)

    def test_max_candidates_zero_returns_empty(self):
        matches = [{"path": "foo.py", "line_number": 10, "text": "def foo(): pass"}]
        result = _group_matches_into_spans(matches, {}, ["foo"], max_candidates=0)
        assert result == []

    def test_single_match_one_result(self):
        matches = [{"path": "foo.py", "line_number": 10, "text": "def foo(): pass"}]
        intent = {"capability": "foo", "target_subsystem": "", "keywords": ["foo"]}
        result = _group_matches_into_spans(matches, intent, ["foo"], max_candidates=5)
        assert isinstance(result, list)
        assert len(result) <= 1


# ---------------------------------------------------------------------------
# _score_match boundary cases
# ---------------------------------------------------------------------------


class TestScoreMatchBoundary:
    def test_empty_match_text_returns_zero(self):
        match = {"path": "foo.py", "line_number": 1, "text": ""}
        score = _score_match(match, {}, ["kw"])
        assert score == 0.0

    def test_empty_intent_does_not_raise(self):
        match = {"path": "foo.py", "line_number": 1, "text": "def foo():"}
        score = _score_match(match, {}, [])
        assert isinstance(score, float)

    def test_score_always_non_negative(self):
        match = {"path": "foo.py", "line_number": 1, "text": "x = 1"}
        score = _score_match(match, {"capability": "", "target_subsystem": ""}, [])
        assert score >= 0.0


# ---------------------------------------------------------------------------
# should_use_search_subagent boundary cases
# ---------------------------------------------------------------------------


class TestShouldUseSearchSubagentBoundary:
    def test_empty_list_returns_false(self):
        assert not should_use_search_subagent([])

    def test_single_symbol_returns_false(self):
        assert not should_use_search_subagent([{"name": "sym_0"}])


# ---------------------------------------------------------------------------
# search_results_to_edit_sites boundary cases
# ---------------------------------------------------------------------------


class TestSearchResultsToEditSitesBoundary:
    def test_empty_input_returns_empty(self):
        assert search_results_to_edit_sites([]) == []

    def test_single_result_returns_one_site(self):
        results = [SearchResult(path="x.py", start_line=1, end_line=1, confidence=0.5, rationale_snippet="")]
        sites = search_results_to_edit_sites(results)
        assert len(sites) == 1

    def test_start_equals_end_line(self):
        results = [SearchResult(path="x.py", start_line=5, end_line=5, confidence=0.5, rationale_snippet="")]
        sites = search_results_to_edit_sites(results)
        assert sites[0]["start_line"] == 5
        assert sites[0]["end_line"] == 5


# ---------------------------------------------------------------------------
# is_hard_feature boundary cases
# ---------------------------------------------------------------------------


class TestIsHardFeatureBoundary:
    def test_empty_feature_dict_returns_false(self):
        assert not is_hard_feature({})

    def test_none_values_returns_false(self):
        assert not is_hard_feature({"difficulty": None, "refinement_attempts": None})

    def test_zero_refinement_attempts_easy_not_hard(self):
        assert not is_hard_feature({"difficulty": "easy", "refinement_attempts": 0})

    def test_spec_quality_exactly_at_boundary_not_hard(self):
        # 0.6 is not below threshold, so should not be hard
        assert not is_hard_feature({"difficulty": "easy", "refinement_attempts": 0, "spec_quality_score": 0.6})

    def test_spec_quality_just_below_boundary_is_hard(self):
        assert is_hard_feature({"difficulty": "easy", "refinement_attempts": 0, "spec_quality_score": 0.59})


# ---------------------------------------------------------------------------
# judge_candidates boundary cases
# ---------------------------------------------------------------------------


class TestJudgeCandidatesBoundary:
    def test_empty_returns_empty(self):
        assert judge_candidates([]) == []

    def test_single_candidate_returns_single(self):
        c = CandidatePatch(candidate_idx=0, worktree_path="/wt", test_pass_count=5)
        result = judge_candidates([c])
        assert len(result) == 1
        assert result[0].score >= 0.0

    def test_all_zero_pass_counts_does_not_raise(self):
        candidates = [CandidatePatch(candidate_idx=i, worktree_path=f"/wt/{i}", test_pass_count=0) for i in range(3)]
        result = judge_candidates(candidates)
        assert len(result) == 3
        for c in result:
            assert isinstance(c.score, float)

    def test_empty_diffs_does_not_raise(self):
        candidates = [CandidatePatch(candidate_idx=0, worktree_path="/wt", patch_diff="")]
        result = judge_candidates(candidates, acceptance_criteria=["something"])
        assert len(result) == 1

    def test_empty_acceptance_criteria_does_not_raise(self):
        candidates = [CandidatePatch(candidate_idx=0, worktree_path="/wt", test_pass_count=5)]
        result = judge_candidates(candidates, acceptance_criteria=[])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# run_multi_candidate boundary cases
# ---------------------------------------------------------------------------


class TestRunMultiCandidateBoundary:
    def _base_feature(self, **kw):
        d = {"id": "test-id", "description": "", "acceptance_criteria": [], "refinement_attempts": 0, "difficulty": "easy"}
        d.update(kw)
        return d

    def test_candidate_count_one_does_not_raise(self, tmp_path):
        result = run_multi_candidate(self._base_feature(), workspace=tmp_path, candidate_count=1)
        assert len(result.all_candidates) == 1

    def test_empty_acceptance_criteria_does_not_raise(self, tmp_path):
        result = run_multi_candidate(self._base_feature(acceptance_criteria=[]), workspace=tmp_path)
        assert result is not None

    def test_empty_description_does_not_raise(self, tmp_path):
        result = run_multi_candidate(self._base_feature(description=""), workspace=tmp_path)
        assert result is not None

    def test_returns_valid_result_with_minimum_feature(self, tmp_path):
        result = run_multi_candidate({"id": "min-id"}, workspace=tmp_path)
        assert result is not None
        assert isinstance(result.winner_idx, int)


# ---------------------------------------------------------------------------
# maybe_run_multi_candidate boundary cases
# ---------------------------------------------------------------------------


class TestMaybeRunMultiCandidateBoundary:
    def test_empty_feature_easy_returns_none(self, tmp_path):
        result = maybe_run_multi_candidate({}, workspace=tmp_path)
        assert result is None

    def test_minimum_hard_feature_returns_result(self, tmp_path):
        feature = {"id": "h", "refinement_attempts": 1}
        result = maybe_run_multi_candidate(feature, workspace=tmp_path)
        assert result is not None


# ---------------------------------------------------------------------------
# _archive_losers boundary cases
# ---------------------------------------------------------------------------


class TestArchiveLosersBoundary:
    def test_empty_losers_creates_dir_no_files(self, tmp_path):
        losers_dir = _archive_losers("fid", [], workspace=tmp_path)
        p = Path(losers_dir)
        assert p.exists()
        assert list(p.iterdir()) == []

    def test_loser_with_empty_diff_writes_json_not_diff(self, tmp_path):
        losers = [CandidatePatch(candidate_idx=0, worktree_path="/wt", patch_diff="")]
        losers_dir = _archive_losers("fid", losers, workspace=tmp_path)
        p = Path(losers_dir)
        assert (p / "candidate_0.json").exists()
        # No diff file should be written when patch_diff is empty
        assert not (p / "candidate_0.diff").exists()
