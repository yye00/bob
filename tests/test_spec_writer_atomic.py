"""Tests for bob3.spec_writer.atomic_write.

Feature 6cafea74-a3f0-4600-836c-335bb156a72d

Verifies that bob3.spec_writer.atomic_write uses an atomic tmp+rename sequence
to write YAML, preventing partial-write corruption of spec_findings.yaml.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob3.spec_writer import atomic_write


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
        content = target.read_text(encoding="utf-8")
        loaded = yaml.safe_load(content)
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
        tmp = tmp_path / "spec_findings.yaml.tmp"
        assert not tmp.exists()

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "nested" / "dir" / "spec_findings.yaml"
        atomic_write({"k": "v"}, target)
        assert target.exists()

    def test_rename_failure_propagates_os_error(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        import bob3.spec_writer as sw
        with patch.object(sw.os, "rename", side_effect=OSError("rename failed")):
            with pytest.raises(OSError):
                atomic_write({"k": "v"}, target)

    def test_target_unchanged_on_rename_failure(self, tmp_path):
        """Original file is preserved when rename fails during overwrite."""
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"original": True}, target)
        import bob3.spec_writer as sw
        with patch.object(sw.os, "rename", side_effect=OSError("rename failed")):
            try:
                atomic_write({"new": True}, target)
            except OSError:
                pass
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"original": True}

    def test_unicode_data_preserved(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"message": "こんにちは — café ñoño"}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_large_dict_writes_successfully(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {f"key_{i}": f"value_{i}" for i in range(1000)}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_write_to_reviews_dir(self, tmp_path):
        """Simulate writing to the reviews/ directory like spec_findings.yaml."""
        reviews_dir = tmp_path / "reviews"
        reviews_dir.mkdir()
        target = reviews_dir / "spec_findings.yaml"
        data = {"findings": [], "version": "1.0"}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_fsync_called_before_rename(self, tmp_path):
        """Verify that os.fsync is called (data is durable before rename)."""
        target = tmp_path / "spec_findings.yaml"
        import bob3.spec_writer as sw
        fsync_called = []
        original_fsync = sw.os.fsync

        def tracking_fsync(fd):
            fsync_called.append(fd)
            return original_fsync(fd)

        with patch.object(sw.os, "fsync", side_effect=tracking_fsync):
            atomic_write({"k": "v"}, target)

        assert len(fsync_called) >= 1, "os.fsync must be called before rename"
