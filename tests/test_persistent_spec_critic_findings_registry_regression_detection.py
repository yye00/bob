"""Tests for persistent_spec_critic_findings_registry_regression_detection.

Verifies that the public function:
  - Records findings keyed by (spec_hash, slot_id, defect_type)
  - Detects regressions and escalates severity on re-run
  - Fires halt-gate when critic_repeat_rate > 0.30 over 3 runs
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob3.persistent_spec_critic_findings_registry_regression_detection import (
    persistent_spec_critic_findings_registry_regression_detection,
)


def test_persistent_spec_critic_findings_registry_regression_detection(tmp_path):
    """Primary AC test: function exists, records findings, detects regressions, and fires halt-gate."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    # --- First run: record a defect, no regression yet ---
    result1 = persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="abc123def456abcd",
        slot_id="AC-0",
        defect_type="ambiguity",
        feature_id="feat-001",
        name="My Feature",
        rationale="AC is vague",
        suggested_fix="Add concrete criterion",
        severity="warning",
        run_id="run-001",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert result1 is not None
    assert isinstance(result1, dict)
    assert result1["is_regression"] is False
    assert result1["spec_hash"] == "abc123def456abcd"
    assert result1["slot_id"] == "AC-0"
    assert result1["defect_type"] == "ambiguity"
    assert result1["severity"] == "warning"
    assert result1["occurrence_count"] == 1

    # --- Second run: same defect at same slot → regression ---
    result2 = persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="abc123def456abcd",
        slot_id="AC-0",
        defect_type="ambiguity",
        feature_id="feat-001",
        name="My Feature",
        rationale="AC is still vague",
        suggested_fix="Add concrete criterion",
        severity="warning",
        run_id="run-002",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert result2["is_regression"] is True
    assert result2["occurrence_count"] == 2
    # severity escalated from warning → error
    assert result2["severity"] == "error"

    # --- Verify findings file has been written ---
    assert findings_path.exists()
    with open(findings_path) as fh:
        data = yaml.safe_load(fh)
    assert "findings" in data
    key = "abc123def456abcd:AC-0:ambiguity"
    assert key in data["findings"]

    # --- Check halt-gate: fire it with repeat rate > 0.30 ---
    # Add more regression events in same run_id window to push rate > 0.30
    for i in range(5):
        persistent_spec_critic_findings_registry_regression_detection(
            spec_hash="abc123def456abcd",
            slot_id=f"AC-{i}",
            defect_type="untestable",
            feature_id="feat-001",
            name="My Feature",
            rationale="untestable AC",
            suggested_fix="make testable",
            severity="warning",
            run_id="run-003",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
    # Now record the same defects again (regression) in run-004
    for i in range(5):
        persistent_spec_critic_findings_registry_regression_detection(
            spec_hash="abc123def456abcd",
            slot_id=f"AC-{i}",
            defect_type="untestable",
            feature_id="feat-001",
            name="My Feature",
            rationale="untestable AC",
            suggested_fix="make testable",
            severity="warning",
            run_id="run-004",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )

    # Metrics file should exist and halt_gate_fired should be True
    assert metrics_path.exists()
    with open(metrics_path) as fh:
        metrics = yaml.safe_load(fh)
    assert "critic_repeat_rate" in metrics
    assert "halt_gate_fired" in metrics
    # rate > 0.30 after repeated regressions
    assert metrics["critic_repeat_rate"] > 0.30
    assert metrics["halt_gate_fired"] is True


def test_function_exists():
    """Verify the module and function can be imported."""
    from bob3.persistent_spec_critic_findings_registry_regression_detection import (
        persistent_spec_critic_findings_registry_regression_detection as fn,
    )
    assert callable(fn)


def test_first_occurrence_not_regression(tmp_path):
    """A brand-new finding is never a regression."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    result = persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="hash0001",
        slot_id="FEATURE",
        defect_type="missing_edge_case",
        feature_id="feat-002",
        name="F2",
        rationale="no edge cases",
        suggested_fix="add edge case ACs",
        severity="info",
        run_id="run-A",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert result["is_regression"] is False
    assert result["severity"] == "info"
    assert result["occurrence_count"] == 1


def test_second_occurrence_escalates_severity(tmp_path):
    """info → warning on regression; warning → error; error → critical."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    kwargs = dict(
        spec_hash="escalate001",
        slot_id="AC-1",
        defect_type="vague_quantifier",
        feature_id="feat-003",
        name="F3",
        rationale="vague",
        suggested_fix="add bound",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    # info → warning
    r1 = persistent_spec_critic_findings_registry_regression_detection(
        **kwargs, severity="info", run_id="r1"
    )
    assert r1["severity"] == "info"

    r2 = persistent_spec_critic_findings_registry_regression_detection(
        **kwargs, severity="info", run_id="r2"
    )
    assert r2["severity"] == "warning"
    assert r2["is_regression"] is True

    r3 = persistent_spec_critic_findings_registry_regression_detection(
        **kwargs, severity="info", run_id="r3"
    )
    assert r3["severity"] == "error"

    r4 = persistent_spec_critic_findings_registry_regression_detection(
        **kwargs, severity="info", run_id="r4"
    )
    assert r4["severity"] == "critical"

    # stays at critical
    r5 = persistent_spec_critic_findings_registry_regression_detection(
        **kwargs, severity="info", run_id="r5"
    )
    assert r5["severity"] == "critical"


def test_different_slot_not_regression(tmp_path):
    """Same spec_hash + defect_type but different slot_id → independent entries."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    base = dict(
        spec_hash="multi001",
        defect_type="ambiguity",
        feature_id="feat-004",
        name="F4",
        rationale="vague",
        suggested_fix="fix",
        severity="warning",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    r1 = persistent_spec_critic_findings_registry_regression_detection(
        slot_id="AC-0", run_id="x1", **base
    )
    r2 = persistent_spec_critic_findings_registry_regression_detection(
        slot_id="AC-1", run_id="x2", **base
    )

    assert r1["is_regression"] is False
    assert r2["is_regression"] is False


def test_different_spec_hash_not_regression(tmp_path):
    """Same slot + defect_type but different spec_hash → independent entries."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    base = dict(
        slot_id="AC-0",
        defect_type="untestable",
        feature_id="feat-005",
        name="F5",
        rationale="r",
        suggested_fix="s",
        severity="warning",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    r1 = persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="hash_A", run_id="y1", **base
    )
    r2 = persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="hash_B", run_id="y2", **base
    )

    assert r1["is_regression"] is False
    assert r2["is_regression"] is False


def test_halt_gate_not_fired_below_threshold(tmp_path):
    """Halt gate does not fire when repeat rate is below 0.30."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    # Single unique finding — no regressions
    persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="nohalt01",
        slot_id="AC-0",
        defect_type="ambiguity",
        feature_id="feat-006",
        name="F6",
        rationale="r",
        suggested_fix="s",
        severity="warning",
        run_id="only-run",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    with open(metrics_path) as fh:
        metrics = yaml.safe_load(fh)

    assert metrics["halt_gate_fired"] is False


def test_findings_file_keyed_by_composite_key(tmp_path):
    """Findings stored with composite key spec_hash:slot_id:defect_type."""
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="keychk01",
        slot_id="AC-3",
        defect_type="implementation_leak",
        feature_id="feat-007",
        name="F7",
        rationale="leak",
        suggested_fix="remove impl detail",
        severity="error",
        run_id="r-key",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    with open(findings_path) as fh:
        data = yaml.safe_load(fh)

    expected_key = "keychk01:AC-3:implementation_leak"
    assert expected_key in data["findings"]
    entry = data["findings"][expected_key]
    assert entry["spec_hash"] == "keychk01"
    assert entry["slot_id"] == "AC-3"
    assert entry["defect_type"] == "implementation_leak"
