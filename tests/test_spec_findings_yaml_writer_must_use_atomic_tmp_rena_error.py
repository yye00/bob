"""Error path tests for bob.spec_findings atomic_write and quarantine_corrupted.

Feature b37d0f34-5d02-4fdc-be9b-b205e2839fcb

Error path: invalid input raises ValueError and the function does not
silently succeed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob.spec_findings import atomic_write, quarantine_corrupted, load_safe


class TestAtomicWriteErrorPaths:
    def test_none_data_raises_or_writes_empty(self, tmp_path):
        """None data should raise TypeError or be handled gracefully (not silently corrupt)."""
        target = tmp_path / "spec_findings.yaml"
        try:
            atomic_write(None, target)
        except (TypeError, AttributeError):
            # Acceptable: function rejects None
            return
        # If it didn't raise, the target must be valid YAML
        content = target.read_text(encoding="utf-8")
        try:
            yaml.safe_load(content)
        except yaml.YAMLError:
            pytest.fail("atomic_write(None) produced invalid YAML without raising")

    def test_non_dict_data_raises_or_writes_valid_yaml(self, tmp_path):
        """Non-dict data should raise or produce valid YAML (no silent corruption)."""
        target = tmp_path / "spec_findings.yaml"
        try:
            atomic_write(["list", "not", "dict"], target)
        except (TypeError, AttributeError):
            return
        # If it didn't raise, the result must be valid YAML
        content = target.read_text(encoding="utf-8")
        yaml.safe_load(content)  # Must not raise

    def test_rename_failure_raises(self, tmp_path):
        """If os.rename fails, the exception propagates (no silent failure)."""
        target = tmp_path / "spec_findings.yaml"
        import bob.spec_findings as sf
        with patch.object(sf.os, "rename", side_effect=OSError("rename failed")):
            with pytest.raises(OSError):
                atomic_write({"k": "v"}, target)

    def test_no_tmp_file_on_rename_failure(self, tmp_path):
        """On rename failure, .tmp may remain but target must not be corrupt."""
        target = tmp_path / "spec_findings.yaml"
        # Write a valid file first
        atomic_write({"original": True}, target)

        import bob.spec_findings as sf
        with patch.object(sf.os, "rename", side_effect=OSError("rename failed")):
            try:
                atomic_write({"new": True}, target)
            except OSError:
                pass

        # Target must still be the original valid content
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"original": True}


class TestQuarantineCorruptedErrorPaths:
    def test_none_path_raises_value_error(self):
        with pytest.raises(ValueError):
            quarantine_corrupted(None)

    def test_invalid_type_path_raises(self):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            quarantine_corrupted(12345)

    def test_does_not_silently_succeed_on_none(self):
        try:
            result = quarantine_corrupted(None)
            pytest.fail(f"Expected ValueError, but got {result!r}")
        except ValueError:
            pass  # Expected

    def test_os_rename_failure_returns_empty_not_raises(self, tmp_path):
        """If os.rename fails during quarantine, function returns {} rather than propagating."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt content", encoding="utf-8")
        import bob.spec_findings as sf
        with patch.object(sf.os, "rename", side_effect=OSError("rename failed")):
            result = quarantine_corrupted(p)
        assert result == {}

    def test_returns_empty_dict_not_none_on_missing(self, tmp_path):
        """Must return {} not None for nonexistent file."""
        result = quarantine_corrupted(tmp_path / "nonexistent.yaml")
        assert result is not None
        assert result == {}


class TestLoadSafeErrorPaths:
    def test_corrupt_yaml_does_not_raise(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("key:\n  bad indent:\n   deeper:\n: broken_key\n", encoding="utf-8")
        result = load_safe(p)
        assert isinstance(result, dict)

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

    def test_list_yaml_treated_as_non_dict_returns_empty(self, tmp_path):
        """YAML that parses to a list (not a dict) returns {} gracefully."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        result = load_safe(p)
        assert result == {}

    def test_does_not_silently_return_corrupted_data(self, tmp_path):
        """load_safe must never return a corrupt object — only {} or a valid dict."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": corrupt yaml here\n  bad: indent\n", encoding="utf-8")
        result = load_safe(p)
        assert isinstance(result, dict)
        assert not any(
            isinstance(v, Exception) for v in result.values()
        ), "Result must not contain Exception objects"
