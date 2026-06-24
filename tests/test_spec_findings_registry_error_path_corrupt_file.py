"""Tests for error-path handling when spec_findings.yaml is malformed/corrupt.

As of feature 483b56b6, corrupt YAML files are quarantined (not crash-raised)
so that boot can continue.  record() on a corrupt file quarantines the file and
writes fresh findings rather than propagating an exception.
"""

from __future__ import annotations

import pytest

from bob.spec_quality.spec_findings_registry import record


class TestCorruptFileErrorPath:
    def test_record_quarantines_corrupt_yaml_and_continues(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        # Write invalid YAML that will fail to parse
        fp.write_text(": : : invalid yaml {{{{[\n")
        # Must NOT raise — quarantine-and-continue behavior
        record("abc123", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        # File must now be valid YAML (fresh write after quarantine)
        import yaml
        data = yaml.safe_load(fp.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        # Original corrupt file must be quarantined
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_record_quarantines_corrupt_yaml_brace_format(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        fp.write_text("{bad yaml content [[[[\n")
        # Must NOT raise
        record("abc123", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        import yaml
        data = yaml.safe_load(fp.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_record_on_yaml_with_wrong_type_continues(self, tmp_path):
        fp = tmp_path / "spec_findings.yaml"
        mp = tmp_path / "metrics.yaml"
        # Valid YAML but wrong type (list instead of dict) — treated as empty, not crash
        fp.write_text("- item1\n- item2\n")
        # Must NOT raise — non-dict YAML is treated as empty findings
        record("abc123", "AC-0", "ambiguity", findings_path=fp, metrics_path=mp)
        import yaml
        data = yaml.safe_load(fp.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
