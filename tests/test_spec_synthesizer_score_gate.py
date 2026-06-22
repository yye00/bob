"""Tests for bob3.spec_synthesizer.score_gate_loop.

Verifies the score-gate loop: re-synthesizes TBD ACs until the composite
score reaches the threshold, caps at max_retries, falls through to
deterministic_fallback on exhaustion, and reports gate_passed/gate_failed/
gate_avg_attempts in the returned ScoreGateReport.

Feature: 8da05a00-87ae-44af-8140-3c75115432e2 — Spec synthesizer score-gate
loop — re-synthesize TBD ACs until score reaches threshold.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from bob3.spec_synthesizer import (
    ScoreGateReport,
    score_gate_loop,
    score_gate_threshold_from_env,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


_HIGH_QUALITY_ACS = [
    "File exists: src/bob3/score_gate.py",
    "Function defined: bob3.score_gate.run",
    "pytest: tests/test_score_gate.py::test_raises_on_invalid_input",
    "pytest: tests/test_score_gate.py::test_returns_none_on_empty_input",
    "pytest: tests/test_score_gate_boundary.py -- empty input returns well-defined result",
    "pytest: tests/test_score_gate_error.py -- invalid input raises ValueError",
]

_LOW_QUALITY_ACS = [
    "The feature works properly",
    "It handles multiple cases correctly",
]


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------

def test_score_gate_loop_is_callable():
    assert callable(score_gate_loop)


def test_score_gate_report_is_dataclass():
    report = ScoreGateReport(
        gate_passed=True,
        gate_failed=False,
        gate_avg_attempts=1,
        criteria=["File exists: src/bob3/foo.py"],
        composite=0.9,
        rationale=["good"],
    )
    assert report.gate_passed is True
    assert report.gate_failed is False
    assert report.gate_avg_attempts == 1
    assert report.composite == 0.9


# ---------------------------------------------------------------------------
# Gate passes on first attempt
# ---------------------------------------------------------------------------

def test_gate_passes_on_first_attempt_with_high_quality_acs():
    good_synth = AsyncMock(return_value=_HIGH_QUALITY_ACS)

    report = _run(score_gate_loop(
        synthesize_fn=good_synth,
        title="Score gate feature",
        description="Raises ValueError on invalid input and returns None on empty.",
        project_id="proj-001",
        threshold=0.0,
        max_retries=3,
    ))

    assert isinstance(report, ScoreGateReport)
    assert report.gate_passed is True
    assert report.gate_failed is False
    assert report.gate_avg_attempts == 1
    assert report.criteria == _HIGH_QUALITY_ACS
    good_synth.assert_called_once()


# ---------------------------------------------------------------------------
# Gate retries when below threshold
# ---------------------------------------------------------------------------

def test_gate_retries_when_below_threshold():
    call_count = 0

    async def improving_synth(**kwargs):
        nonlocal call_count
        call_count += 1
        return _LOW_QUALITY_ACS if call_count == 1 else _HIGH_QUALITY_ACS

    report = _run(score_gate_loop(
        synthesize_fn=improving_synth,
        title="Retrying gate feature",
        description="Feature with error handling and boundary conditions.",
        project_id="proj-002",
        threshold=0.5,
        max_retries=3,
    ))

    assert call_count >= 2
    assert report.gate_avg_attempts >= 2


# ---------------------------------------------------------------------------
# Falls back to deterministic criteria after max retries
# ---------------------------------------------------------------------------

def test_falls_back_after_max_retries_exhausted():
    always_bad = AsyncMock(return_value=_LOW_QUALITY_ACS)

    report = _run(score_gate_loop(
        synthesize_fn=always_bad,
        title="fallback gate feature",
        description="does something simple.",
        project_id="proj-003",
        threshold=1.0,
        max_retries=3,
        use_fallback=True,
    ))

    assert isinstance(report, ScoreGateReport)
    assert report.gate_failed is True
    assert report.criteria is not None
    assert len(report.criteria) >= 3
    assert report.gate_avg_attempts == 3


# ---------------------------------------------------------------------------
# gate_passed and gate_failed are mutually exclusive
# ---------------------------------------------------------------------------

def test_gate_passed_and_gate_failed_are_mutually_exclusive_on_pass():
    good_synth = AsyncMock(return_value=_HIGH_QUALITY_ACS)

    report = _run(score_gate_loop(
        synthesize_fn=good_synth,
        title="exclusive gate feature",
        description="checks boundary and error paths.",
        project_id="proj-004",
        threshold=0.0,
    ))

    assert report.gate_passed is True
    assert report.gate_failed is False
    assert report.gate_passed != report.gate_failed


def test_gate_passed_and_gate_failed_are_mutually_exclusive_on_fail():
    always_bad = AsyncMock(return_value=_LOW_QUALITY_ACS)

    report = _run(score_gate_loop(
        synthesize_fn=always_bad,
        title="exclusive fail gate feature",
        description="does something.",
        project_id="proj-005",
        threshold=1.0,
        max_retries=1,
        use_fallback=True,
    ))

    assert report.gate_passed is False
    assert report.gate_failed is True
    assert report.gate_passed != report.gate_failed


# ---------------------------------------------------------------------------
# retry_feedback is passed to synthesize_fn on subsequent attempts
# ---------------------------------------------------------------------------

def test_retry_feedback_is_none_on_first_attempt_and_string_on_retry():
    received_feedbacks: list = []

    async def capture_feedback_fn(**kwargs):
        received_feedbacks.append(kwargs.get("retry_feedback"))
        return _LOW_QUALITY_ACS

    _run(score_gate_loop(
        synthesize_fn=capture_feedback_fn,
        title="retry feedback feature",
        description="needs error and boundary ACs.",
        project_id="proj-006",
        threshold=1.0,
        max_retries=2,
        use_fallback=True,
    ))

    assert received_feedbacks[0] is None
    assert received_feedbacks[1] is not None
    assert isinstance(received_feedbacks[1], str)
    assert len(received_feedbacks[1]) > 0


# ---------------------------------------------------------------------------
# synthesize_fn returning None triggers fallback
# ---------------------------------------------------------------------------

def test_synthesize_returning_none_triggers_fallback():
    always_none = AsyncMock(return_value=None)

    report = _run(score_gate_loop(
        synthesize_fn=always_none,
        title="none synth gate feature",
        description="does something.",
        project_id="proj-007",
        max_retries=2,
        use_fallback=True,
    ))

    assert isinstance(report, ScoreGateReport)
    assert report.gate_failed is True
    assert report.criteria is not None


# ---------------------------------------------------------------------------
# gate_avg_attempts reflects actual attempts used
# ---------------------------------------------------------------------------

def test_gate_avg_attempts_reflects_actual_attempts():
    call_count = 0

    async def third_time_lucky(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return _LOW_QUALITY_ACS
        return _HIGH_QUALITY_ACS

    report = _run(score_gate_loop(
        synthesize_fn=third_time_lucky,
        title="third attempt gate feature",
        description="raises ValueError on invalid input; returns None on empty.",
        project_id="proj-008",
        threshold=0.3,
        max_retries=5,
    ))

    assert report.gate_passed is True
    assert report.gate_avg_attempts == 3


# ---------------------------------------------------------------------------
# Report has required keys/attributes
# ---------------------------------------------------------------------------

def test_report_has_all_required_attributes():
    good_synth = AsyncMock(return_value=_HIGH_QUALITY_ACS)

    report = _run(score_gate_loop(
        synthesize_fn=good_synth,
        title="keys check gate feature",
        description="verifies AC attribute completeness.",
        project_id="proj-009",
        threshold=0.0,
    ))

    assert hasattr(report, "gate_passed")
    assert hasattr(report, "gate_failed")
    assert hasattr(report, "gate_avg_attempts")
    assert hasattr(report, "criteria")
    assert hasattr(report, "composite")
    assert hasattr(report, "rationale")
    assert isinstance(report.composite, float)
    assert isinstance(report.rationale, list)


# ---------------------------------------------------------------------------
# use_fallback=False raises ValueError on exhaustion
# ---------------------------------------------------------------------------

def test_no_fallback_raises_value_error_on_exhaustion():
    always_none = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="score_gate_loop"):
        _run(score_gate_loop(
            synthesize_fn=always_none,
            title="no fallback gate feature",
            description="does something.",
            project_id="proj-010",
            max_retries=2,
            use_fallback=False,
        ))


# ---------------------------------------------------------------------------
# threshold default from environment
# ---------------------------------------------------------------------------

def test_threshold_default_reads_from_env(monkeypatch):
    monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD", raising=False)
    assert score_gate_threshold_from_env() == 0.85

    monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "0.7")
    assert abs(score_gate_threshold_from_env() - 0.7) < 1e-9
