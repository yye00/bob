"""Error path tests for brownfield scope correction (F-R7-611).

Tests that invalid inputs raise ValueError and functions do not silently succeed.
Covers:
  (A) resurrection.filter_signals_by_config — invalid signal_kind values
  (B) resurrection.detect_resurrection_signals — invalid parameter types/ranges
  (C) elicit.elicit — unknown feature mode raises ValueError
  (D) elicit.branch_candidates_headless — negative candidate_count
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.brownfield import resurrection, elicit


# ===========================================================================
# (A) resurrection.filter_signals_by_config — error paths
# ===========================================================================


class TestFilterSignalsByConfigErrors:
    """Error paths: filter_signals_by_config with invalid inputs."""

    def test_non_list_signals_raises_type_error(self):
        """Passing a non-list for signals should raise TypeError (or AttributeError
        at worst — but must NOT silently succeed and return a wrong value)."""
        with pytest.raises((TypeError, AttributeError)):
            resurrection.filter_signals_by_config("not_a_list", config={})

    def test_none_signals_raises(self):
        """None signals must not silently succeed."""
        with pytest.raises((TypeError, AttributeError)):
            resurrection.filter_signals_by_config(None, config={})


# ===========================================================================
# (B) resurrection.detect_resurrection_signals — invalid parameter ranges
# ===========================================================================


class TestDetectResurrectionSignalsErrors:
    """Error paths: detect_resurrection_signals with invalid parameters."""

    def test_non_list_touches_raises_type_error(self):
        """touches must be a list; non-list raises TypeError."""
        with pytest.raises(TypeError):
            resurrection.detect_resurrection_signals(
                workspace_root="/tmp",
                touches="not_a_list",
                feature_keywords=[],
            )

    def test_negative_pr_lookback_raises_value_error(self):
        """Negative pr_lookback_days raises ValueError."""
        with pytest.raises(ValueError, match="pr_lookback_days"):
            resurrection.detect_resurrection_signals(
                workspace_root="/tmp",
                touches=[],
                feature_keywords=[],
                pr_lookback_days=-1,
            )

    def test_negative_branch_diverge_days_raises_value_error(self):
        """Negative branch_diverge_days raises ValueError."""
        with pytest.raises(ValueError, match="branch_diverge_days"):
            resurrection.detect_resurrection_signals(
                workspace_root="/tmp",
                touches=[],
                feature_keywords=[],
                branch_diverge_days=-1,
            )

    def test_zero_todo_cluster_min_size_raises_value_error(self):
        """todo_cluster_min_size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="todo_cluster_min_size"):
            resurrection.detect_resurrection_signals(
                workspace_root="/tmp",
                touches=["foo.py"],
                feature_keywords=[],
                todo_cluster_min_size=0,
            )

    def test_negative_todo_cluster_min_size_raises_value_error(self):
        """Negative todo_cluster_min_size raises ValueError."""
        with pytest.raises(ValueError, match="todo_cluster_min_size"):
            resurrection.detect_resurrection_signals(
                workspace_root="/tmp",
                touches=["foo.py"],
                feature_keywords=[],
                todo_cluster_min_size=-5,
            )


# ===========================================================================
# (C) elicit.elicit — unknown feature mode
# ===========================================================================


class TestElicitUnknownModeErrors:
    """Error paths: elicit() with invalid/unknown mode."""

    def test_unknown_mode_raises_value_error(self):
        """Passing an unrecognized feature mode must raise ValueError."""
        request = elicit.ElicitationRequest(
            intent_stub="add something",
            candidate_count=3,
        )
        with pytest.raises(ValueError, match="Unknown feature.mode"):
            elicit.elicit(request, feature_mode="robot_mode")

    def test_empty_string_mode_raises_value_error(self):
        """Empty string mode is not 'interactive' or 'headless' — raises ValueError."""
        request = elicit.ElicitationRequest(
            intent_stub="add something",
            candidate_count=3,
        )
        with pytest.raises(ValueError):
            elicit.elicit(request, feature_mode="")

    def test_none_mode_raises(self):
        """None mode must raise (not silently succeed)."""
        request = elicit.ElicitationRequest(
            intent_stub="add something",
            candidate_count=3,
        )
        with pytest.raises((ValueError, AttributeError)):
            elicit.elicit(request, feature_mode=None)


# ===========================================================================
# (D) elicit.branch_candidates_headless — error path (negative count)
# ===========================================================================


class TestBranchCandidatesHeadlessErrors:
    """Error paths: branch_candidates_headless with invalid inputs."""

    def test_negative_candidate_count_does_not_silently_succeed_with_wrong_count(self):
        """Negative candidate_count: either raises or returns empty list (not wrong positive count)."""
        request = elicit.ElicitationRequest(
            intent_stub="fix the bug",
            candidate_count=-1,
        )
        try:
            result = elicit.branch_candidates_headless(request)
            # If it doesn't raise, it must return [] (range(-1) is empty)
            assert isinstance(result, list)
            # Must not return a positive number of candidates for negative count
            assert len(result) == 0
        except (ValueError, TypeError):
            pass  # Raising is also acceptable

    def test_non_string_intent_stub_raises_or_returns_valid(self):
        """Non-string intent_stub: either raises AttributeError/TypeError or returns list."""
        request = elicit.ElicitationRequest.__new__(elicit.ElicitationRequest)
        object.__setattr__(request, "intent_stub", None)
        object.__setattr__(request, "research_notes", "")
        object.__setattr__(request, "candidate_count", 2)
        object.__setattr__(request, "context", {})
        try:
            result = elicit.branch_candidates_headless(request)
            assert isinstance(result, list)
        except (TypeError, AttributeError):
            pass  # Acceptable — invalid input should not silently succeed incorrectly
