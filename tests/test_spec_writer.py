"""Tests for bob.spec_writer — atomic_write and quarantine_corrupt_yaml.

Feature d6aa0a0e-5939-4134-9832-be59d18a4c3e

Verifies that:
- atomic_write uses a tmp+rename sequence preventing partial-write corruption.
- quarantine_corrupt_yaml moves corrupt files to timestamped quarantine paths
  and returns {} instead of crashing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob.spec_writer import atomic_write, quarantine_corrupt_yaml


class TestAtomicWrite:
    def test_creates_target_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"key": "value"}, target)
        assert target.exists()

    def test_written_content_is_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": "F-001", "severity": "error"}]}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_roundtrip_preserves_data(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_empty_dict_writes_valid_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({}, target)
        assert target.exists()
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded is None or loaded == {}

    def test_accepts_string_path(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"x": 1}, str(target))
        assert target.exists()

    def test_overwrites_previous_content(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"version": 1}, target)
        atomic_write({"version": 2}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"version": 2}

    def test_tmp_file_removed_after_successful_write(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"k": "v"}, target)
        assert not (tmp_path / "spec_findings.yaml.tmp").exists()

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "nested" / "dir" / "spec_findings.yaml"
        atomic_write({"k": "v"}, target)
        assert target.exists()

    def test_rename_failure_propagates_os_error(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        import bob.spec_writer as sw
        with patch.object(sw.os, "rename", side_effect=OSError("rename failed")):
            with pytest.raises(OSError):
                atomic_write({"k": "v"}, target)

    def test_target_unchanged_on_rename_failure(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"original": True}, target)
        import bob.spec_writer as sw
        with patch.object(sw.os, "rename", side_effect=OSError("rename failed")):
            try:
                atomic_write({"new": True}, target)
            except OSError:
                pass
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"original": True}

    def test_fsync_called_before_rename(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        import bob.spec_writer as sw
        fsync_called = []
        original_fsync = sw.os.fsync

        def tracking_fsync(fd):
            fsync_called.append(fd)
            return original_fsync(fd)

        with patch.object(sw.os, "fsync", side_effect=tracking_fsync):
            atomic_write({"k": "v"}, target)

        assert len(fsync_called) >= 1

    def test_unicode_data_preserved(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"message": "こんにちは — café ñoño"}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_write_to_reviews_dir(self, tmp_path):
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()
        target = reviews_dir / "spec_findings.yaml"
        atomic_write({"findings": [], "version": "1.0"}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"findings": [], "version": "1.0"}


class TestQuarantineCorruptYaml:
    def test_nonexistent_file_returns_empty_dict(self, tmp_path):
        result = quarantine_corrupt_yaml(tmp_path / "never_existed.yaml")
        assert result == {}

    def test_existing_file_is_moved(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt: content\n  bad: indent\n", encoding="utf-8")
        result = quarantine_corrupt_yaml(p)
        assert result == {}
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_returns_empty_dict_not_none(self, tmp_path):
        result = quarantine_corrupt_yaml(tmp_path / "missing.yaml")
        assert result is not None
        assert isinstance(result, dict)
        assert result == {}

    def test_none_path_raises_value_error(self):
        with pytest.raises(ValueError):
            quarantine_corrupt_yaml(None)

    def test_string_path_accepted(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data: here\n", encoding="utf-8")
        result = quarantine_corrupt_yaml(str(p))
        assert result == {}
        assert not p.exists()

    def test_quarantine_path_has_timestamp_suffix(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("x: y\n", encoding="utf-8")
        quarantine_corrupt_yaml(p)
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1
        suffix = quarantine_files[0].name.split(".corrupt.")[1]
        assert suffix.isdigit()

    def test_rename_failure_returns_empty_not_raises(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt content", encoding="utf-8")
        import bob.spec_writer as sw
        with patch.object(sw.os, "rename", side_effect=OSError("rename failed")):
            result = quarantine_corrupt_yaml(p)
        assert result == {}

    def test_empty_file_quarantines(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        result = quarantine_corrupt_yaml(p)
        assert result == {}
        assert not p.exists()
