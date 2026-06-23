"""Tests for spec_quality_score_gate_features_below_threshold_cannot module."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob3.spec_quality_score_gate_features_below_threshold_cannot import (
    spec_quality_score_gate_features_below_threshold_cannot,
)


def test_spec_quality_score_gate_features_below_threshold_cannot():
    """Core AC test: function exists and returns correct types and gate semantics."""
    name = "Test feature"
    description = "A test feature with clear function compute_score and class QualityReport."
    acs = [
        "File exists: src/bob3/spec_quality/quality_score.py",
        "Function defined: bob3.spec_quality.quality_score.compute_score",
        "pytest: tests/test_spec_quality_score_gate_features_below_threshold_cannot.py",
    ]

    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot(
        name=name,
        description=description,
        acceptance_criteria=acs,
    )

    assert isinstance(score, float), f"Expected float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"Score {score} not in [0, 1]"
    assert isinstance(passed, bool), f"Expected bool, got {type(passed)}"

    if passed:
        assert remediation is None
    else:
        assert isinstance(remediation, str)
        assert len(remediation) > 0


def test_gate_blocks_empty_acs():
    """Features with empty AC list must be blocked (score < 0.85 threshold)."""
    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot(
        name="Empty ACs feature",
        description=None,
        acceptance_criteria=[],
    )

    assert score == 0.0
    assert passed is False
    assert remediation is not None
    assert "BLOCKED" in remediation
    assert "pending" in remediation


def test_score_in_unit_interval_various_inputs():
    """Score must always be in [0.0, 1.0] regardless of input."""
    test_cases = [
        [],
        ["File exists: src/bob3/spec_quality/quality_score.py"],
        [
            "File exists: src/bob3/spec_quality/quality_score.py",
            "Function defined: bob3.spec_quality.quality_score.compute_score",
        ],
    ]
    for acs in test_cases:
        score, _, _ = spec_quality_score_gate_features_below_threshold_cannot(
            name="Range check",
            description=None,
            acceptance_criteria=acs,
        )
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for ACs={acs}"


def test_remediation_contains_component_names():
    """Blocked features must include sub-score component names in the report."""
    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot(
        name="Blocked feature",
        description=None,
        acceptance_criteria=[],
    )

    assert not passed
    assert remediation is not None
    assert "ambiguity" in remediation
    assert "reachability" in remediation
    assert "ears" in remediation
    assert "ac_coverage" in remediation


def test_accepts_json_encoded_criteria():
    """Function must accept JSON-encoded AC list strings."""
    acs_json = json.dumps([
        "File exists: src/bob3/spec_quality/quality_score.py",
        "Function defined: bob3.spec_quality.quality_score.compute_score",
    ])

    score, _, _ = spec_quality_score_gate_features_below_threshold_cannot(
        name="JSON ACs",
        description=None,
        acceptance_criteria=acs_json,
    )

    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_threshold_env_override(monkeypatch):
    """BOB3_SPEC_QUALITY_THRESHOLD env var must adjust the gate threshold."""
    monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "0.01")
    monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)

    acs = [
        "File exists: src/bob3/spec_quality/quality_score.py",
        "pytest: tests/test_spec_quality_score_gate_features_below_threshold_cannot.py",
    ]
    score, passed, remediation = spec_quality_score_gate_features_below_threshold_cannot(
        name="Threshold override",
        description=None,
        acceptance_criteria=acs,
    )

    assert passed is True
    assert remediation is None
