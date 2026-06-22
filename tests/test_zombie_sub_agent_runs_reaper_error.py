"""Error-path tests for bob3.zombie_reaper.reap_zombie_runs.

AC: pytest: tests/test_zombie_sub_agent_runs_reaper_error.py
    — invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob3.zombie_reaper import reap_zombie_runs
from bob3.sub_agent_runs_reaper import reap_zombie_runs as reap_from_sub_agent_module


class TestInvalidProjectId:
    """Passing None or empty string must raise ValueError immediately."""

    def test_none_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_from_sub_agent_module(None)

    def test_empty_string_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_from_sub_agent_module("")

    def test_whitespace_only_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_from_sub_agent_module("   ")

    def test_raises_not_silently_succeeds_on_none(self):
        """The function must NOT return [] when given None — it must raise."""
        try:
            result = reap_from_sub_agent_module(None)
        except ValueError:
            return  # correct behaviour
        except Exception as exc:
            pytest.fail(f"Expected ValueError but got {type(exc).__name__}: {exc}")
        pytest.fail(
            f"Expected ValueError but function returned {result!r} silently — "
            "invalid input must not succeed"
        )

    def test_raises_not_silently_succeeds_on_empty(self):
        """The function must NOT return [] when given '' — it must raise."""
        try:
            result = reap_from_sub_agent_module("")
        except ValueError:
            return  # correct behaviour
        except Exception as exc:
            pytest.fail(f"Expected ValueError but got {type(exc).__name__}: {exc}")
        pytest.fail(
            f"Expected ValueError but function returned {result!r} silently — "
            "invalid input must not succeed"
        )

    def test_error_message_contains_project_id(self):
        """ValueError message must be informative."""
        with pytest.raises(ValueError, match="project_id"):
            reap_from_sub_agent_module(None)

    def test_tab_only_project_id_raises_value_error(self):
        with pytest.raises(ValueError):
            reap_from_sub_agent_module("\t")


class TestOrchestratorFindZombieRunsValidation:
    """The underlying find_zombie_runs should propagate errors from db correctly."""

    def test_db_error_is_not_swallowed_in_find(self):
        from unittest.mock import patch

        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.side_effect = RuntimeError("db failure")
            from bob3.orchestrator.zombie_run_reaper import find_zombie_runs

            with pytest.raises(RuntimeError, match="db failure"):
                find_zombie_runs("proj-db-error")

    def test_single_reap_failure_does_not_abort_others(self):
        """scan_and_reap logs and skips failed reaps, returning partial results."""
        from unittest.mock import MagicMock, patch
        from datetime import datetime, timezone

        def make_run(run_id, target_id):
            r = MagicMock()
            r.id = run_id
            r.purpose = "test"
            r.target_id = target_id
            return r

        def make_feature(feature_id):
            f = MagicMock()
            f.id = feature_id
            return f

        run_ok = make_run("run-ok", "feat-ok")
        run_bad = make_run("run-bad", "feat-bad")
        feat_ok = make_feature("feat-ok")
        feat_bad = make_feature("feat-bad")

        call_count = {"n": 0}

        def update_side_effect(run_id, **kwargs):
            if run_id == "run-bad":
                raise RuntimeError("update failed")

        with patch("bob3.orchestrator.zombie_run_reaper.db") as mock_db:
            mock_db.query_agent_runs.return_value = [run_ok, run_bad]
            mock_db.list_features.side_effect = lambda project_id, status: (
                [feat_ok, feat_bad] if status == "completed" else []
            )
            mock_db.update_agent_run.side_effect = update_side_effect
            from bob3.orchestrator.zombie_run_reaper import scan_and_reap

            result = scan_and_reap("proj-partial")

        # run-ok should be reaped; run-bad should be skipped (not in result)
        assert "run-ok" in result
        assert "run-bad" not in result
