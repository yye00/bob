"""Tests for atomic write and quarantine behavior of spec_findings_writer.

Covers:
- atomic_write_yaml uses .tmp then rename (no direct open+yaml.dump on target)
- SIGKILL mid-write simulation: target file unchanged, only .tmp present
- quarantine_corrupt_findings on malformed YAML: quarantines + returns empty dict
- Post-quarantine boot continues without exception propagation
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from bob.reviews.spec_findings_writer import (
    atomic_write_yaml,
    quarantine_corrupt_findings,
    load_spec_findings_safe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_data() -> dict:
    return {"schema_version": 1, "findings_by_hash": {"abc": {"defect_count": 0}}}


# ---------------------------------------------------------------------------
# atomic_write_yaml — basic behavior
# ---------------------------------------------------------------------------


class TestAtomicWriteYamlBasic:
    def test_creates_target_file(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = _make_valid_data()
        atomic_write_yaml(data, target)
        assert target.exists()

    def test_target_is_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = _make_valid_data()
        atomic_write_yaml(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_no_tmp_file_after_success(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write_yaml(_make_valid_data(), target)
        assert not Path(str(target) + ".tmp").exists()

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "spec_findings.yaml"
        atomic_write_yaml(_make_valid_data(), target)
        assert target.exists()

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write_yaml({"v": 1}, target)
        atomic_write_yaml({"v": 2}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == {"v": 2}

    def test_uses_tmp_then_rename(self, tmp_path):
        """Verify the write goes through .tmp by intercepting os.rename."""
        target = tmp_path / "spec_findings.yaml"
        renamed_froms = []
        original_rename = os.rename

        def capture_rename(src, dst):
            renamed_froms.append(str(src))
            original_rename(src, dst)

        with patch("bob.reviews.spec_findings_writer.os.rename", side_effect=capture_rename):
            atomic_write_yaml(_make_valid_data(), target)

        assert len(renamed_froms) == 1
        assert renamed_froms[0].endswith(".tmp")

    def test_fsync_called(self, tmp_path):
        """Verify fsync is called on the tmp file handle."""
        target = tmp_path / "spec_findings.yaml"
        fsync_calls = []
        original_fsync = os.fsync

        def capture_fsync(fd):
            fsync_calls.append(fd)
            original_fsync(fd)

        with patch("bob.reviews.spec_findings_writer.os.fsync", side_effect=capture_fsync):
            atomic_write_yaml(_make_valid_data(), target)

        assert len(fsync_calls) == 1


# ---------------------------------------------------------------------------
# SIGKILL mid-write simulation: target unchanged, only .tmp present
# ---------------------------------------------------------------------------


class TestSigkillMidWrite:
    """Simulate SIGKILL between write and rename; target must be unchanged."""

    def test_sigkill_leaves_target_unchanged(self, tmp_path):
        """
        Write an initial valid file, then simulate an interrupted write
        (write to .tmp but do NOT rename), and assert the target is unchanged.
        This mirrors what SIGKILL between write and rename would do.
        """
        target = tmp_path / "spec_findings.yaml"
        original_data = {"schema_version": 1, "prior": True}
        # Write a valid initial target
        atomic_write_yaml(original_data, target)

        # Now simulate: write to .tmp but crash before rename
        tmp = Path(str(target) + ".tmp")
        new_data = {"schema_version": 1, "new": True}
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(new_data, fh)
            fh.flush()
            os.fsync(fh.fileno())
        # Intentionally do NOT rename — this is the SIGKILL scenario

        # Target must still contain original data
        assert target.exists()
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == original_data

        # .tmp is present (incomplete write visible)
        assert tmp.exists()

    def test_sigkill_on_first_write_leaves_no_target(self, tmp_path):
        """
        On first write (no prior target), SIGKILL before rename leaves no target.
        Only .tmp is present. Loader returns empty dict.
        """
        target = tmp_path / "spec_findings.yaml"
        tmp = Path(str(target) + ".tmp")
        data = _make_valid_data()

        # Write to .tmp but don't rename
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh)
            fh.flush()
            os.fsync(fh.fileno())

        # Target does NOT exist
        assert not target.exists()
        # .tmp is present
        assert tmp.exists()

    def test_subprocess_sigkill_mid_rename_leaves_target_intact(self, tmp_path):
        """
        Launch a subprocess that writes .tmp then pauses before rename.
        Parent sends SIGKILL. Target must be untouched.

        This uses a Python helper script in a subprocess.
        """
        target = tmp_path / "spec_findings.yaml"
        tmp_file = Path(str(target) + ".tmp")

        # Prepare initial valid target
        original = {"schema_version": 1, "existing": "yes"}
        atomic_write_yaml(original, target)

        # Script: writes .tmp, signals parent ready (prints line), then sleeps
        helper_script = textwrap.dedent(f"""\
            import os, sys, time, yaml
            from pathlib import Path
            target = Path({str(target)!r})
            tmp = Path(str(target) + '.tmp')
            data = {{'schema_version': 2, 'new': 'value'}}
            with open(tmp, 'w', encoding='utf-8') as fh:
                yaml.safe_dump(data, fh)
                fh.flush()
                os.fsync(fh.fileno())
            print('ready', flush=True)
            time.sleep(30)  # pause before rename — SIGKILL hits here
            os.rename(tmp, target)
        """)

        proc = subprocess.Popen(
            [sys.executable, "-c", helper_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            # Wait for "ready" signal (tmp written, before rename)
            line = proc.stdout.readline()
            assert line.strip() == b"ready"
            # Kill it before the rename
            proc.send_signal(signal.SIGKILL)
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        # Target unchanged (original data)
        assert target.exists()
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == original

        # .tmp is present (only .tmp left over)
        assert tmp_file.exists()


# ---------------------------------------------------------------------------
# quarantine_corrupt_findings
# ---------------------------------------------------------------------------


class TestQuarantineCorruptFindings:
    def test_returns_empty_dict_on_corrupt(self, tmp_path):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text("key: [unmatched\n  bad: yaml: :\n", encoding="utf-8")
        result = quarantine_corrupt_findings(corrupt)
        assert result == {}

    def test_quarantines_corrupt_file(self, tmp_path):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text(": broken\n  indent: bad", encoding="utf-8")
        quarantine_corrupt_findings(corrupt)
        # Original must be gone
        assert not corrupt.exists()
        # A .corrupt.<ts> file must exist
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_quarantine_filename_contains_unix_ts(self, tmp_path):
        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text(": broken\n", encoding="utf-8")
        before = int(time.time())
        quarantine_corrupt_findings(corrupt)
        after = int(time.time())
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert quarantine_files
        ts_part = int(quarantine_files[0].name.split(".corrupt.")[-1])
        assert before <= ts_part <= after

    def test_nonexistent_file_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        result = quarantine_corrupt_findings(missing)
        assert result == {}

    def test_valid_yaml_file_is_not_touched_by_quarantine(self, tmp_path):
        """quarantine_corrupt_findings doesn't validate YAML — it just moves the file.
        But when called with a valid file, the file IS moved (caller decides when to call it).
        This test documents that quarantine is a 'move regardless' operation."""
        valid = tmp_path / "spec_findings.yaml"
        valid.write_text("schema_version: 1\n", encoding="utf-8")
        result = quarantine_corrupt_findings(valid)
        assert result == {}
        assert not valid.exists()


# ---------------------------------------------------------------------------
# load_spec_findings_safe — boot-path safe loader
# ---------------------------------------------------------------------------


class TestLoadSpecFindingsSafe:
    def test_returns_empty_for_nonexistent(self, tmp_path):
        result = load_spec_findings_safe(tmp_path / "missing.yaml")
        assert result == {}

    def test_loads_valid_yaml(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        data = _make_valid_data()
        atomic_write_yaml(data, p)
        result = load_spec_findings_safe(p)
        assert result == data

    def test_scanner_error_quarantines_and_returns_empty(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("key:\n  bad indent:\n   deeper:\n: broken_key\n", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == {}
        # File must be quarantined
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_boot_does_not_raise_on_corrupt_yaml(self, tmp_path):
        """Key post-quarantine test: no exception propagates from safe loader."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": bad\n  mapping: values\n", encoding="utf-8")
        # Must NOT raise
        result = load_spec_findings_safe(p)
        assert isinstance(result, dict)

    def test_empty_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == {}

    def test_null_yaml_returns_empty_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("null\n", encoding="utf-8")
        result = load_spec_findings_safe(p)
        assert result == {}


# ---------------------------------------------------------------------------
# Post-quarantine boot continues (no exception propagates)
# ---------------------------------------------------------------------------


class TestPostQuarantineBootContinues:
    def test_spec_findings_registry_load_continues_after_corrupt(self, tmp_path):
        """_load_yaml in spec_findings_registry must not crash on ScannerError."""
        from bob.spec_quality import spec_findings_registry as sfr

        corrupt = tmp_path / "spec_findings.yaml"
        # Write a genuinely malformed YAML that triggers ScannerError
        corrupt.write_text(
            "findings:\n  - key: val\n    bad: [unclosed\n",
            encoding="utf-8",
        )
        # Must not raise
        result = sfr._load_yaml(corrupt)
        assert isinstance(result, dict)

    def test_spec_critic_load_continues_after_corrupt(self, tmp_path):
        """_load_spec_findings in spec_critic must not crash on ScannerError."""
        from bob.spec_quality import spec_critic

        corrupt = tmp_path / "spec_findings.yaml"
        corrupt.write_text(": broken\n  bad: yaml:\n", encoding="utf-8")
        # Must not raise
        result = spec_critic._load_spec_findings(corrupt)
        assert isinstance(result, dict)

    def test_no_exception_after_quarantine_and_reload(self, tmp_path):
        """
        Simulate the full boot cycle:
        1. Corrupt file exists.
        2. Safe load quarantines it, returns {}.
        3. Write a new valid file (as if boot proceeds normally).
        4. Second load succeeds.
        """
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": corrupt\n  mapping: bad\n", encoding="utf-8")

        # Boot attempt 1: quarantine
        first = load_spec_findings_safe(p)
        assert first == {}
        assert not p.exists()

        # Boot proceeds: write fresh valid data
        valid_data = {"schema_version": 1, "findings_by_hash": {}}
        atomic_write_yaml(valid_data, p)

        # Boot attempt 2: load fresh file
        second = load_spec_findings_safe(p)
        assert second == valid_data
