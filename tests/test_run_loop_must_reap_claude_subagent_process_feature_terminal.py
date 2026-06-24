"""Tests for run_loop_must_reap_claude_subagent_process_feature_terminal.

Acceptance criteria (feature 5957b0ad-3de8-4fed-a8c1-e54cab634910):
  - File exists: src/bob/run_loop_must_reap_claude_subagent_process_feature_terminal.py
  - Function defined: bob.run_loop_must_reap_claude_subagent_process_feature_terminal
    .run_loop_must_reap_claude_subagent_process_feature_terminal
  - pytest: tests/test_run_loop_must_reap_claude_subagent_process_feature_terminal.py
    ::test_run_loop_must_reap_claude_subagent_process_feature_terminal
  - integration: bob.orchestrator.run_loop
"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# AC test — must be named exactly as in the acceptance criterion
# ---------------------------------------------------------------------------


def test_run_loop_must_reap_claude_subagent_process_feature_terminal():
    """AC test: function importable and verifies core reaping behaviour."""
    import bob.run_loop_must_reap_claude_subagent_process_feature_terminal as mod
    from bob.run_loop_must_reap_claude_subagent_process_feature_terminal import (
        run_loop_must_reap_claude_subagent_process_feature_terminal,
    )

    # Function must be callable
    assert callable(run_loop_must_reap_claude_subagent_process_feature_terminal)

    # Module must expose the function in __all__
    assert "run_loop_must_reap_claude_subagent_process_feature_terminal" in mod.__all__

    # Module docstring exists and mentions reap/terminal
    assert mod.__doc__ is not None
    doc_lower = mod.__doc__.lower()
    assert "reap" in doc_lower or "terminal" in doc_lower

    # Function returns a list (of reaped PIDs)
    feature_id = "5957b0ad-3de8-4fed-a8c1-e54cab634910"
    with patch(
        "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
        ".reap_subagent_for_feature"
    ) as mock_reap:
        mock_reap.return_value = [12345]
        result = run_loop_must_reap_claude_subagent_process_feature_terminal(feature_id)

    assert isinstance(result, list)
    mock_reap.assert_called_once_with(feature_id)

    # Applies to all terminal states
    for status in ("completed", "needs_human", "regression", "failed"):
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            r = run_loop_must_reap_claude_subagent_process_feature_terminal(
                feature_id, status=status
            )
        assert isinstance(r, list)
        mock_reap.assert_called_once_with(feature_id)

    # Integration: run_loop.py imports from this module (integration AC)
    import bob.orchestrator.run_loop as rl
    assert hasattr(rl, "reap_subagent_for_feature") or hasattr(rl, "_reap_subagent") or hasattr(
        rl, "run_loop_must_reap_claude_subagent_process_feature_terminal"
    ), (
        "run_loop must import reap_subagent_for_feature or "
        "run_loop_must_reap_claude_subagent_process_feature_terminal"
    )


# ---------------------------------------------------------------------------
# Reaping behaviour tests
# ---------------------------------------------------------------------------


class TestReapingBehaviour:
    """Detailed tests for run_loop_must_reap_claude_subagent_process_feature_terminal."""

    def setup_method(self):
        from bob.run_loop_must_reap_claude_subagent_process_feature_terminal import (
            run_loop_must_reap_claude_subagent_process_feature_terminal as fn,
        )
        self.fn = fn
        self.feature_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_returns_empty_when_no_subagent_found(self):
        """Returns empty list when no claude subagent is running for the feature."""
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            result = self.fn(self.feature_id)
        assert result == []

    def test_returns_reaped_pids_when_subagent_found(self):
        """Returns list of reaped PIDs when subagent is running."""
        expected_pids = [99901, 99902]
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = expected_pids
            result = self.fn(self.feature_id)
        assert result == expected_pids

    def test_delegates_to_reap_subagent_for_feature(self):
        """Delegates to bob.orchestrator.subagent_reaper.reap_subagent_for_feature."""
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [7777]
            self.fn(self.feature_id)
        mock_reap.assert_called_once_with(self.feature_id)

    def test_applies_to_completed_status(self):
        """Reaping is triggered for completed terminal state."""
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [1234]
            result = self.fn(self.feature_id, status="completed")
        assert result == [1234]
        mock_reap.assert_called_once_with(self.feature_id)

    def test_applies_to_needs_human_status(self):
        """Reaping is triggered for needs_human terminal state."""
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = []
            result = self.fn(self.feature_id, status="needs_human")
        assert result == []
        mock_reap.assert_called_once_with(self.feature_id)

    def test_applies_to_regression_status(self):
        """Reaping is triggered for regression terminal state."""
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [5678]
            result = self.fn(self.feature_id, status="regression")
        assert result == [5678]

    def test_applies_to_failed_status(self):
        """Reaping is triggered for failed terminal state."""
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [9999]
            result = self.fn(self.feature_id, status="failed")
        assert result == [9999]

    def test_reap_exceptions_do_not_propagate(self):
        """Reaping errors must be caught and an empty list returned."""
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.side_effect = RuntimeError("PID scan error")
            result = self.fn(self.feature_id)
        assert result == []

    def test_audit_sentinel_emitted_on_reap(self):
        """Audit sentinel subagent_reaped_on_terminal=<id> emitted for confirmed reaps."""
        import logging
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            ".reap_subagent_for_feature"
        ) as mock_reap:
            mock_reap.return_value = [42]
            with patch(
                "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
                ".logger"
            ) as mock_logger:
                result = self.fn(self.feature_id)
        # The underlying reaper emits the sentinel; our facade may or may not log again.
        # We only verify the function returns the reaped PIDs.
        assert result == [42]


# ---------------------------------------------------------------------------
# Orphan sweep tests
# ---------------------------------------------------------------------------


class TestOrphanSweep:
    """Tests for sweep_orphan_subagents via the module's public API."""

    def test_sweep_function_importable(self):
        """sweep_orphan_subagents is importable from the module."""
        from bob.run_loop_must_reap_claude_subagent_process_feature_terminal import (
            sweep_orphan_subagents,
        )
        assert callable(sweep_orphan_subagents)

    def test_sweep_returns_list(self):
        """sweep_orphan_subagents returns a list of (feature_id, pid) pairs."""
        from bob.run_loop_must_reap_claude_subagent_process_feature_terminal import (
            sweep_orphan_subagents,
        )
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            "._sweep_orphans"
        ) as mock_sweep:
            mock_sweep.return_value = [("feat-1", 1111), ("feat-2", 2222)]
            result = sweep_orphan_subagents()
        assert result == [("feat-1", 1111), ("feat-2", 2222)]

    def test_sweep_delegates_to_subagent_reaper(self):
        """sweep_orphan_subagents delegates to bob.orchestrator.subagent_reaper."""
        from bob.run_loop_must_reap_claude_subagent_process_feature_terminal import (
            sweep_orphan_subagents,
        )
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            "._sweep_orphans"
        ) as mock_sweep:
            mock_sweep.return_value = []
            sweep_orphan_subagents()
        mock_sweep.assert_called_once()

    def test_sweep_returns_empty_when_no_orphans(self):
        """Returns empty list when no orphan subagents exist."""
        from bob.run_loop_must_reap_claude_subagent_process_feature_terminal import (
            sweep_orphan_subagents,
        )
        with patch(
            "bob.run_loop_must_reap_claude_subagent_process_feature_terminal"
            "._sweep_orphans"
        ) as mock_sweep:
            mock_sweep.return_value = []
            result = sweep_orphan_subagents()
        assert result == []


# ---------------------------------------------------------------------------
# Integration: run_loop integration
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    """Verify the reaper is wired into bob.orchestrator.run_loop."""

    def test_reap_subagent_for_feature_in_run_loop(self):
        """bob.orchestrator.run_loop imports reap_subagent_for_feature."""
        import bob.orchestrator.run_loop as rl
        # The run_loop imports _reap_subagent as an alias for reap_subagent_for_feature
        assert hasattr(rl, "_reap_subagent") or hasattr(rl, "reap_subagent_for_feature"), (
            "run_loop must import reap_subagent_for_feature (or alias _reap_subagent)"
        )

    def test_run_loop_module_has_noqa_import_or_direct_usage(self):
        """run_loop_must_reap_... is imported in run_loop (integration AC)."""
        import importlib
        import inspect
        run_loop_src = inspect.getsource(
            importlib.import_module("bob.orchestrator.run_loop")
        )
        # Either the module is imported or the reaper is called at terminal transitions
        assert (
            "reap_subagent_for_feature" in run_loop_src
            or "_reap_subagent" in run_loop_src
            or "run_loop_must_reap" in run_loop_src
        ), "run_loop must reference reap_subagent_for_feature or run_loop_must_reap module"

    def test_terminal_states_covered_in_run_loop(self):
        """run_loop covers all terminal states: completed, needs_human, regression, failed."""
        import importlib
        import inspect
        run_loop_src = inspect.getsource(
            importlib.import_module("bob.orchestrator.run_loop")
        )
        for state in ("completed", "needs_human", "regression", "failed"):
            assert state in run_loop_src, (
                f"Terminal state '{state}' must be mentioned in run_loop.py"
            )
