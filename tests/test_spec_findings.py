"""Tests for bob.spec_findings — atomic write, quarantine, and safe load.

Feature 12d2ba50-e129-436c-bf80-a73502b9db53

Covers:
- atomic_write / write_atomic: tmp+rename sequence, no partial writes
- quarantine_corrupted: timestamped rename, structured logging
- load_safe / load_with_corruption_recovery: quarantine on ScannerError, return {}
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import bob.spec_findings as sf
from bob.spec_findings import (
    atomic_write,
    load_safe,
    load_with_corruption_recovery,
    quarantine_corrupted,
    quarantine_corrupt_file,
    write_atomic,
)


class TestAtomicWrite:
    def test_file_created_with_correct_content(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"feature": "12d2ba50", "status": "ok"}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_tmp_file_removed_after_success(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"k": "v"}, target)
        assert not (tmp_path / "spec_findings.yaml.tmp").exists()

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "spec_findings.yaml"
        atomic_write({"x": 1}, target)
        assert target.exists()

    def test_overwrites_previous_valid_content(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"old": True}, target)
        atomic_write({"new": True}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"new": True}

    def test_accepts_string_path(self, tmp_path):
        target = str(tmp_path / "spec_findings.yaml")
        atomic_write({"s": "path"}, target)
        assert Path(target).exists()

    def test_produces_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": 1, "msg": "ok"}], "count": 1}
        atomic_write(data, target)
        content = target.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        assert parsed == data

    def test_rename_failure_propagates(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        with patch.object(sf.os, "rename", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                atomic_write({"k": "v"}, target)

    def test_original_intact_after_rename_failure(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"original": True}, target)
        with patch.object(sf.os, "rename", side_effect=OSError("disk full")):
            try:
                atomic_write({"new": True}, target)
            except OSError:
                pass
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"original": True}


class TestWriteAtomic:
    """AC-facing alias write_atomic delegates to atomic_write."""

    def test_alias_writes_file(self, tmp_path):
        target = tmp_path / "findings.yaml"
        write_atomic({"alias": True}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"alias": True}

    def test_alias_is_importable(self):
        from bob.spec_findings import write_atomic as wa  # noqa: F401
        assert callable(wa)

    def test_alias_behaves_identically_to_atomic_write(self, tmp_path):
        t1 = tmp_path / "a.yaml"
        t2 = tmp_path / "b.yaml"
        data = {"shared": "data", "count": 42}
        atomic_write(data, t1)
        write_atomic(data, t2)
        assert t1.read_text() == t2.read_text()


class TestQuarantineCorrupted:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = quarantine_corrupted(tmp_path / "never_existed.yaml")
        assert result == {}

    def test_file_is_renamed_to_corrupt_path(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": bad yaml here\n", encoding="utf-8")
        quarantine_corrupted(p)
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_returns_empty_dict_after_quarantine(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt: data", encoding="utf-8")
        result = quarantine_corrupted(p)
        assert result == {}

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            quarantine_corrupted(None)

    def test_string_path_accepted(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data: here", encoding="utf-8")
        result = quarantine_corrupted(str(p))
        assert result == {}
        assert not p.exists()

    def test_rename_failure_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt content", encoding="utf-8")
        with patch.object(sf.os, "rename", side_effect=OSError("rename failed")):
            result = quarantine_corrupted(p)
        assert result == {}

    def test_quarantine_corrupt_file_alias(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data: ok", encoding="utf-8")
        result = quarantine_corrupt_file(p)
        assert result == {}
        assert not p.exists()


class TestLoadSafe:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_safe(tmp_path / "missing.yaml")
        assert result == {}

    def test_valid_yaml_loads_correctly(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        data = {"feature_id": "abc", "status": "done"}
        atomic_write(data, p)
        result = load_safe(p)
        assert result == data

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

    def test_empty_file_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        result = load_safe(p)
        assert result == {}

    def test_always_returns_dict(self, tmp_path):
        for content in ["", "null\n", "k: v\n"]:
            p = tmp_path / "spec_findings.yaml"
            p.write_text(content, encoding="utf-8")
            result = load_safe(p)
            assert isinstance(result, dict)


class TestLoadWithCorruptionRecovery:
    """AC-facing alias load_with_corruption_recovery delegates to load_safe."""

    def test_alias_loads_valid_yaml(self, tmp_path):
        p = tmp_path / "findings.yaml"
        atomic_write({"key": "value"}, p)
        result = load_with_corruption_recovery(p)
        assert result == {"key": "value"}

    def test_alias_returns_empty_on_missing(self, tmp_path):
        result = load_with_corruption_recovery(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_alias_quarantines_corrupt_file(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        # Simulate the real production bug: truncated key produces a ScannerError
        # "me: perf-orphan-69\n  [unclosed" triggers "mapping values not allowed here"
        p.write_text("me: perf-orphan-69\n[unclosed bracket", encoding="utf-8")
        result = load_with_corruption_recovery(p)
        assert result == {}
        assert not p.exists()

    def test_alias_is_importable(self):
        from bob.spec_findings import load_with_corruption_recovery as lwr  # noqa: F401
        assert callable(lwr)


class TestAtomicityGuarantee:
    """Verify that partial writes don't corrupt the target."""

    def test_sigkill_simulation_leaves_target_valid(self, tmp_path):
        """Simulate mid-write interruption: tmp written but rename not called."""
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"original": True}, target)

        tmp = Path(str(target) + ".tmp")
        tmp.write_text("partial: content without closing\n  [unclosed", encoding="utf-8")

        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"original": True}

    def test_stale_tmp_does_not_affect_load_safe(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"real": "data"}, target)

        tmp = Path(str(target) + ".tmp")
        tmp.write_text(": corrupt stale tmp\n", encoding="utf-8")

        result = load_safe(target)
        assert result == {"real": "data"}
