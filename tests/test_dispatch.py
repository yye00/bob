"""Tests for bob.dispatch — SWE-Bench cheap wins (F-R7-609).

Covers the AC-required functions:
  - bob.dispatch.compute_edit_metrics
  - bob.dispatch.check_mutation_pass
  - integration: bob.dispatch importable
  - behavior: boundary cases (zero/empty input)
  - behavior: invalid input raises ValueError
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bob.dispatch as dispatch_module
from bob.dispatch import (
    EditModeDecision,
    build_repo_tree,
    check_mutation_pass,
    compute_edit_metrics,
    select_edit_mode,
)


# ── Integration: module importable ────────────────────────────────────────────


class TestIntegration:
    def test_module_importable(self):
        import importlib
        mod = importlib.import_module("bob.dispatch")
        assert mod is not None

    def test_compute_edit_metrics_in_module(self):
        assert hasattr(dispatch_module, "compute_edit_metrics")
        assert callable(dispatch_module.compute_edit_metrics)

    def test_check_mutation_pass_in_module(self):
        assert hasattr(dispatch_module, "check_mutation_pass")
        assert callable(dispatch_module.check_mutation_pass)

    def test_compute_edit_metrics_in_all(self):
        assert "compute_edit_metrics" in dispatch_module.__all__

    def test_check_mutation_pass_in_all(self):
        assert "check_mutation_pass" in dispatch_module.__all__


# ── compute_edit_metrics — normal operation ───────────────────────────────────


class TestComputeEditMetrics:
    def test_returns_edit_mode_decision(self):
        result = compute_edit_metrics(1, 10)
        assert isinstance(result, EditModeDecision)

    def test_small_edit_returns_replace(self):
        result = compute_edit_metrics(1, 10)
        assert result.mode == "replace"

    def test_many_sites_returns_rewrite(self):
        result = compute_edit_metrics(4, 10)
        assert result.mode == "rewrite"

    def test_large_span_returns_rewrite(self):
        result = compute_edit_metrics(1, 41)
        assert result.mode == "rewrite"

    def test_at_threshold_is_replace(self):
        result = compute_edit_metrics(3, 40)
        assert result.mode == "replace"

    def test_one_over_site_threshold_is_rewrite(self):
        result = compute_edit_metrics(4, 0)
        assert result.mode == "rewrite"

    def test_one_over_span_threshold_is_rewrite(self):
        result = compute_edit_metrics(0, 41)
        assert result.mode == "rewrite"

    def test_sites_field_preserved(self):
        result = compute_edit_metrics(3, 15)
        assert result.sites == 3

    def test_span_field_preserved(self):
        result = compute_edit_metrics(2, 25)
        assert result.span == 25


# ── compute_edit_metrics — boundary cases (zero/empty input) ─────────────────


class TestComputeEditMetricsBoundary:
    def test_zero_sites_zero_span_returns_replace(self):
        """Zero/empty input must return a well-defined result (replace), not crash."""
        result = compute_edit_metrics(0, 0)
        assert isinstance(result, EditModeDecision)
        assert result.mode == "replace"
        assert result.sites == 0
        assert result.span == 0

    def test_zero_sites_nonzero_span_replace(self):
        result = compute_edit_metrics(0, 5)
        assert result.mode == "replace"
        assert result.sites == 0

    def test_nonzero_sites_zero_span_replace(self):
        result = compute_edit_metrics(2, 0)
        assert result.mode == "replace"
        assert result.span == 0

    def test_exactly_one_site_one_span_replace(self):
        result = compute_edit_metrics(1, 1)
        assert result.mode == "replace"

    def test_large_values_rewrite(self):
        result = compute_edit_metrics(100, 1000)
        assert result.mode == "rewrite"


# ── compute_edit_metrics — invalid input raises ValueError ────────────────────


class TestComputeEditMetricsInvalidInput:
    def test_negative_site_count_raises(self):
        """Negative edit_site_count must raise ValueError, not silently succeed."""
        with pytest.raises(ValueError, match="non-negative"):
            compute_edit_metrics(-1, 10)

    def test_negative_span_raises(self):
        """Negative edit_span must raise ValueError, not silently succeed."""
        with pytest.raises(ValueError, match="non-negative"):
            compute_edit_metrics(1, -5)

    def test_both_negative_raises(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(-1, -1)

    def test_float_site_count_raises(self):
        """Non-integer inputs must raise ValueError."""
        with pytest.raises((ValueError, TypeError)):
            compute_edit_metrics(1.5, 10)  # type: ignore[arg-type]

    def test_float_span_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_edit_metrics(1, 10.5)  # type: ignore[arg-type]

    def test_string_site_count_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_edit_metrics("3", 10)  # type: ignore[arg-type]

    def test_none_site_count_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_edit_metrics(None, 10)  # type: ignore[arg-type]

    def test_none_span_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_edit_metrics(1, None)  # type: ignore[arg-type]


# ── check_mutation_pass — normal operation ────────────────────────────────────


class TestCheckMutationPass:
    def test_returns_false_when_test_fails(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
            result = check_mutation_pass(["pytest", "test_foo.py"], tmp_path, "feat-001")
        assert result is False

    def test_returns_true_when_test_passes_after_mutation(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test_foo.py"], tmp_path, "feat-001")
        assert result is True

    def test_timeout_returns_false(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=120)
            result = check_mutation_pass(["pytest", "test_foo.py"], tmp_path, "feat-001")
        assert result is False

    def test_accepts_env_kwarg(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            check_mutation_pass(
                ["pytest", "test.py"], tmp_path, "feat-002", env={"MY_VAR": "1"}
            )
        call_kwargs = mock_run.call_args[1]
        assert "MY_VAR" in call_kwargs["env"]

    def test_accepts_timeout_kwarg(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            check_mutation_pass(
                ["pytest", "test.py"], tmp_path, "feat-003", timeout=60
            )
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 60


# ── check_mutation_pass — boundary cases (zero/empty input) ──────────────────


class TestCheckMutationPassBoundary:
    def test_empty_test_command_handled(self, tmp_path):
        """Empty test command must not crash — may fail but must return a bool."""
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = check_mutation_pass([], tmp_path, "feat-empty")
        assert isinstance(result, bool)

    def test_empty_feature_id_handled(self, tmp_path):
        """Empty feature_id string is valid — must not crash."""
        with patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = check_mutation_pass(["pytest", "test.py"], tmp_path, "")
        assert isinstance(result, bool)


# ── AC-required top-level test functions ─────────────────────────────────────


def test_swe_bench_repo_tree(tmp_path):
    """AC: repo tree is built for a workspace and returns a non-empty string."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    result = build_repo_tree(tmp_path)
    assert isinstance(result, str)
    assert len(result) > 0


def test_adaptive_edit_mode():
    """AC: adaptive edit mode returns 'replace' by default and 'rewrite' when thresholds exceeded."""
    replace_decision = select_edit_mode(1, 5)
    assert replace_decision.mode == "replace"

    rewrite_by_sites = select_edit_mode(4, 0)
    assert rewrite_by_sites.mode == "rewrite"

    rewrite_by_span = select_edit_mode(0, 41)
    assert rewrite_by_span.mode == "rewrite"

    assert isinstance(replace_decision, EditModeDecision)
    assert replace_decision.sites == 1
    assert replace_decision.span == 5


def test_mutation_pass_check(tmp_path):
    """AC: mutation pass check returns True when test still passes (weak test), False otherwise."""
    with patch("bob.dispatch.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = check_mutation_pass(["pytest", "test_foo.py"], tmp_path, "feat-001")
    assert result is True

    with patch("bob.dispatch.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED")
        result = check_mutation_pass(["pytest", "test_foo.py"], tmp_path, "feat-001")
    assert result is False
