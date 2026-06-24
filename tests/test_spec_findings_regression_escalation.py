"""Tests for spec_findings_registry regression severity escalation.

On re-run with the same (spec_hash, slot_id, defect_type), the registry
escalates severity by one level: info→warning→error→critical (capped).
"""

from __future__ import annotations

import yaml

from bob.spec_quality.spec_findings_registry import (
    SEVERITY_ORDER,
    record,
    _escalate_severity,
)


class TestSeverityEscalation:
    def test_escalate_info_to_warning(self):
        assert _escalate_severity("info") == "warning"

    def test_escalate_warning_to_error(self):
        assert _escalate_severity("warning") == "error"

    def test_escalate_error_to_critical(self):
        assert _escalate_severity("error") == "critical"

    def test_escalate_critical_stays_critical(self):
        assert _escalate_severity("critical") == "critical"

    def test_severity_order_has_four_levels(self):
        assert len(SEVERITY_ORDER) == 4

    def test_first_record_keeps_initial_severity(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        entry = record(
            "aabbccdd", "AC-0", "ambiguity",
            severity="info",
            findings_path=fp, metrics_path=mp,
        )
        assert entry["severity"] == "info"

    def test_second_record_escalates_severity(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", severity="info",
               findings_path=fp, metrics_path=mp)
        entry = record("aabbccdd", "AC-0", "ambiguity", severity="info",
                       findings_path=fp, metrics_path=mp)
        assert entry["severity"] == "warning"

    def test_third_record_escalates_again(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", severity="info",
               findings_path=fp, metrics_path=mp)
        record("aabbccdd", "AC-0", "ambiguity", severity="info",
               findings_path=fp, metrics_path=mp)
        entry = record("aabbccdd", "AC-0", "ambiguity", severity="info",
                       findings_path=fp, metrics_path=mp)
        assert entry["severity"] == "error"

    def test_fourth_record_reaches_critical(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        for _ in range(3):
            record("aabbccdd", "AC-0", "ambiguity", severity="info",
                   findings_path=fp, metrics_path=mp)
        entry = record("aabbccdd", "AC-0", "ambiguity", severity="info",
                       findings_path=fp, metrics_path=mp)
        assert entry["severity"] == "critical"

    def test_severity_capped_at_critical(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        for _ in range(10):
            entry = record("aabbccdd", "AC-0", "ambiguity", severity="info",
                           findings_path=fp, metrics_path=mp)
        assert entry["severity"] == "critical"

    def test_escalation_per_key_independent(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        # Escalate one key three times
        for _ in range(3):
            record("aabbccdd", "AC-0", "ambiguity", severity="info",
                   findings_path=fp, metrics_path=mp)
        # Different slot should still start at original severity
        entry = record("aabbccdd", "AC-1", "ambiguity", severity="info",
                       findings_path=fp, metrics_path=mp)
        assert entry["severity"] == "info"
        assert entry["is_regression"] is False

    def test_regression_flag_matches_escalation(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        e1 = record("aabbccdd", "AC-0", "ambiguity", severity="warning",
                    findings_path=fp, metrics_path=mp)
        e2 = record("aabbccdd", "AC-0", "ambiguity", severity="warning",
                    findings_path=fp, metrics_path=mp)
        assert e1["is_regression"] is False
        assert e2["is_regression"] is True
        assert e2["severity"] == "error"

    def test_escalated_severity_stored_in_yaml(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", severity="info",
               findings_path=fp, metrics_path=mp)
        record("aabbccdd", "AC-0", "ambiguity", severity="info",
               findings_path=fp, metrics_path=mp)
        data = yaml.safe_load(fp.read_text())
        key = "aabbccdd:AC-0:ambiguity"
        assert data["findings"][key]["severity"] == "warning"
