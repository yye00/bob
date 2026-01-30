"""Tests for new event types added in Phase 1."""

from bob.observability.logger import EventType


class TestNewEventTypes:
    """Test that all new event types are defined."""

    def test_verification_events(self):
        assert EventType.VERIFICATION_FAILED.value == "verification_failed"
        assert EventType.VERIFICATION_PASSED.value == "verification_passed"

    def test_debug_mode_events(self):
        assert EventType.DEBUG_MODE_ENTERED.value == "debug_mode_entered"
        assert EventType.DEBUG_MODE_SUCCEEDED.value == "debug_mode_succeeded"
        assert EventType.DEBUG_MODE_FAILED.value == "debug_mode_failed"

    def test_attempt_events(self):
        assert EventType.ATTEMPT_STARTED.value == "attempt_started"
        assert EventType.ATTEMPT_COMPLETED.value == "attempt_completed"
        assert EventType.ATTEMPT_TIMEOUT.value == "attempt_timeout"

    def test_run_events(self):
        assert EventType.RUN_STARTED.value == "run_started"
        assert EventType.RUN_COMPLETED.value == "run_completed"

    def test_stall_event(self):
        assert EventType.STALL_DETECTED.value == "stall_detected"

    def test_original_events_still_exist(self):
        """Ensure backward compatibility — original events unchanged."""
        assert EventType.TASK_STARTED.value == "task_started"
        assert EventType.TASK_COMPLETED.value == "task_completed"
        assert EventType.TASK_FAILED.value == "task_failed"
        assert EventType.SESSION_STARTED.value == "session_started"
        assert EventType.SESSION_ENDED.value == "session_ended"
        assert EventType.ESCALATION_TRIGGERED.value == "escalation_triggered"
        assert EventType.RESEARCH_STARTED.value == "research_started"
        assert EventType.RESEARCH_COMPLETED.value == "research_completed"
        assert EventType.DECOMPOSITION_STARTED.value == "decomposition_started"
        assert EventType.DECOMPOSITION_COMPLETED.value == "decomposition_completed"
        assert EventType.CHECKPOINT_CREATED.value == "checkpoint_created"
        assert EventType.CHECKPOINT_RESTORED.value == "checkpoint_restored"
