"""Feature ac644c8b: bob run MUST auto-resume after QUEUE_DRAINED.

Core behavioural tests for the unattended-build supervisor loop. The queue
draining must NOT halt the build when runnable/recoverable pending work remains;
it must terminate only when there is no pending work (``QUEUE_EMPTY``) or every
remaining pending feature is transitively blocked by human-gated work
(``BLOCKED_ON_HUMAN``). A live ``executing`` feature is never reset.
"""

from __future__ import annotations

import importlib

from bob.supervisor_loop import (
    RECOVERABLE_FAILURE_STATUSES,
    RUNNABLE_STATUSES,
    ResumeDecision,
    auto_resume_run,
    supervise_run,
)


# --- module / symbol presence (AC: File exists + Function defined) -----------


def test_module_exposes_required_symbols():
    assert callable(auto_resume_run)
    assert callable(supervise_run)


def test_cli_integration_importable():
    # AC: integration: bob.cli
    cli = importlib.import_module("bob.cli")
    assert cli is not None


# --- resume when runnable pending remains ------------------------------------


def test_pending_with_completed_deps_resumes_without_reset():
    features = [
        {"id": "dep", "status": "completed"},
        {"id": "b", "status": "pending", "depends_on": ["dep"]},
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert decision.reset_feature_ids == []
    assert decision.terminate_reason is None


def test_pending_blocked_only_by_transient_failed_sibling_resets_and_resumes():
    resets: list[str] = []
    features = [
        {"id": "dep", "status": "failed"},
        {"id": "b", "status": "pending", "depends_on": ["dep"]},
    ]
    decision = auto_resume_run(features, reset_fn=resets.append)
    assert decision.should_resume is True
    assert decision.reset_feature_ids == ["dep"]
    assert resets == ["dep"]
    assert decision.terminate_reason is None


def test_all_recoverable_failure_statuses_reset():
    for status in sorted(RECOVERABLE_FAILURE_STATUSES):
        features = [
            {"id": "dep", "status": status},
            {"id": "b", "status": "pending", "depends_on": ["dep"]},
        ]
        decision = auto_resume_run(features)
        assert decision.should_resume is True, status
        assert decision.reset_feature_ids == ["dep"], status


# --- WIP preservation --------------------------------------------------------


def test_executing_feature_is_never_reset():
    resets: list[str] = []
    features = [
        {"id": "live", "status": "executing"},
        {"id": "b", "status": "pending", "depends_on": ["live"]},
    ]
    decision = auto_resume_run(features, reset_fn=resets.append)
    assert decision.should_resume is True
    assert "live" not in decision.reset_feature_ids
    assert resets == []


def test_executing_only_keeps_loop_alive():
    decision = auto_resume_run([{"id": "live", "status": "executing"}])
    assert decision.should_resume is True
    assert decision.terminate_reason is None


# --- terminate conditions ----------------------------------------------------


def test_no_pending_terminates_queue_empty():
    features = [
        {"id": "a", "status": "completed"},
        {"id": "b", "status": "completed"},
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is False
    assert decision.terminate_reason == "QUEUE_EMPTY"


def test_pending_blocked_by_needs_human_terminates():
    features = [
        {"id": "gate", "status": "needs_human"},
        {"id": "b", "status": "pending", "depends_on": ["gate"]},
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is False
    assert decision.terminate_reason == "BLOCKED_ON_HUMAN"


def test_pending_transitively_blocked_by_needs_human_terminates():
    features = [
        {"id": "gate", "status": "needs_human"},
        {"id": "mid", "status": "failed", "depends_on": ["gate"]},
        {"id": "b", "status": "pending", "depends_on": ["mid"]},
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is False
    assert decision.terminate_reason == "BLOCKED_ON_HUMAN"


# --- mixed graphs: at least one advanceable pending -> resume ----------------


def test_mixed_one_advanceable_one_blocked_resumes():
    features = [
        {"id": "gate", "status": "needs_human"},
        {"id": "blocked", "status": "pending", "depends_on": ["gate"]},
        {"id": "dep", "status": "failed"},
        {"id": "ok", "status": "pending", "depends_on": ["dep"]},
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert "dep" in decision.reset_feature_ids


def test_dependency_cycle_does_not_loop_forever():
    features = [
        {"id": "a", "status": "failed", "depends_on": ["b"]},
        {"id": "b", "status": "failed", "depends_on": ["a"]},
        {"id": "c", "status": "pending", "depends_on": ["a"]},
    ]
    # Cycle is treated as non-recoverable -> no advanceable pending -> terminate.
    decision = auto_resume_run(features)
    assert decision.should_resume is False
    assert decision.terminate_reason == "BLOCKED_ON_HUMAN"


# --- purity: no reset_fn means no persistence but ids still reported ---------


def test_no_reset_fn_reports_ids_without_side_effects():
    features = [
        {"id": "dep", "status": "timeout"},
        {"id": "b", "status": "pending", "depends_on": ["dep"]},
    ]
    decision = auto_resume_run(features)
    assert decision.should_resume is True
    assert decision.reset_feature_ids == ["dep"]


def test_runnable_statuses_constant():
    assert "pending" in RUNNABLE_STATUSES
    assert "ready" in RUNNABLE_STATUSES
