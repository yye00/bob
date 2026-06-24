"""Tests for the 0.85 threshold boundary in the quality gate.

AC: tests/test_quality_score_threshold_boundary_0_85.py asserts
    gate_for_ready returns True at exactly 0.85 minimum threshold
"""

from __future__ import annotations

import pytest

from bob.spec_quality.quality_score import (
    QualityReport,
    ScoreComponents,
    gate_for_ready,
    score_threshold,
)

THRESHOLD = 0.85


@pytest.fixture(autouse=True)
def _reset_threshold_to_default(monkeypatch):
    """Ensure the quality threshold is 0.85 for every test in this module."""
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
    import bob.spec_quality.threshold_resolver as _tr
    _tr._frozen_value = None
    _tr._frozen_initialized = False
    yield
    _tr._frozen_value = None
    _tr._frozen_initialized = False


def _make_report(score: float) -> QualityReport:
    return QualityReport(
        score=score,
        components=ScoreComponents(
            ambiguity_score=score,
            reachability_score=score,
            ears_score=score,
            ac_coverage_score=score,
        ),
    )


def test_gate_passes_at_exactly_0_85():
    report = _make_report(0.85)
    passed, message = gate_for_ready(report)
    assert passed is True
    assert message is None


def test_gate_blocks_just_below_0_85():
    report = _make_report(0.8499)
    passed, message = gate_for_ready(report)
    assert passed is False
    assert message is not None


def test_gate_passes_above_0_85():
    report = _make_report(0.90)
    passed, message = gate_for_ready(report)
    assert passed is True
    assert message is None


def test_gate_passes_at_1_0():
    report = _make_report(1.0)
    passed, message = gate_for_ready(report)
    assert passed is True
    assert message is None


def test_gate_blocks_at_0_0():
    report = _make_report(0.0)
    passed, message = gate_for_ready(report)
    assert passed is False
    assert message is not None


def test_score_threshold_returns_0_85():
    assert score_threshold() == THRESHOLD


def test_gate_blocked_message_contains_score(tmp_path):
    report = _make_report(0.60)
    passed, message = gate_for_ready(report)
    assert passed is False
    assert "0.60" in message or "0.6" in message


def test_gate_blocked_message_contains_threshold():
    report = _make_report(0.70)
    passed, message = gate_for_ready(report)
    assert "0.85" in message


def test_gate_blocked_message_contains_pending():
    report = _make_report(0.50)
    passed, message = gate_for_ready(report)
    assert "pending" in message


def test_gate_blocked_message_is_structured():
    report = _make_report(0.40)
    passed, message = gate_for_ready(report)
    assert "BLOCKED" in message
    assert "threshold" in message
    assert "ambiguity" in message
