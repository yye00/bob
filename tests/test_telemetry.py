"""Tests for telemetry module — RunTelemetry, TaskTelemetry, etc."""

import json
import time
from pathlib import Path

import pytest

from bob.observability.telemetry import RunTelemetry, TaskTelemetry, TaskAttempt


class TestRunTelemetry:
    """Test RunTelemetry lifecycle and persistence."""

    def test_init_creates_telemetry_dir(self, tmp_path):
        """Test that initialization creates the telemetry directory."""
        rt = RunTelemetry(workspace=tmp_path)
        assert (tmp_path / ".bob" / "telemetry").exists()

    def test_start_run(self, tmp_path):
        """Test starting a run records start time."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        assert rt.start_time is not None
        assert rt.start_time > 0

    def test_end_run(self, tmp_path):
        """Test ending a run records end time and persists."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.end_run()
        assert rt.end_time is not None
        assert rt.end_time >= rt.start_time
        # File should be persisted
        tel_dir = tmp_path / ".bob" / "telemetry"
        files = list(tel_dir.glob("run-*.json"))
        assert len(files) == 1

    def test_custom_run_id(self, tmp_path):
        """Test creating telemetry with a custom run ID."""
        rt = RunTelemetry(workspace=tmp_path, run_id="test-run-42")
        assert rt.run_id == "test-run-42"

    def test_start_task_attempt(self, tmp_path):
        """Test recording a task attempt start."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(
            task_id="t1", spec_id="F001", title="Test Task", model="sonnet"
        )
        assert "t1" in rt.tasks
        assert rt.tasks["t1"].spec_id == "F001"
        assert rt.tasks["t1"].total_attempts == 1
        assert rt.total_iterations == 1

    def test_end_task_attempt_success(self, tmp_path):
        """Test recording a successful task attempt end."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.end_task_attempt(task_id="t1", success=True)
        assert rt.tasks["t1"].final_status == "completed"
        assert len(rt.tasks["t1"].attempts) == 1
        assert rt.tasks["t1"].attempts[0]["success"] is True

    def test_end_task_attempt_failure(self, tmp_path):
        """Test recording a failed task attempt end."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.end_task_attempt(task_id="t1", success=False, error_message="boom")
        assert "boom" in rt.tasks["t1"].error_messages
        assert len(rt.tasks["t1"].attempts) == 1
        assert rt.tasks["t1"].attempts[0]["success"] is False

    def test_record_verification(self, tmp_path):
        """Test recording verification results."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.record_verification(task_id="t1", passed=True, message="All good")
        assert len(rt.tasks["t1"].verification_results) == 1
        assert rt.tasks["t1"].verification_results[0]["passed"] is True

    def test_record_debug(self, tmp_path):
        """Test recording debug attempt results."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.record_debug(task_id="t1", debug_attempt=1, success=False, error_message="still broken")
        # Debug records go into attempts list
        found_debug = False
        for a in rt.tasks["t1"].attempts:
            if a.get("type") == "debug":
                found_debug = True
                assert a["debug_attempt"] == 1
                assert a["success"] is False
        assert found_debug

    def test_record_escalation(self, tmp_path):
        """Test recording model escalation."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.record_escalation(task_id="t1", from_model="sonnet", to_model="opus", reason="too hard")
        assert len(rt.tasks["t1"].escalations) == 1
        assert rt.tasks["t1"].escalations[0]["to_model"] == "opus"

    def test_record_stall(self, tmp_path):
        """Test recording stall detection."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.record_stall(task_id="t1", stall_duration_seconds=600.0)
        assert any("Stall" in msg for msg in rt.tasks["t1"].error_messages)

    def test_set_task_final_status(self, tmp_path):
        """Test setting final task status."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Test", model="sonnet")
        rt.set_task_final_status("t1", "failed")
        assert rt.tasks["t1"].final_status == "failed"

    def test_get_summary(self, tmp_path):
        """Test getting a run summary."""
        rt = RunTelemetry(workspace=tmp_path, run_id="test-run")
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Task 1", model="sonnet")
        rt.end_task_attempt(task_id="t1", success=True)
        rt.set_task_final_status("t1", "completed")
        rt.start_task_attempt(task_id="t2", spec_id="F002", title="Task 2", model="sonnet")
        rt.end_task_attempt(task_id="t2", success=False, error_message="fail")
        rt.set_task_final_status("t2", "failed")
        rt.end_run()

        summary = rt.get_summary()
        assert summary["run_id"] == "test-run"
        assert summary["tasks_completed"] == 1
        assert summary["tasks_failed"] == 1
        assert summary["total_tasks"] == 2
        assert summary["total_attempts"] == 2
        assert summary["wall_clock_seconds"] >= 0

    def test_debug_attempt_increments_count(self, tmp_path):
        """Test that debug attempts increment the debug counter."""
        rt = RunTelemetry(workspace=tmp_path)
        rt.start_run()
        rt.start_task_attempt(
            task_id="t1", spec_id="F001", title="Test",
            model="sonnet", is_debug=True, debug_attempt_number=1,
        )
        assert rt.tasks["t1"].debug_attempts == 1
        rt.end_task_attempt(task_id="t1", success=False, error_message="nope")

        rt.start_task_attempt(
            task_id="t1", spec_id="F001", title="Test",
            model="sonnet", is_debug=True, debug_attempt_number=2,
        )
        assert rt.tasks["t1"].debug_attempts == 2
        assert rt.tasks["t1"].total_attempts == 2

    def test_persist_and_load(self, tmp_path):
        """Test persisting and loading telemetry data."""
        rt = RunTelemetry(workspace=tmp_path, run_id="persist-test")
        rt.start_run()
        rt.start_task_attempt(task_id="t1", spec_id="F001", title="Persist Test", model="sonnet")
        rt.end_task_attempt(task_id="t1", success=True)
        rt.end_run()

        # Load the file
        filepath = tmp_path / ".bob" / "telemetry" / "persist-test.json"
        assert filepath.exists()
        data = RunTelemetry.load(filepath)
        assert data["run_id"] == "persist-test"
        assert data["tasks_completed"] == 0  # completed status not set via set_task_final_status
        assert len(data["tasks"]) == 1

    def test_list_runs(self, tmp_path):
        """Test listing runs."""
        # Create two runs
        rt1 = RunTelemetry(workspace=tmp_path, run_id="run-001")
        rt1.start_run()
        rt1.end_run()

        time.sleep(0.05)  # Ensure different mtimes

        rt2 = RunTelemetry(workspace=tmp_path, run_id="run-002")
        rt2.start_run()
        rt2.end_run()

        runs = RunTelemetry.list_runs(tmp_path)
        assert len(runs) == 2
        # Newest first
        assert "run-002" in runs[0].name

    def test_list_runs_empty(self, tmp_path):
        """Test listing runs when no telemetry exists."""
        runs = RunTelemetry.list_runs(tmp_path)
        assert runs == []


class TestTaskAttemptDataclass:
    """Test the TaskAttempt dataclass."""

    def test_default_values(self):
        """Test TaskAttempt default values."""
        ta = TaskAttempt(attempt_number=1, started_at="2024-01-01T00:00:00Z")
        assert ta.attempt_number == 1
        assert ta.success is False
        assert ta.is_debug is False
        assert ta.debug_attempt_number is None
        assert ta.error_message is None
        assert ta.stall_detected is False

    def test_debug_attempt(self):
        """Test creating a debug attempt."""
        ta = TaskAttempt(
            attempt_number=2,
            started_at="2024-01-01T00:00:00Z",
            is_debug=True,
            debug_attempt_number=1,
        )
        assert ta.is_debug is True
        assert ta.debug_attempt_number == 1


class TestTaskTelemetry:
    """Test TaskTelemetry dataclass."""

    def test_default_values(self):
        """Test default values."""
        tt = TaskTelemetry(task_id="t1", spec_id="F001", title="Test")
        assert tt.total_attempts == 0
        assert tt.debug_attempts == 0
        assert tt.verification_results == []
        assert tt.error_messages == []
        assert tt.attempts == []
        assert tt.escalations == []
