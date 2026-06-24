"""Tests for bob.spec_findings_writer — atomic write and corruption recovery.

Feature c24eba26-1ea6-47f8-9a07-384f277e7bd4

Verifies:
- write_atomic() writes valid YAML via atomic tmp+rename
- load_with_corruption_recovery() handles missing, empty, and corrupt files
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob.spec_findings_writer import load_with_corruption_recovery, write_atomic


class TestWriteAtomic:
    def test_creates_target_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        write_atomic({"key": "value"}, target)
        assert target.exists()

    def test_no_tmp_file_after_success(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        write_atomic({"key": "value"}, target)
        assert not Path(str(target) + ".tmp").exists()

    def test_produces_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": "F001", "severity": "high"}]}
        write_atomic(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_roundtrip_empty_dict(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        write_atomic({}, target)
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        loaded = yaml.safe_load(content)
        assert loaded is None or loaded == {}

    def test_roundtrip_nested_dict(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"a": {"b": {"c": "deep"}}}
        write_atomic(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "nested" / "deep" / "spec_findings.yaml"
        write_atomic({"k": "v"}, target)
        assert target.exists()

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        write_atomic({"version": 1}, target)
        write_atomic({"version": 2}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"version": 2}

    def test_accepts_string_path(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        write_atomic({"str": True}, str(target))
        assert target.exists()

    def test_rename_failure_preserves_original(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        write_atomic({"original": True}, target)

        import bob.spec_findings_writer as sfw
        with patch.object(sfw.os, "rename", side_effect=OSError("rename failed")):
            with pytest.raises(OSError):
                write_atomic({"new": True}, target)

        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"original": True}

    def test_rename_failure_raises_not_silently_succeeds(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        import bob.spec_findings_writer as sfw
        with patch.object(sfw.os, "rename", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                write_atomic({"k": "v"}, target)


class TestLoadWithCorruptionRecovery:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_with_corruption_recovery(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_valid_yaml_returns_data(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("findings:\n  - id: F001\n", encoding="utf-8")
        result = load_with_corruption_recovery(p)
        assert result == {"findings": [{"id": "F001"}]}

    def test_empty_file_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        result = load_with_corruption_recovery(p)
        assert result == {}

    def test_null_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("null\n", encoding="utf-8")
        result = load_with_corruption_recovery(p)
        assert result == {}

    def test_list_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        result = load_with_corruption_recovery(p)
        assert result == {}

    def test_corrupt_yaml_does_not_raise(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("me: perf-orphan-69\n  bad: indent\n  [unclosed", encoding="utf-8")
        result = load_with_corruption_recovery(p)
        assert result == {}

    def test_corrupt_yaml_quarantines_file(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": broken mapping\n  key: value\n", encoding="utf-8")
        load_with_corruption_recovery(p)
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_corrupt_yaml_logs_structured_event(self, tmp_path, caplog):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": broken\n", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="bob.spec_findings_writer"):
            load_with_corruption_recovery(p)
        assert any("spec_findings_corrupt" in r.message for r in caplog.records)

    def test_returns_dict_type_always(self, tmp_path):
        for content in ["", "null\n", "k: v\n"]:
            p = tmp_path / "findings.yaml"
            p.write_text(content, encoding="utf-8")
            result = load_with_corruption_recovery(p)
            assert isinstance(result, dict), f"Expected dict for {content!r}"

    def test_accepts_string_path(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("k: v\n", encoding="utf-8")
        result = load_with_corruption_recovery(str(p))
        assert result == {"k": "v"}

    def test_roundtrip_with_write_atomic(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"finding_count": 42, "features": ["F001", "F002"]}
        write_atomic(data, target)
        result = load_with_corruption_recovery(target)
        assert result == data
