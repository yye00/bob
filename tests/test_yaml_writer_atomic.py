"""Tests for bob3.yaml_writer.atomic_write.

Feature d43a5b31-ab9d-4c4a-9149-3e4758979a15

Verifies that atomic_write performs a tmp+rename sequence so that a
mid-write SIGKILL cannot corrupt the target YAML file.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob3.yaml_writer import atomic_write


class TestAtomicWrite:
    def test_writes_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": "F-001", "severity": "error"}]}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "a" / "b" / "spec_findings.yaml"
        atomic_write({"x": 1}, target)
        assert target.exists()

    def test_no_tmp_file_after_successful_write(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"y": 2}, target)
        tmp = Path(str(target) + ".tmp")
        assert not tmp.exists()

    def test_tmp_file_used_during_write(self, tmp_path):
        """Verify the tmp file path is <target>.tmp (by checking rename was called)."""
        target = tmp_path / "spec_findings.yaml"
        rename_calls = []
        real_rename = __import__("os").rename

        def capture_rename(src, dst):
            rename_calls.append((src, dst))
            real_rename(src, dst)

        import bob3.yaml_writer as yw
        with patch.object(yw.os, "rename", side_effect=capture_rename):
            atomic_write({"z": 3}, target)

        assert len(rename_calls) == 1
        src, dst = rename_calls[0]
        assert str(src).endswith(".tmp")
        assert str(dst) == str(target)

    def test_rename_atomicity_preserves_old_content_on_failure(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"original": True}, target)

        import bob3.yaml_writer as yw
        with patch.object(yw.os, "rename", side_effect=OSError("rename failed")):
            try:
                atomic_write({"new": True}, target)
            except OSError:
                pass

        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"original": True}

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"v": 1}, target)
        atomic_write({"v": 2}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"v": 2}

    def test_empty_dict_produces_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({}, target)
        content = target.read_text(encoding="utf-8")
        loaded = yaml.safe_load(content)
        assert loaded is None or loaded == {}

    def test_accepts_string_path(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"str_path": True}, str(target))
        assert target.exists()

    def test_unicode_content(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"msg": "こんにちは — world 🌍"}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_rename_failure_raises_os_error(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        import bob3.yaml_writer as yw
        with patch.object(yw.os, "rename", side_effect=OSError("no space")):
            with pytest.raises(OSError):
                atomic_write({"k": "v"}, target)
