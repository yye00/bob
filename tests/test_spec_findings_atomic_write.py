"""Tests for bob.spec_findings atomic_write and quarantine_corrupted.

Feature b37d0f34-5d02-4fdc-be9b-b205e2839fcb

spec_findings.yaml writers MUST use atomic tmp+rename to prevent
partial-write corruption that kills bob boot with ScannerError
mapping-values-not-allowed.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest
import yaml

from bob.spec_findings import atomic_write, quarantine_corrupted, load_safe


# ---------------------------------------------------------------------------
# atomic_write tests
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_creates_target_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": "perf-orphan-1", "severity": "high"}]}
        atomic_write(data, target)
        assert target.exists()

    def test_written_yaml_round_trips(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_no_tmp_file_remains_after_success(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"x": 1}, target)
        assert not Path(str(target) + ".tmp").exists()

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "spec_findings.yaml"
        atomic_write({"hello": "world"}, target)
        assert target.exists()

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"v": 1}, target)
        atomic_write({"v": 2}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"v": 2}

    def test_uses_tmp_then_rename(self, tmp_path):
        """Verify write goes through .tmp via os.rename interception."""
        target = tmp_path / "spec_findings.yaml"
        renamed_froms = []
        original_rename = os.rename

        def capture_rename(src, dst):
            renamed_froms.append(str(src))
            original_rename(src, dst)

        import bob.spec_findings as sf
        from unittest.mock import patch
        with patch.object(sf.os, "rename", side_effect=capture_rename):
            atomic_write({"x": 1}, target)

        assert len(renamed_froms) == 1
        assert renamed_froms[0].endswith(".tmp")

    def test_fsync_called(self, tmp_path):
        """Verify fsync is called before rename."""
        target = tmp_path / "spec_findings.yaml"
        fsync_calls = []
        original_fsync = os.fsync

        def capture_fsync(fd):
            fsync_calls.append(fd)
            original_fsync(fd)

        import bob.spec_findings as sf
        from unittest.mock import patch
        with patch.object(sf.os, "fsync", side_effect=capture_fsync):
            atomic_write({"x": 1}, target)

        assert len(fsync_calls) == 1

    def test_empty_dict_writes_successfully(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({}, target)
        assert target.exists()

    def test_accepts_string_path(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"key": "val"}, str(target))
        assert target.exists()
        loaded = yaml.safe_load(target.read_text())
        assert loaded == {"key": "val"}

    def test_target_contains_previous_version_after_interrupted_write(self, tmp_path):
        """Simulate SIGKILL between write and rename — target remains unchanged."""
        target = tmp_path / "spec_findings.yaml"
        original_data = {"schema_version": 1, "prior": True}
        atomic_write(original_data, target)

        # Write to .tmp but do NOT rename (simulates SIGKILL mid-write)
        tmp = Path(str(target) + ".tmp")
        new_data = {"schema_version": 2, "new": True}
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(new_data, fh)
            fh.flush()
            os.fsync(fh.fileno())
        # Intentionally skip os.rename — this is the interrupt

        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == original_data


# ---------------------------------------------------------------------------
# quarantine_corrupted tests
# ---------------------------------------------------------------------------


class TestQuarantineCorrupted:
    def test_returns_empty_dict_on_corrupt_file(self, tmp_path):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text("key: [unmatched\n  bad: yaml: :\n", encoding="utf-8")
        result = quarantine_corrupted(corrupt)
        assert result == {}

    def test_moves_corrupt_file_to_quarantine_path(self, tmp_path):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text(": broken\n  indent: bad", encoding="utf-8")
        quarantine_corrupted(corrupt)
        assert not corrupt.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_quarantine_filename_contains_unix_timestamp(self, tmp_path):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text(": broken\n", encoding="utf-8")
        before = int(time.time())
        quarantine_corrupted(corrupt)
        after = int(time.time())
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert quarantine_files
        ts_part = int(quarantine_files[0].name.split(".corrupt.")[-1])
        assert before <= ts_part <= after

    def test_nonexistent_file_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = quarantine_corrupted(missing)
        assert result == {}

    def test_none_path_raises_value_error(self):
        with pytest.raises(ValueError):
            quarantine_corrupted(None)

    def test_accepts_string_path(self, tmp_path):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text("corrupt content", encoding="utf-8")
        result = quarantine_corrupted(str(corrupt))
        assert result == {}
        assert not corrupt.exists()

    def test_logs_structured_corrupt_event(self, tmp_path, caplog):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text("corrupt data", encoding="utf-8")
        with caplog.at_level(logging.ERROR):
            quarantine_corrupted(corrupt)
        assert any("spec_findings_corrupt" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# load_safe tests
# ---------------------------------------------------------------------------


class TestLoadSafe:
    def test_returns_empty_for_nonexistent_file(self, tmp_path):
        result = load_safe(tmp_path / "missing.yaml")
        assert result == {}

    def test_loads_valid_yaml(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": "test-1"}]}
        atomic_write(data, p)
        result = load_safe(p)
        assert result == data

    def test_scanner_error_quarantines_and_returns_empty(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("key:\n  bad indent:\n   deeper:\n: broken_key\n", encoding="utf-8")
        result = load_safe(p)
        assert result == {}
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_does_not_raise_on_corrupt_yaml(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": bad\n  mapping: values\n", encoding="utf-8")
        result = load_safe(p)
        assert isinstance(result, dict)

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

    def test_logs_corrupt_event_on_scanner_error(self, tmp_path, caplog):
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": bad yaml :\n  - [unclosed", encoding="utf-8")
        with caplog.at_level(logging.ERROR):
            load_safe(p)
        assert any("spec_findings_corrupt" in r.message for r in caplog.records)

    def test_full_quarantine_and_reload_cycle(self, tmp_path):
        """Simulate boot cycle: corrupt → quarantine → write fresh → reload."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": corrupt\n  mapping: bad\n", encoding="utf-8")

        first = load_safe(p)
        assert first == {}
        assert not p.exists()

        valid_data = {"schema_version": 1, "findings_by_hash": {}}
        atomic_write(valid_data, p)

        second = load_safe(p)
        assert second == valid_data
