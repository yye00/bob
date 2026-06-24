"""Error path tests for search_subagent and multi_candidate_patch.

Tests that invalid input raises ValueError and functions do not silently succeed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.brownfield.search_subagent import (
    SearchResult,
    spawn_search_subagent,
)
from bob.brownfield.multi_candidate_patch import (
    CandidatePatch,
    judge_candidates,
    is_hard_feature,
    run_multi_candidate,
)


# ---------------------------------------------------------------------------
# SearchResult.from_dict error paths
# ---------------------------------------------------------------------------


class TestSearchResultFromDictErrors:
    def test_missing_path_raises(self):
        with pytest.raises((KeyError, TypeError, ValueError)):
            SearchResult.from_dict({"start_line": 1, "end_line": 10})

    def test_missing_start_line_raises(self):
        with pytest.raises((KeyError, TypeError, ValueError)):
            SearchResult.from_dict({"path": "foo.py", "end_line": 10})

    def test_missing_end_line_raises(self):
        with pytest.raises((KeyError, TypeError, ValueError)):
            SearchResult.from_dict({"path": "foo.py", "start_line": 1})

    def test_non_numeric_start_line_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SearchResult.from_dict({"path": "foo.py", "start_line": "abc", "end_line": 10})

    def test_non_numeric_end_line_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SearchResult.from_dict({"path": "foo.py", "start_line": 1, "end_line": "xyz"})

    def test_non_numeric_confidence_raises(self):
        with pytest.raises((ValueError, TypeError)):
            SearchResult.from_dict({"path": "foo.py", "start_line": 1, "end_line": 10, "confidence": "not-a-float"})


# ---------------------------------------------------------------------------
# spawn_search_subagent error paths
# ---------------------------------------------------------------------------


class TestSpawnSearchSubagentErrors:
    def test_non_dict_intent_raises(self, tmp_path):
        with pytest.raises((AttributeError, TypeError, ValueError)):
            spawn_search_subagent(None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_intent_list_raises(self, tmp_path):
        with pytest.raises((AttributeError, TypeError, ValueError)):
            spawn_search_subagent([], workspace=tmp_path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CandidatePatch error paths
# ---------------------------------------------------------------------------


class TestCandidatePatchErrors:
    def test_missing_required_args_raises(self):
        with pytest.raises(TypeError):
            CandidatePatch()  # type: ignore[call-arg]

    def test_missing_candidate_idx_raises(self):
        with pytest.raises(TypeError):
            CandidatePatch(worktree_path="/wt")  # type: ignore[call-arg]

    def test_missing_worktree_path_raises(self):
        with pytest.raises(TypeError):
            CandidatePatch(candidate_idx=0)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# is_hard_feature error paths
# ---------------------------------------------------------------------------


class TestIsHardFeatureErrors:
    def test_non_numeric_refinement_attempts_raises(self):
        with pytest.raises((ValueError, TypeError)):
            is_hard_feature({"difficulty": "easy", "refinement_attempts": "not-a-number"})

    def test_non_numeric_spec_quality_raises(self):
        with pytest.raises((ValueError, TypeError)):
            is_hard_feature({"difficulty": "easy", "refinement_attempts": 0, "spec_quality_score": "bad"})


# ---------------------------------------------------------------------------
# judge_candidates error paths
# ---------------------------------------------------------------------------


class TestJudgeCandidatesErrors:
    def test_non_candidate_in_list_raises(self):
        with pytest.raises((AttributeError, TypeError)):
            judge_candidates(["not_a_candidate"])  # type: ignore[list-item]

    def test_invalid_candidate_type_raises(self):
        with pytest.raises((AttributeError, TypeError)):
            judge_candidates([42])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# run_multi_candidate error paths
# ---------------------------------------------------------------------------


class TestRunMultiCandidateErrors:
    def test_non_dict_feature_raises(self, tmp_path):
        with pytest.raises((AttributeError, TypeError, ValueError)):
            run_multi_candidate(None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_candidate_count_zero_does_not_silently_succeed(self, tmp_path):
        # Zero candidates is not a valid input — must raise or return empty candidates
        feature = {"id": "test", "description": "", "acceptance_criteria": [], "refinement_attempts": 0}
        # With count=0 we expect an empty candidate list or ValueError, not a winner
        try:
            result = run_multi_candidate(feature, workspace=tmp_path, candidate_count=0)
            # If it returns, the winner should be -1 (no candidates)
            assert result.winner_idx == -1 or len(result.all_candidates) == 0
        except (ValueError, IndexError):
            pass  # Raising is also acceptable
