"""Tests for bob.spec_findings_io atomic writer + quarantining loader.

Feature a81db7cc-7e62-4135-8875-e4cfda7ddac2

A prior generation's bob process crashed on boot with
yaml.scanner.ScannerError at reviews/spec_findings.yaml — a partial/interrupted
overwrite left a truncated key on disk. Every write to spec_findings.yaml (or
any persisted YAML state file under reviews/) MUST use atomic tmp+rename so a
mid-write SIGTERM/SIGKILL never leaves malformed YAML. On boot, a ScannerError
MUST quarantine the corrupt file (never crash-loop).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from bob.spec_findings_io import (
    atomic_write_findings,
    load_findings_or_quarantine,
)


class TestAtomicWriteFindings:
    def test_writes_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": "f1", "smell": "orphan"}]}
        atomic_write_findings(data, target)
        assert target.exists()
        assert yaml.safe_load(target.read_text(encoding="utf-8")) == data

    def test_empty_dict(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write_findings({}, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded is None or loaded == {}

    def test_accepts_string_path(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write_findings({"k": "v"}, str(target))
        assert target.exists()

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "reviews" / "spec_findings.yaml"
        atomic_write_findings({"k": "v"}, target)
        assert target.exists()

    def test_no_tmp_file_left_on_success(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write_findings({"k": "v"}, target)
        assert not (tmp_path / "spec_findings.yaml.tmp").exists()

    def test_uses_tmp_rename_sequence(self, tmp_path):
        """Write goes through os.rename (atomic), not a direct open on target."""
        target = tmp_path / "spec_findings.yaml"
        import bob.spec_findings_io as sfio
        with patch.object(sfio.os, "rename", wraps=sfio.os.rename) as rn:
            atomic_write_findings({"k": "v"}, target)
        assert rn.called

    def test_overwrite_preserves_previous_on_rename_failure(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write_findings({"original": True}, target)
        import bob.spec_findings_io as sfio
        with patch.object(sfio.os, "rename", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                atomic_write_findings({"new": True}, target)
        assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"original": True}


class TestLoadFindingsOrQuarantine:
    def test_roundtrip(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": [{"id": "x"}]}
        atomic_write_findings(data, target)
        assert load_findings_or_quarantine(target) == data

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_findings_or_quarantine(tmp_path / "nope.yaml") == {}

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        assert load_findings_or_quarantine(p) == {}

    def test_corrupt_yaml_returns_empty_and_quarantines(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        # The exact corruption shape from the incident: a truncated key.
        p.write_text("me: perf-orphan-69\n  bad: indent\n: broken\n", encoding="utf-8")
        result = load_findings_or_quarantine(p)
        assert result == {}
        assert not p.exists()
        quarantined = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
        assert len(quarantined) == 1

    def test_scanner_error_mapping_values_not_allowed(self, tmp_path):
        """Reproduces yaml.scanner.ScannerError mapping-values-not-allowed."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text("key: value: extra colon here\n", encoding="utf-8")
        result = load_findings_or_quarantine(p)
        assert result == {}
        assert not p.exists()

    def test_always_returns_dict(self, tmp_path):
        for content in ["", "null\n", "k: v\n", "- a\n- b\n"]:
            p = tmp_path / "spec_findings.yaml"
            p.write_text(content, encoding="utf-8")
            assert isinstance(load_findings_or_quarantine(p), dict)

    def test_list_yaml_returns_empty(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        assert load_findings_or_quarantine(p) == {}
