"""Boundary tests for bob.supervisor_loop.auto_resume_run.

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

from bob.supervisor_loop import ResumeDecision, auto_resume_run


def test_empty_feature_list_returns_terminate_not_raises():
    decision = auto_resume_run([])
    assert isinstance(decision, ResumeDecision)
    assert decision.should_resume is False
    assert decision.reset_feature_ids == []
    assert decision.terminate_reason == "QUEUE_EMPTY"


def test_single_completed_feature_terminates_cleanly():
    decision = auto_resume_run([{"id": "a", "status": "completed"}])
    assert decision.should_resume is False
    assert decision.terminate_reason == "QUEUE_EMPTY"


def test_single_pending_no_deps_resumes():
    decision = auto_resume_run([{"id": "a", "status": "pending"}])
    assert decision.should_resume is True
    assert decision.reset_feature_ids == []
    assert decision.terminate_reason is None


def test_single_needs_human_only_terminates():
    decision = auto_resume_run([{"id": "a", "status": "needs_human"}])
    assert decision.should_resume is False
    # No pending remain -> queue empty of runnable work.
    assert decision.terminate_reason == "QUEUE_EMPTY"
