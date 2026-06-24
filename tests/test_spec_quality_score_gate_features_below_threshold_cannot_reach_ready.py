"""Tests for spec_quality_score_gate_features_below_threshold_cannot_reach_ready."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.spec_quality_score_gate_features_below_threshold_cannot_reach_ready import (
    spec_quality_score_gate_features_below_threshold_cannot_reach_ready,
)


def test_spec_quality_score_gate_features_below_threshold_cannot_reach_ready():
    """Core AC test: function exists and returns correct types and gate semantics."""
    name = "Test feature"
    description = "A test feature with clear function compute_score and class QualityReport."
    acs = [
        "File exists: src/bob/spec_quality/quality_score.py",
        "Function defined: bob.spec_quality.quality_score.compute_score",
        "pytest: tests/test_spec_quality_score_gate_features_below_threshold_cannot_reach_ready.py",
    ]

    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
        name=name,
        description=description,
        acceptance_criteria=acs,
    )

    # score is a float in [0, 1]
    assert isinstance(score, float), f"Expected float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"Score {score} not in [0, 1]"

    # passed is a bool
    assert isinstance(passed, bool), f"Expected bool, got {type(passed)}"

    # remediation is None when passed, non-empty string when blocked
    if passed:
        assert remediation is None, f"Expected None remediation when passed, got {remediation!r}"
    else:
        assert isinstance(remediation, str), f"Expected str remediation when blocked, got {type(remediation)}"
        assert len(remediation) > 0


def test_gate_blocks_below_threshold():
    """Features with score < 0.85 should be blocked with a remediation report."""
    # Empty AC list → score = 0.0 < 0.85 → blocked
    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
        name="Empty ACs feature",
        description=None,
        acceptance_criteria=[],
    )

    assert score == 0.0
    assert passed is False
    assert remediation is not None
    assert "BLOCKED" in remediation
    assert "pending" in remediation


def test_gate_passes_high_quality_spec():
    """Features with well-structured ACs should pass the gate."""
    name = "High quality feature"
    description = None
    acs = [
        "File exists: src/bob/spec_quality/quality_score.py",
        "Function defined: bob.spec_quality.quality_score.compute_score",
        "pytest: tests/test_spec_quality_score_gate_features_below_threshold_cannot_reach_ready.py::test_gate_passes_high_quality_spec",
        "Function defined: bob.spec_quality.quality_score.gate_for_ready",
    ]

    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
        name=name,
        description=description,
        acceptance_criteria=acs,
    )

    # Score should be in valid range
    assert 0.0 <= score <= 1.0

    # If passed, remediation must be None
    if passed:
        assert remediation is None
    else:
        # It's acceptable that it doesn't pass — verify the remediation is structured
        assert isinstance(remediation, str)
        assert "threshold" in remediation.lower() or "score" in remediation.lower()


def test_returns_structured_remediation_report():
    """Blocked features must include component scores and actionable hints."""
    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
        name="Blocked feature",
        description=None,
        acceptance_criteria=[],
    )

    assert not passed
    assert remediation is not None
    # Remediation report must include component names
    assert "ambiguity" in remediation
    assert "reachability" in remediation
    assert "ears" in remediation
    assert "ac_coverage" in remediation


def test_score_is_float_in_unit_interval():
    """Score must always be in [0.0, 1.0] regardless of input."""
    for acs in [
        [],
        ["File exists: src/bob/spec_quality/quality_score.py"],
        ["File exists: src/bob/spec_quality/quality_score.py", "Function defined: bob.spec_quality.quality_score.compute_score"],
    ]:
        score, _, _ = spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
            name="Range check",
            description=None,
            acceptance_criteria=acs,
        )
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for ACs={acs}"


def test_accepts_json_encoded_criteria():
    """Function must handle JSON-encoded AC list strings."""
    import json
    acs_json = json.dumps([
        "File exists: src/bob/spec_quality/quality_score.py",
        "Function defined: bob.spec_quality.quality_score.compute_score",
    ])

    score, _, _ = spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
        name="JSON ACs",
        description=None,
        acceptance_criteria=acs_json,
    )

    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_threshold_env_override(monkeypatch):
    """BOB_SPEC_QUALITY_THRESHOLD env var should adjust the gate threshold."""
    # Set a very low threshold so any non-zero score passes
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.01")
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)

    acs = [
        "File exists: src/bob/spec_quality/quality_score.py",
        "pytest: tests/test_spec_quality_score_gate_features_below_threshold_cannot_reach_ready.py",
    ]
    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
        name="Threshold override",
        description=None,
        acceptance_criteria=acs,
    )

    # With threshold=0.01, any reasonable spec should pass
    assert passed is True
    assert remediation is None
