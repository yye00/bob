"""Tests for spec_findings_registry deduplication behaviour.

Verifies that (spec_hash, slot_id, defect_type) acts as a composite primary key:
recording the same triple twice results in a single entry (updated), not two.
"""

from __future__ import annotations

import yaml

from bob3.spec_quality.spec_findings_registry import (
    detect_regression,
    record,
)


class TestDeduplication:
    def test_first_record_is_not_regression(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        entry = record(
            "aabbccdd", "AC-0", "ambiguity",
            feature_id="f1", name="Test", rationale="r", suggested_fix="s",
            findings_path=fp, metrics_path=tmp_path / "metrics.yaml",
        )
        assert entry["is_regression"] is False

    def test_second_record_same_key_is_regression(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        entry = record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        assert entry["is_regression"] is True

    def test_different_slot_not_deduped(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        entry0 = record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        entry1 = record("aabbccdd", "AC-1", "ambiguity", findings_path=fp, metrics_path=mp)
        assert entry0["is_regression"] is False
        assert entry1["is_regression"] is False

        data = yaml.safe_load(fp.read_text())
        assert len(data["findings"]) == 2

    def test_different_defect_type_not_deduped(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        entry = record("aabbccdd", "AC-0", "untestable", findings_path=fp, metrics_path=mp)
        assert entry["is_regression"] is False

    def test_different_spec_hash_not_deduped(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("hash1111", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        entry = record("hash2222", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        assert entry["is_regression"] is False

    def test_occurrence_count_increments_on_repeat(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        entry = record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        assert entry["occurrence_count"] == 3

    def test_yaml_file_created_on_first_record(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        assert not fp.exists()
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp,
               metrics_path=tmp_path / "metrics.yaml")
        assert fp.exists()

    def test_yaml_has_schema_version(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp,
               metrics_path=tmp_path / "metrics.yaml")
        data = yaml.safe_load(fp.read_text())
        assert "schema_version" in data

    def test_entry_keyed_by_composite_key(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", feature_id="f1",
               findings_path=fp, metrics_path=mp)
        data = yaml.safe_load(fp.read_text())
        keys = list(data["findings"].keys())
        assert len(keys) == 1
        assert "aabbccdd" in keys[0]
        assert "AC-0" in keys[0]
        assert "ambiguity" in keys[0]

    def test_detect_regression_false_for_unseen(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        result = detect_regression("aabbccdd", "AC-0", "ambiguity", findings_path=fp)
        assert result is False

    def test_detect_regression_false_after_first_record(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        # occurrence_count is 1 after first record, not a regression
        result = detect_regression("aabbccdd", "AC-0", "ambiguity", findings_path=fp)
        assert result is False

    def test_detect_regression_true_after_second_record(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        record("aabbccdd", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        result = detect_regression("aabbccdd", "AC-0", "ambiguity", findings_path=fp)
        assert result is True
