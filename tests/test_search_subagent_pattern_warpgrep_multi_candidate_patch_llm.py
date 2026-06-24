"""Tests for bob.search_subagent_pattern_warpgrep_multi_candidate_patch_llm.

Covers the WarpGrep search-subagent + multi-candidate patch + LLM-judge vote
facade module (Feature 8296b3a0).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bob.search_subagent_pattern_warpgrep_multi_candidate_patch_llm import (
    search_subagent_pattern_warpgrep_multi_candidate_patch_llm,
)


# ---------------------------------------------------------------------------
# Boundary case: empty / zero input
# ---------------------------------------------------------------------------


class TestBoundaryEmptyInput:
    """AC: handles empty or zero input by returning a well-defined result."""

    def test_empty_intent_returns_dict(self):
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})
        assert isinstance(result, dict)

    def test_empty_intent_does_not_crash(self):
        # Must not raise
        search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})

    def test_empty_intent_has_search_candidates_key(self):
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})
        assert "search_candidates" in result

    def test_empty_intent_candidates_is_list(self):
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})
        assert isinstance(result["search_candidates"], list)

    def test_empty_intent_has_multi_candidate_key(self):
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})
        assert "multi_candidate" in result

    def test_none_keywords_returns_empty_candidates(self):
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm(
            {"keywords": [], "capability": "", "target_subsystem": ""}
        )
        assert isinstance(result, dict)
        assert isinstance(result["search_candidates"], list)

    def test_zero_difficulty_returns_result(self):
        feature = {
            "id": "test-feat",
            "difficulty": "",
            "refinement_attempts": 0,
        }
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm(
            feature, run_multi_candidate=False
        )
        assert isinstance(result, dict)
        assert result.get("multi_candidate") is None  # not hard, skipped


# ---------------------------------------------------------------------------
# Invalid input: raises ValueError or returns rejection
# ---------------------------------------------------------------------------


class TestInvalidInput:
    """AC: raises ValueError (or returns rejection) on invalid input, no silent success."""

    def test_none_intent_raises(self):
        with pytest.raises((ValueError, TypeError)):
            search_subagent_pattern_warpgrep_multi_candidate_patch_llm(None)

    def test_string_intent_raises(self):
        with pytest.raises((ValueError, TypeError)):
            search_subagent_pattern_warpgrep_multi_candidate_patch_llm("not a dict")

    def test_int_intent_raises(self):
        with pytest.raises((ValueError, TypeError)):
            search_subagent_pattern_warpgrep_multi_candidate_patch_llm(42)

    def test_list_intent_raises(self):
        with pytest.raises((ValueError, TypeError)):
            search_subagent_pattern_warpgrep_multi_candidate_patch_llm(["a", "b"])


# ---------------------------------------------------------------------------
# Search subagent integration
# ---------------------------------------------------------------------------


class TestSearchSubagentIntegration:
    """Verify the facade delegates to spawn_search_subagent."""

    def test_delegates_to_search_subagent(self):
        intent = {"capability": "grep locator", "target_subsystem": "brownfield"}
        with patch(
            "bob.search_subagent_pattern_warpgrep_multi_candidate_patch_llm"
            ".spawn_search_subagent"
        ) as mock_spawn:
            mock_spawn.return_value = []
            result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm(
                intent, run_multi_candidate=False
            )
            mock_spawn.assert_called_once()
            assert result["search_candidates"] == []

    def test_search_candidates_forwarded_from_subagent(self):
        fake_candidate = MagicMock()
        fake_candidate.to_dict.return_value = {
            "path": "src/foo.py",
            "start_line": 10,
            "end_line": 20,
            "confidence": 0.9,
            "rationale_snippet": "def foo",
        }
        intent = {"capability": "foo", "keywords": ["foo"]}
        with patch(
            "bob.search_subagent_pattern_warpgrep_multi_candidate_patch_llm"
            ".spawn_search_subagent"
        ) as mock_spawn:
            mock_spawn.return_value = [fake_candidate]
            result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm(
                intent, run_multi_candidate=False
            )
            assert len(result["search_candidates"]) == 1
            assert result["search_candidates"][0]["path"] == "src/foo.py"


# ---------------------------------------------------------------------------
# Multi-candidate gate
# ---------------------------------------------------------------------------


class TestMultiCandidateGate:
    """Verify the facade gates multi-candidate dispatch on feature difficulty."""

    def test_easy_feature_skips_multi_candidate(self):
        feature = {
            "id": "easy-feat",
            "difficulty": "easy",
            "refinement_attempts": 0,
        }
        with patch(
            "bob.search_subagent_pattern_warpgrep_multi_candidate_patch_llm"
            ".maybe_run_multi_candidate"
        ) as mock_mrc:
            mock_mrc.return_value = None
            result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm(feature)
            assert result["multi_candidate"] is None

    def test_hard_feature_triggers_multi_candidate(self):
        feature = {
            "id": "hard-feat",
            "difficulty": "hard",
            "refinement_attempts": 0,
        }
        fake_result = MagicMock()
        fake_result.winner_idx = 1
        fake_result.telemetry = {"event": "MULTI_CANDIDATE_WIN"}
        with patch(
            "bob.search_subagent_pattern_warpgrep_multi_candidate_patch_llm"
            ".maybe_run_multi_candidate"
        ) as mock_mrc:
            mock_mrc.return_value = fake_result
            result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm(feature)
            assert result["multi_candidate"] is not None

    def test_run_multi_candidate_false_skips_dispatch(self):
        feature = {
            "id": "hard-feat-2",
            "difficulty": "hard",
            "refinement_attempts": 2,
        }
        with patch(
            "bob.search_subagent_pattern_warpgrep_multi_candidate_patch_llm"
            ".maybe_run_multi_candidate"
        ) as mock_mrc:
            result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm(
                feature, run_multi_candidate=False
            )
            mock_mrc.assert_not_called()
            assert result["multi_candidate"] is None


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class TestResultStructure:
    """Verify the result dict shape."""

    def test_result_has_required_keys(self):
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})
        for key in ("search_candidates", "multi_candidate"):
            assert key in result, f"Missing key: {key}"

    def test_result_is_dict(self):
        result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Canonical test (required by AC)
# ---------------------------------------------------------------------------


def test_search_subagent_pattern_warpgrep_multi_candidate_patch_llm():
    """Canonical AC test: function exists, handles boundary, validates input."""
    # Boundary: empty dict returns result without crashing
    result = search_subagent_pattern_warpgrep_multi_candidate_patch_llm({})
    assert isinstance(result, dict)
    assert "search_candidates" in result
    assert "multi_candidate" in result
    assert isinstance(result["search_candidates"], list)

    # Invalid input: None must raise
    with pytest.raises((ValueError, TypeError)):
        search_subagent_pattern_warpgrep_multi_candidate_patch_llm(None)
