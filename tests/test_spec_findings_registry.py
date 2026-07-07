"""Tests for spec_critic.registry (F-R7-450).

Verifies:
- write_findings records findings to spec_findings.yaml
- Keyed by (spec_hash, slot_id, defect_type)
- detect_regression detects repeated findings
- Severity is escalated on regression
- Halt-gate fires when critic_repeat_rate > 0.30 over 3 runs
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from spec_critic.registry import (
    write_findings,
    detect_regression,
    compute_critic_repeat_rate,
    is_halt_gate_fired,
)


def test_write_findings_returns_dict(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    result = write_findings(
        spec_hash="abc123",
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

    assert result is not None
    assert isinstance(result, dict)
    assert result["spec_hash"] == "abc123"
    assert result["slot_id"] == "AC-0"
    assert result["defect_type"] == "ambiguity"
    assert result["severity"] == "warning"
    assert result["is_regression"] is False
    assert result["occurrence_count"] == 1


def test_write_findings_creates_yaml_file(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="hashfile01",
        slot_id="AC-1",
        defect_type="untestable",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert findings_path.exists()
    with open(findings_path) as fh:
        data = yaml.safe_load(fh)
    assert "findings" in data
    assert "hashfile01:AC-1:untestable" in data["findings"]


def test_detect_regression_returns_false_on_first_occurrence(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="reg001",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    is_reg = detect_regression(
        spec_hash="reg001",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=findings_path,
    )
    assert is_reg is False


def test_detect_regression_returns_true_on_second_occurrence(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="reg002",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )
    write_findings(
        spec_hash="reg002",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-2",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    is_reg = detect_regression(
        spec_hash="reg002",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=findings_path,
    )
    assert is_reg is True


def test_severity_escalated_on_regression(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    r1 = write_findings(
        spec_hash="esc001",
        slot_id="AC-0",
        defect_type="ambiguity",
        severity="warning",
        run_id="run-1",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )
    assert r1["severity"] == "warning"

    r2 = write_findings(
        spec_hash="esc001",
        slot_id="AC-0",
        defect_type="ambiguity",
        severity="warning",
        run_id="run-2",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )
    assert r2["is_regression"] is True
    assert r2["severity"] == "error"


def test_halt_gate_fires_when_repeat_rate_exceeds_threshold(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    # First add unique findings in run-1
    for i in range(5):
        write_findings(
            spec_hash="hg001",
            slot_id=f"AC-{i}",
            defect_type="untestable",
            run_id="run-1",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )

    # Repeat same defects in run-2 (all regressions)
    for i in range(5):
        write_findings(
            spec_hash="hg001",
            slot_id=f"AC-{i}",
            defect_type="untestable",
            run_id="run-2",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )

    # Repeat again in run-3
    for i in range(5):
        write_findings(
            spec_hash="hg001",
            slot_id=f"AC-{i}",
            defect_type="untestable",
            run_id="run-3",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )

    assert is_halt_gate_fired(findings_path=findings_path, metrics_path=metrics_path) is True


def test_halt_gate_not_fired_for_single_occurrence(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="nohalt01",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    assert is_halt_gate_fired(findings_path=findings_path, metrics_path=metrics_path) is False


def test_different_slot_ids_are_independent(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    base = dict(
        spec_hash="multi001",
        defect_type="ambiguity",
        severity="warning",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    r0 = write_findings(slot_id="AC-0", run_id="x1", **base)
    r1 = write_findings(slot_id="AC-1", run_id="x2", **base)

    assert r0["is_regression"] is False
    assert r1["is_regression"] is False


def test_different_spec_hashes_are_independent(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    base = dict(
        slot_id="AC-0",
        defect_type="ambiguity",
        severity="warning",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    rA = write_findings(spec_hash="hash_A", run_id="y1", **base)
    rB = write_findings(spec_hash="hash_B", run_id="y2", **base)

    assert rA["is_regression"] is False
    assert rB["is_regression"] is False


def test_occurrence_count_increments(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    for i in range(1, 4):
        r = write_findings(
            spec_hash="cnt001",
            slot_id="AC-0",
            defect_type="missing_edge_case",
            run_id=f"run-{i}",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        assert r["occurrence_count"] == i


def test_compute_critic_repeat_rate_zero_for_no_regressions(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="rate001",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    rate = compute_critic_repeat_rate(findings_path=findings_path)
    assert rate == 0.0


def test_record_findings_canonical_entrypoint_exists():
    """AC requires bob.spec_findings_registry.record_findings to be defined."""
    from bob import spec_findings_registry as reg

    assert hasattr(reg, "record_findings")
    assert callable(reg.record_findings)


def test_record_findings_records_and_detects_regression(tmp_path):
    """record_findings behaves like write_findings (keyed + regression)."""
    from bob.spec_findings_registry import record_findings, detect_regression as dr

    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    r1 = record_findings(
        spec_hash="rec001",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-1",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )
    assert r1["is_regression"] is False
    assert r1["occurrence_count"] == 1

    r2 = record_findings(
        spec_hash="rec001",
        slot_id="AC-0",
        defect_type="ambiguity",
        run_id="run-2",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )
    assert r2["is_regression"] is True
    assert r2["severity"] == "error"
    assert dr(
        spec_hash="rec001",
        slot_id="AC-0",
        defect_type="ambiguity",
        findings_path=findings_path,
    ) is True


def test_findings_composite_key_format(tmp_path):
    findings_path = tmp_path / "spec_findings.yaml"
    metrics_path = tmp_path / "metrics.yaml"

    write_findings(
        spec_hash="key001",
        slot_id="AC-5",
        defect_type="implementation_leak",
        findings_path=findings_path,
        metrics_path=metrics_path,
    )

    with open(findings_path) as fh:
        data = yaml.safe_load(fh)

    assert "key001:AC-5:implementation_leak" in data["findings"]
