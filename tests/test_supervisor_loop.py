"""Tests for bob.supervisor_loop.auto_resume_run.

Feature 27e4c777: `bob run --all` MUST auto-resume after a would-be
QUEUE_DRAINED exit instead of halting the whole unattended build.
"""

from __future__ import annotations

import pytest

from bob.supervisor_loop import (
    ResumeDecision,
    auto_resume_run,
    RECOVERABLE_FAILURE_STATUSES,
)


def _feat(fid, status, depends_on=None):
    return {"id": fid, "status": status, "depends_on": depends_on or []}


def test_runnable_pending_triggers_resume_without_reset():
    """A pending feature with all deps completed => resume, no resets needed."""
    features = [
        _feat("a", "completed"),
        _feat("b", "pending", depends_on=["a"]),
    ]
    decision = auto_resume_run(features)
    assert isinstance(decision, ResumeDecision)
    assert decision.should_resume is True
    assert decision.reset_feature_ids == []
    assert decision.terminate_reason is None


def test_transient_failed_sibling_is_reset_and_resumes():
    """Pending blocked only by a transient-failed non-needs_human sibling =>
    reset the sibling to pending and resume."""
    features = [
        _feat("dep", "failed"),
        _feat("b", "pending", depends_on=["dep"]),
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert "dep" in decision.reset_feature_ids
    assert decision.terminate_reason is None


@pytest.mark.parametrize("status", sorted(RECOVERABLE_FAILURE_STATUSES))
def test_each_recoverable_status_is_resettable(status):
    features = [
        _feat("dep", status),
        _feat("b", "pending", depends_on=["dep"]),
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert "dep" in decision.reset_feature_ids


def test_reset_fn_called_for_each_reset_id():
    calls = []
    features = [
        _feat("dep", "timeout"),
        _feat("b", "pending", depends_on=["dep"]),
    ]
    decision = auto_resume_run(features, reset_fn=lambda fid: calls.append(fid))
    assert calls == ["dep"]
    assert decision.reset_feature_ids == ["dep"]


def test_executing_feature_never_reset():
    """A live executing feature must never be reset even if a pending depends on it."""
    features = [
        _feat("dep", "executing"),
        _feat("b", "pending", depends_on=["dep"]),
    ]
    decision = auto_resume_run(features)
    assert "dep" not in decision.reset_feature_ids
    # Executing dep means work is in flight — resume the loop, don't terminate.
    assert decision.should_resume is True
    assert decision.terminate_reason is None


def test_needs_human_block_terminates():
    """Pending blocked transitively only by a needs_human feature => terminate."""
    features = [
        _feat("human", "needs_human"),
        _feat("b", "pending", depends_on=["human"]),
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is False
    assert decision.reset_feature_ids == []
    assert decision.terminate_reason == "BLOCKED_ON_HUMAN"


def test_transitive_needs_human_block_terminates():
    """b depends on failed dep, but dep depends on needs_human => not recoverable."""
    features = [
        _feat("human", "needs_human"),
        _feat("dep", "failed", depends_on=["human"]),
        _feat("b", "pending", depends_on=["dep"]),
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is False
    assert decision.reset_feature_ids == []
    assert decision.terminate_reason == "BLOCKED_ON_HUMAN"


def test_no_pending_terminates_queue_empty():
    features = [
        _feat("a", "completed"),
        _feat("b", "completed"),
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is False
    assert decision.terminate_reason == "QUEUE_EMPTY"


def test_executing_present_but_no_pending_resumes():
    """Executing work in flight with no pending => keep running (don't terminate)."""
    features = [
        _feat("a", "executing"),
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert decision.terminate_reason is None


def test_mixed_recoverable_and_human_resets_only_recoverable():
    features = [
        _feat("human", "needs_human"),
        _feat("blocked", "pending", depends_on=["human"]),
        _feat("failed_dep", "failed"),
        _feat("runnable", "pending", depends_on=["failed_dep"]),
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert decision.reset_feature_ids == ["failed_dep"]


def test_object_features_supported():
    class F:
        def __init__(self, id, status, depends_on=None):
            self.id = id
            self.status = status
            self.depends_on = depends_on or []

    features = [F("dep", "failed"), F("b", "pending", ["dep"])]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert decision.reset_feature_ids == ["dep"]


def test_decision_is_stable_ordered():
    features = [
        _feat("d2", "failed"),
        _feat("d1", "timeout"),
        _feat("b", "pending", depends_on=["d1", "d2"]),
    ]
    decision = auto_resume_run(features)
    # Reset ids preserve input order.
    assert decision.reset_feature_ids == ["d2", "d1"]
