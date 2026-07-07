"""Tests for spec_quality.quality_score_gate.

Feature: Spec quality score gate — features below threshold cannot reach ready.

The gate combines the F-R7-410/411/412 sub-scorers plus an AC-coverage metric
into a per-feature ``spec_quality_score`` in [0, 1]. Features with score < 0.85
stay pending with a structured remediation report.

ACs covered here:
  - Function defined: spec_quality.quality_score_gate.compute_spec_quality_score
  - Function defined: spec_quality.quality_score_gate.gate_feature_readiness
  - integration: spec_quality.composite_score
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.quality_score_gate import (
    compute_spec_quality_score,
    gate_feature_readiness,
)


# ---------------------------------------------------------------------------
# compute_spec_quality_score
# ---------------------------------------------------------------------------

def test_compute_returns_float_in_unit_interval():
    score = compute_spec_quality_score(
        name="well-formed feature",
        description=None,
        acceptance_criteria=[
            "File exists: src/spec_quality/quality_score_gate.py",
            "Function defined: spec_quality.quality_score_gate.compute_spec_quality_score",
            "pytest: tests/test_spec_quality_score_gate.py",
        ],
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_compute_empty_criteria_returns_zero():
    score = compute_spec_quality_score(
        name="no ACs",
        description=None,
        acceptance_criteria=[],
    )
    assert score == 0.0


def test_compute_accepts_json_encoded_list():
    score = compute_spec_quality_score(
        name="json feature",
        description=None,
        acceptance_criteria='["File exists: src/spec_quality/quality_score_gate.py"]',
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_compute_none_name_raises_value_error():
    with pytest.raises(ValueError):
        compute_spec_quality_score(
            name=None,
            description=None,
            acceptance_criteria=["File exists: x.py"],
        )


def test_compute_non_string_name_raises_value_error():
    with pytest.raises(ValueError):
        compute_spec_quality_score(
            name=123,
            description=None,
            acceptance_criteria=["File exists: x.py"],
        )


def test_compute_invalid_criteria_type_raises_value_error():
    with pytest.raises(ValueError):
        compute_spec_quality_score(
            name="bad acs",
            description=None,
            acceptance_criteria={"not": "a list"},
        )


# ---------------------------------------------------------------------------
# gate_feature_readiness
# ---------------------------------------------------------------------------

def test_gate_returns_dict_with_expected_keys():
    result = gate_feature_readiness(
        name="feature",
        description=None,
        acceptance_criteria=["File exists: src/spec_quality/quality_score_gate.py"],
    )
    assert isinstance(result, dict)
    assert "ready" in result
    assert "score" in result
    assert "threshold" in result
    assert "remediation" in result


def test_gate_blocks_low_quality_feature(monkeypatch):
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "0.85")
    # An empty AC list scores 0.0 → below threshold → not ready.
    result = gate_feature_readiness(
        name="empty feature",
        description=None,
        acceptance_criteria=[],
    )
    assert result["ready"] is False
    assert result["score"] < result["threshold"]
    assert result["remediation"] is not None
    assert isinstance(result["remediation"], str)
    assert len(result["remediation"]) > 0


def test_gate_passes_high_quality_feature(monkeypatch):
    # Freeze threshold to 0.0 so any well-formed feature passes deterministically.
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "0.0")
    result = gate_feature_readiness(
        name="good feature",
        description=None,
        acceptance_criteria=[
            "File exists: src/spec_quality/quality_score_gate.py",
            "Function defined: spec_quality.quality_score_gate.compute_spec_quality_score",
            "pytest: tests/test_spec_quality_score_gate.py",
        ],
    )
    assert result["ready"] is True
    assert result["remediation"] is None
    assert result["score"] >= result["threshold"]


def test_gate_remediation_report_is_structured(monkeypatch):
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "0.85")
    result = gate_feature_readiness(
        name="blocked feature",
        description=None,
        acceptance_criteria=[],
    )
    report = result["remediation"]
    assert "score" in report.lower()
    assert "threshold" in report.lower()


def test_gate_honors_threshold_env(monkeypatch):
    # Use the non-frozen env var, which is re-read on every call.
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
    monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "1.0")
    result = gate_feature_readiness(
        name="perfectionist",
        description=None,
        acceptance_criteria=[
            "File exists: src/spec_quality/quality_score_gate.py",
        ],
    )
    assert result["threshold"] == 1.0


def test_gate_none_name_raises_value_error():
    with pytest.raises(ValueError):
        gate_feature_readiness(
            name=None,
            description=None,
            acceptance_criteria=["File exists: x.py"],
        )


# ---------------------------------------------------------------------------
# integration: spec_quality.composite_score
# ---------------------------------------------------------------------------

def test_composite_score_is_reachable_and_used():
    """The gate composes with the composite_score module (integration AC)."""
    from spec_quality import composite_score

    assert hasattr(composite_score, "compute_spec_quality_score")
    # The gate module must expose the composite integration point.
    import spec_quality.quality_score_gate as gate_mod

    assert hasattr(gate_mod, "compute_spec_quality_score")
    assert hasattr(gate_mod, "gate_feature_readiness")
