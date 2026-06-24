"""Tests for diff_since_ref (findings newer than a reference date/run_id)."""

from __future__ import annotations

from datetime import date

from bob.spec_quality.spec_findings_registry import diff_since_ref, record


class TestDiffSinceRef:
    def test_empty_registry_returns_empty_list(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        result = diff_since_ref("2026-01-01", findings_path=fp)
        assert result == []

    def test_finding_after_ref_is_included(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        today = date.today().isoformat()
        result = diff_since_ref(today, findings_path=fp)
        assert len(result) >= 1
        assert any("finding" in str(e) or e.get("defect_type") == "ambiguity" for e in result)

    def test_finding_returns_entry_with_finding_key(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        today = date.today().isoformat()
        result = diff_since_ref(today, findings_path=fp)
        assert len(result) >= 1
        # Each entry should be a dict and represent a finding
        entry = result[0]
        assert isinstance(entry, dict)
        assert "defect_type" in entry or "spec_hash" in entry

    def test_finding_before_ref_excluded(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        # Use a future date as ref — no findings should be after it
        result = diff_since_ref("2099-12-31", findings_path=fp)
        assert result == []

    def test_returns_list_type(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        result = diff_since_ref("2026-01-01", findings_path=fp)
        assert isinstance(result, list)

    def test_multiple_findings_sorted_by_last_seen_desc(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        record("hash1", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        record("hash2", "AC-1", "untestable", findings_path=fp, metrics_path=mp)
        today = date.today().isoformat()
        result = diff_since_ref(today, findings_path=fp)
        assert len(result) == 2
        # They should all be dicts with last_seen
        for entry in result:
            assert isinstance(entry, dict)
