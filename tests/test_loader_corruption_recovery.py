"""Tests for bob.loader.handle_scanner_error and load_safe.

Feature d43a5b31-ab9d-4c4a-9149-3e4758979a15

Verifies that the loader handles yaml.scanner.ScannerError by quarantining
the corrupt file and returning an empty dict so boot can continue.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob.loader import handle_scanner_error, load_safe


class TestHandleScannerError:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = handle_scanner_error(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_existing_file_is_quarantined(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt content", encoding="utf-8")
        handle_scanner_error(p)
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_returns_empty_dict_after_quarantine(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("bad: yaml", encoding="utf-8")
        result = handle_scanner_error(p)
        assert result == {}

    def test_quarantine_path_is_timestamped(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data", encoding="utf-8")
        handle_scanner_error(p)
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1
        suffix = quarantine_files[0].name.split(".corrupt.")[-1]
        assert suffix.isdigit(), f"Expected unix timestamp, got: {suffix!r}"

    def test_accepts_string_path(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data", encoding="utf-8")
        result = handle_scanner_error(str(p))
        assert result == {}

    def test_rename_failure_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data", encoding="utf-8")
        import bob.loader as ldr
        with patch.object(ldr.os, "rename", side_effect=OSError("rename failed")):
            result = handle_scanner_error(p)
        assert result == {}

    def test_returns_dict_type(self, tmp_path):
        result = handle_scanner_error(tmp_path / "nonexistent.yaml")
        assert isinstance(result, dict)

    def test_logs_spec_findings_corrupt_event(self, tmp_path, caplog):
        import logging
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data", encoding="utf-8")
        with caplog.at_level(logging.ERROR, logger="bob.loader"):
            handle_scanner_error(p)
        assert any("spec_findings_corrupt" in msg for msg in caplog.messages)


class TestLoadSafe:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_safe(tmp_path / "missing.yaml")
        assert result == {}

    def test_valid_yaml_loaded(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("findings:\n  - id: F-001\n", encoding="utf-8")
        result = load_safe(p)
        assert result == {"findings": [{"id": "F-001"}]}

    def test_corrupt_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("me: perf-orphan-69\n  bad: indent\n  [unclosed", encoding="utf-8")
        result = load_safe(p)
        assert result == {}

    def test_corrupt_yaml_quarantines_file(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": broken\n  mapping: values\n", encoding="utf-8")
        load_safe(p)
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_empty_file_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        result = load_safe(p)
        assert result == {}

    def test_null_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("null\n", encoding="utf-8")
        result = load_safe(p)
        assert result == {}

    def test_list_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        result = load_safe(p)
        assert result == {}

    def test_always_returns_dict(self, tmp_path):
        for content in ["", "null\n", "k: v\n"]:
            p = tmp_path / "spec_findings.yaml"
            p.write_text(content, encoding="utf-8")
            result = load_safe(p)
            assert isinstance(result, dict)

    def test_scanner_error_replicates_original_boot_bug(self, tmp_path):
        """Simulate the exact boot corruption from bob version 13 r10."""
        corrupt_yaml = "me: perf-orphan-69\n  severity: error\n    [unclosed bracket"
        p = tmp_path / "spec_findings.yaml"
        p.write_text(corrupt_yaml, encoding="utf-8")
        result = load_safe(p)
        assert result == {}
        assert not p.exists()

    def test_does_not_raise_on_scanner_error(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("key:\n  bad indent:\n   deeper:\n: broken_key\n", encoding="utf-8")
        try:
            load_safe(p)
        except yaml.YAMLError:
            pytest.fail("load_safe must not propagate yaml.YAMLError")
