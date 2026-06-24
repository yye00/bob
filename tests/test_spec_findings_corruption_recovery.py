"""Recovery tests for bob3.spec_findings corruption handling.

Feature 280eba15-9818-41d0-a392-f61067a112ce

Verifies that bob3 boot-path survives a corrupt spec_findings.yaml via
quarantine, returning empty findings rather than crash-looping.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest
import yaml

from bob3.spec_findings import (
    atomic_write,
    quarantine_corrupt_file,
    quarantine_corrupted,
    load_safe,
)


class TestQuarantineCorruptFile:
    """Tests for the quarantine_corrupt_file AC-facing function."""

    def test_function_is_importable(self):
        from bob3.spec_findings import quarantine_corrupt_file
        assert callable(quarantine_corrupt_file)

    def test_nonexistent_file_returns_empty_dict(self, tmp_path):
        result = quarantine_corrupt_file(tmp_path / "never_existed.yaml")
        assert result == {}

    def test_returns_empty_dict_for_existing_file(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt: data", encoding="utf-8")
        result = quarantine_corrupt_file(p)
        assert result == {}

    def test_moves_file_to_quarantine_path(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt: data", encoding="utf-8")
        quarantine_corrupt_file(p)
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

    def test_quarantine_filename_has_unix_timestamp(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt", encoding="utf-8")
        before = int(time.time())
        quarantine_corrupt_file(p)
        after = int(time.time())
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert quarantine_files
        ts = int(quarantine_files[0].name.split(".corrupt.")[-1])
        assert before <= ts <= after

    def test_none_path_raises_value_error(self):
        with pytest.raises(ValueError):
            quarantine_corrupt_file(None)

    def test_accepts_string_path(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt: content", encoding="utf-8")
        result = quarantine_corrupt_file(str(p))
        assert result == {}
        assert not p.exists()

    def test_logs_structured_event(self, tmp_path, caplog):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("corrupt: content", encoding="utf-8")
        with caplog.at_level(logging.ERROR):
            quarantine_corrupt_file(p)
        assert any("spec_findings_corrupt" in r.message for r in caplog.records)

    def test_is_equivalent_to_quarantine_corrupted(self, tmp_path):
        """quarantine_corrupt_file must produce same behavior as quarantine_corrupted."""
        p1 = tmp_path / "a" / "spec_findings.yaml"
        p2 = tmp_path / "b" / "spec_findings.yaml"
        p1.parent.mkdir()
        p2.parent.mkdir()
        p1.write_text("corrupt: data", encoding="utf-8")
        p2.write_text("corrupt: data", encoding="utf-8")

        r1 = quarantine_corrupt_file(p1)
        r2 = quarantine_corrupted(p2)
        assert r1 == r2 == {}
        assert not p1.exists()
        assert not p2.exists()


class TestCorruptionRecovery:
    """Integration-level recovery: corrupt file → quarantine → fresh write → load."""

    def test_full_recovery_cycle(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        # Write a corrupt file (simulates truncated mid-write)
        p.write_text("me: perf-orphan-69\n  bad: indent\n  [unclosed", encoding="utf-8")

        # Boot-path loader must not raise
        result = load_safe(p)
        assert result == {}

        # File must be quarantined
        assert not p.exists()
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantine_files) == 1

        # Write fresh valid data
        fresh = {"schema_version": 1, "findings_by_hash": {}}
        atomic_write(fresh, p)

        # Second load must succeed
        result2 = load_safe(p)
        assert result2 == fresh

    def test_scanner_error_does_not_crash_boot(self, tmp_path):
        """Any yaml.scanner.ScannerError must be caught, not re-raised."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text(": bad mapping values not allowed\n  x: y\n", encoding="utf-8")
        result = load_safe(p)
        assert isinstance(result, dict)
        assert result == {}

    def test_multiple_corrupt_files_accumulate_quarantines(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        for i in range(3):
            p.write_text(f"corrupt_version_{i}: [unclosed", encoding="utf-8")
            load_safe(p)
            # Each call quarantines; file is gone, so next iteration re-creates it
        quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        # Multiple calls may collapse to fewer files if they share the same unix second;
        # what matters is at least one quarantine file exists and the target is gone.
        assert len(quarantine_files) >= 1
        assert not p.exists()

    def test_valid_file_survives_recovery_path(self, tmp_path):
        """A valid file must NOT be quarantined."""
        p = tmp_path / "spec_findings.yaml"
        valid = {"findings_by_hash": {"abc123": {"severity": "low"}}}
        atomic_write(valid, p)
        result = load_safe(p)
        assert result == valid
        assert p.exists()

    def test_quarantine_corrupt_file_used_in_recovery(self, tmp_path):
        """quarantine_corrupt_file can be used directly in a recovery flow."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text("me: perf-orphan-69\n  bad_indent: here\n", encoding="utf-8")

        recovery_result = quarantine_corrupt_file(p)
        assert recovery_result == {}
        assert not p.exists()

        # After quarantine, write fresh and verify
        atomic_write({"recovered": True}, p)
        loaded = load_safe(p)
        assert loaded == {"recovered": True}

    def test_empty_findings_is_recoverable_not_fatal(self, tmp_path):
        """Empty findings dict (post-quarantine) allows bob3 to continue."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text("garbage: [unclosed bracket", encoding="utf-8")
        findings = load_safe(p)
        # An empty dict is acceptable — bob3 continues with no findings
        assert findings == {}
        assert isinstance(findings, dict)
