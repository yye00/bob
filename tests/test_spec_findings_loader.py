"""Tests for bob3.spec_findings_loader.load_spec_findings_safe.

Feature f3447fc6-0853-4e80-8bc6-5449036d8d1a

Verifies that load_spec_findings_safe:
- Returns {} for missing or empty files
- Returns parsed dict for valid YAML
- Quarantines corrupt YAML and returns {} (no crash)
- Always returns dict, never raises on bad input
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob3.spec_findings_loader import load_spec_findings_safe


class TestLoadSpecFindingsSafe:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_spec_findings_safe(tmp_path / "missing.yaml")
        assert result == {}

    def test_empty_file_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == {}

    def test_null_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("null\n", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == {}

    def test_valid_yaml_returns_data(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        data = {"f1": {"severity": "high"}, "f2": {"severity": "low"}}
        p.write_text(yaml.safe_dump(data), encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == data

    def test_list_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == {}

    def test_corrupt_yaml_does_not_raise(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("me: perf-orphan-69\n  bad: indent\n  [unclosed", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert isinstance(result, dict)

    def test_corrupt_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": broken\n  mapping: values\n", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == {}

    def test_corrupt_yaml_quarantines_file(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": broken\n  mapping: values\n", encoding="utf-8")
        load_spec_findings_safe(p)
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_accepts_string_path(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("key: value\n", encoding="utf-8")
        result = load_spec_findings_safe(str(p))
        assert result == {"key": "value"}

    def test_always_returns_dict(self, tmp_path):
        for content in ["", "null\n", "k: v\n"]:
            p = tmp_path / "sf.yaml"
            p.write_text(content, encoding="utf-8")
            result = load_spec_findings_safe(p)
            assert isinstance(result, dict), f"Expected dict for {content!r}"
