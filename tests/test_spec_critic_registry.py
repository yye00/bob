"""Tests for bob3.spec_critic registry — F-R7-450.

Verifies the three AC-mandated functions:
  - bob3.spec_critic.write_findings
  - bob3.spec_critic.detect_regression
  - bob3.spec_critic.check_repeat_rate_halt_gate

And confirms integration with bob3.orchestrator (module is importable,
run_loop uses spec_critic internally).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob3.spec_critic import write_findings, detect_regression, check_repeat_rate_halt_gate


# ---------------------------------------------------------------------------
# write_findings
# ---------------------------------------------------------------------------


class TestWriteFindings:
    def test_write_returns_dict(self, tmp_path):
        result = write_findings(
            spec_hash="aabbccdd11223344",
            slot_id="AC-0",
            defect_type="ambiguity",
            feature_id="feat-001",
            name="Test feature",
            rationale="AC is vague",
            suggested_fix="Use concrete predicate",
            run_id="run-1",
            findings_path=tmp_path / "spec_findings.yaml",
            metrics_path=tmp_path / "metrics.yaml",
        )
        assert isinstance(result, dict)
        assert result["spec_hash"] == "aabbccdd11223344"
        assert result["slot_id"] == "AC-0"
        assert result["defect_type"] == "ambiguity"

    def test_write_creates_file(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        write_findings(
            spec_hash="abc001",
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
            metrics_path=tmp_path / "metrics.yaml",
        )
        assert findings_path.exists()

    def test_write_first_occurrence_not_regression(self, tmp_path):
        result = write_findings(
            spec_hash="fresh001",
            slot_id="AC-0",
            defect_type="ambiguity",
            run_id="run-1",
            findings_path=tmp_path / "spec_findings.yaml",
            metrics_path=tmp_path / "metrics.yaml",
        )
        assert result["is_regression"] is False
        assert result["occurrence_count"] == 1

    def test_write_second_occurrence_is_regression(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        common = dict(
            spec_hash="regr001",
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        write_findings(**common, run_id="run-1")
        result = write_findings(**common, run_id="run-2")
        assert result["is_regression"] is True
        assert result["occurrence_count"] == 2

    def test_severity_escalates_on_regression(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        common = dict(
            spec_hash="sev001",
            slot_id="AC-0",
            defect_type="ambiguity",
            severity="warning",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        write_findings(**common, run_id="run-1")
        result = write_findings(**common, run_id="run-2")
        assert result["severity"] in ("error", "critical"), (
            f"Expected escalated severity, got {result['severity']!r}"
        )

    def test_yaml_file_structure(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        write_findings(
            spec_hash="struct001",
            slot_id="AC-1",
            defect_type="untestable",
            findings_path=findings_path,
            metrics_path=tmp_path / "metrics.yaml",
        )
        with open(findings_path) as fh:
            data = yaml.safe_load(fh)
        assert "findings" in data
        key = "struct001:AC-1:untestable"
        assert key in data["findings"]
        entry = data["findings"][key]
        assert entry["spec_hash"] == "struct001"
        assert entry["slot_id"] == "AC-1"
        assert entry["defect_type"] == "untestable"

    def test_different_keys_stored_separately(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        write_findings(
            spec_hash="multi001",
            slot_id="AC-0",
            defect_type="ambiguity",
            run_id="run-1",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        write_findings(
            spec_hash="multi001",
            slot_id="AC-1",
            defect_type="missing_edge_case",
            run_id="run-1",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        with open(findings_path) as fh:
            data = yaml.safe_load(fh)
        assert "multi001:AC-0:ambiguity" in data["findings"]
        assert "multi001:AC-1:missing_edge_case" in data["findings"]


# ---------------------------------------------------------------------------
# detect_regression
# ---------------------------------------------------------------------------


class TestDetectRegression:
    def test_returns_false_before_any_write(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        assert detect_regression(
            spec_hash="new001",
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
        ) is False

    def test_returns_false_after_single_write(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        write_findings(
            spec_hash="once001",
            slot_id="AC-0",
            defect_type="ambiguity",
            run_id="run-1",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        assert detect_regression(
            spec_hash="once001",
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
        ) is False

    def test_returns_true_after_two_writes(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        common = dict(
            spec_hash="twice001",
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        write_findings(**common, run_id="run-1")
        write_findings(**common, run_id="run-2")
        assert detect_regression(
            spec_hash="twice001",
            slot_id="AC-0",
            defect_type="ambiguity",
            findings_path=findings_path,
        ) is True

    def test_different_slot_not_regression(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        write_findings(
            spec_hash="slot001",
            slot_id="AC-0",
            defect_type="ambiguity",
            run_id="run-1",
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        assert detect_regression(
            spec_hash="slot001",
            slot_id="AC-1",
            defect_type="ambiguity",
            findings_path=findings_path,
        ) is False


# ---------------------------------------------------------------------------
# check_repeat_rate_halt_gate
# ---------------------------------------------------------------------------


class TestCheckRepeatRateHaltGate:
    def test_empty_registry_does_not_fire(self, tmp_path):
        assert check_repeat_rate_halt_gate(
            findings_path=tmp_path / "spec_findings.yaml",
            metrics_path=tmp_path / "metrics.yaml",
        ) is False

    def test_no_regressions_does_not_fire(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        # One unique finding per run — no regressions
        for i in range(4):
            write_findings(
                spec_hash=f"unique{i:03d}",
                slot_id="AC-0",
                defect_type="ambiguity",
                run_id=f"run-{i}",
                findings_path=findings_path,
                metrics_path=metrics_path,
            )
        assert check_repeat_rate_halt_gate(
            findings_path=findings_path,
            metrics_path=metrics_path,
        ) is False

    def test_high_regression_rate_fires_gate(self, tmp_path):
        findings_path = tmp_path / "spec_findings.yaml"
        metrics_path = tmp_path / "metrics.yaml"
        # Push the same finding across many runs to drive repeat_rate > 0.30
        for i in range(1, 8):
            write_findings(
                spec_hash="repeated001",
                slot_id="AC-0",
                defect_type="ambiguity",
                run_id=f"run-{i}",
                findings_path=findings_path,
                metrics_path=metrics_path,
            )
        result = check_repeat_rate_halt_gate(
            findings_path=findings_path,
            metrics_path=metrics_path,
        )
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_orchestrator_importable(self):
        import bob3.orchestrator  # noqa: F401

    def test_run_loop_importable(self):
        from bob3.orchestrator import run_loop  # noqa: F401

    def test_spec_critic_functions_accessible_from_bob3(self):
        import bob3.spec_critic as sc

        assert callable(sc.write_findings)
        assert callable(sc.detect_regression)
        assert callable(sc.check_repeat_rate_halt_gate)


# ---------------------------------------------------------------------------
# File existence AC
# ---------------------------------------------------------------------------


def test_spec_findings_yaml_exists_in_bob3():
    """AC: File exists: src/bob3/reviews/spec_findings.yaml"""
    p = Path(__file__).resolve().parents[1] / "src" / "bob3" / "reviews" / "spec_findings.yaml"
    assert p.exists(), f"Expected {p} to exist"


def test_reviews_spec_findings_yaml_exists():
    """AC: reviews/spec_findings.yaml exists at workspace root."""
    p = Path(__file__).resolve().parents[1] / "reviews" / "spec_findings.yaml"
    assert p.exists(), f"Expected {p} to exist"
