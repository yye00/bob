"""Tests for spec_findings.yaml atomic write and corrupt-file quarantine.

Feature 231a63be-dfc9-4b04-9c1e-24564b6f8e90

spec_findings.yaml writers MUST use atomic tmp+rename to prevent
partial-write corruption that kills bob3 boot with ScannerError.

On ScannerError at boot, the loader MUST quarantine the file and
return empty findings rather than crash-looping.

AC:
 - Function defined: bob3.spec_findings_yaml_writer_must_use_atomic_tmp_rename_...
 - pytest: tests/test_spec_findings_yaml_writer_must_use_atomic_tmp_rename_...::test_spec_findings_yaml_writer_must_use_atomic_tmp_rename_...
"""

from __future__ import annotations

import importlib
import logging
import os
import tempfile
from pathlib import Path

import yaml

_MOD = (
    "bob3.spec_findings_yaml_writer_must_use_atomic_tmp_rename_"
    "partial_write_corruption_kills_bob3_boot_scannererror_mapping_values_not_allowed"
)
_FUNC = (
    "spec_findings_yaml_writer_must_use_atomic_tmp_rename_"
    "partial_write_corruption_kills_bob3_boot_scannererror_mapping_values_not_allowed"
)


def _import_func():
    mod = importlib.import_module(_MOD)
    return getattr(mod, _FUNC)


def _import_mod():
    return importlib.import_module(_MOD)


# ---------------------------------------------------------------------------
# AC smoke test — the one AC-named test that must pass
# ---------------------------------------------------------------------------


def test_spec_findings_yaml_writer_must_use_atomic_tmp_rename_partial_write_corruption_kills_bob3_boot_scannererror_mapping_values_not_allowed():
    """Main AC test: function is importable, callable, and performs atomic write+quarantine."""
    fn = _import_func()
    assert callable(fn)

    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "spec_findings.yaml"
        test_data = {"findings": [{"id": "perf-orphan-42", "severity": "high"}]}

        result = fn(data=test_data, path=target)

        # File must exist and be valid YAML
        assert target.exists(), "Target file must be written"
        assert not Path(str(target) + ".tmp").exists(), "Tmp file must not remain after rename"

        loaded = yaml.safe_load(target.read_text())
        assert loaded == test_data, "Written YAML must round-trip correctly"

        # Result must report success
        assert result["success"] is True
        assert result["path"] == str(target)


# ---------------------------------------------------------------------------
# Additional behavioral tests
# ---------------------------------------------------------------------------


def test_import_is_possible():
    fn = _import_func()
    assert fn is not None
    assert callable(fn)


def test_atomic_write_leaves_valid_yaml(tmp_path):
    """atomic_write_yaml must produce a loadable YAML file."""
    mod = _import_mod()
    target = tmp_path / "reviews" / "spec_findings.yaml"
    data = {"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
    mod.atomic_write_yaml(data, target)
    assert target.exists()
    loaded = yaml.safe_load(target.read_text())
    assert loaded == data


def test_atomic_write_no_tmp_after_success(tmp_path):
    """Tmp file must not survive after a successful write."""
    mod = _import_mod()
    target = tmp_path / "spec_findings.yaml"
    mod.atomic_write_yaml({"x": 1}, target)
    assert not Path(str(target) + ".tmp").exists()


def test_atomic_write_creates_parent_dirs(tmp_path):
    """atomic_write_yaml must create parent directories if missing."""
    mod = _import_mod()
    target = tmp_path / "deep" / "nested" / "spec_findings.yaml"
    mod.atomic_write_yaml({"hello": "world"}, target)
    assert target.exists()


def test_quarantine_corrupt_file(tmp_path):
    """quarantine_corrupt_findings must rename the corrupt file and return {}."""
    mod = _import_mod()
    target = tmp_path / "spec_findings.yaml"
    target.write_text("me: perf-orphan-69\n  bad: indent: here\n  corrupt: [unclosed")

    result = mod.quarantine_corrupt_findings(target)

    assert result == {}, "Must return empty dict on corrupt file"
    assert not target.exists(), "Original corrupt file must be moved"
    quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
    assert len(quarantine_files) == 1, "One quarantine file must be created"


def test_quarantine_missing_file_returns_empty(tmp_path):
    """quarantine_corrupt_findings returns {} when file does not exist."""
    mod = _import_mod()
    result = mod.quarantine_corrupt_findings(tmp_path / "nonexistent.yaml")
    assert result == {}


def test_load_spec_findings_safe_valid_file(tmp_path):
    """load_spec_findings_safe returns data from a valid YAML file."""
    mod = _import_mod()
    target = tmp_path / "spec_findings.yaml"
    expected = {"findings": [{"id": "test-1"}]}
    target.write_text(yaml.safe_dump(expected))
    result = mod.load_spec_findings_safe(target)
    assert result == expected


def test_load_spec_findings_safe_missing_file(tmp_path):
    """load_spec_findings_safe returns {} when file does not exist."""
    mod = _import_mod()
    result = mod.load_spec_findings_safe(tmp_path / "absent.yaml")
    assert result == {}


def test_load_spec_findings_safe_corrupt_file(tmp_path):
    """load_spec_findings_safe quarantines corrupt file and returns {}."""
    mod = _import_mod()
    target = tmp_path / "spec_findings.yaml"
    target.write_text("me: perf-orphan-69\n  bad indent:\n  [unclosed")
    result = mod.load_spec_findings_safe(target)
    assert result == {}
    assert not target.exists(), "Corrupt file must be quarantined"
    quarantine_files = list(tmp_path.glob("spec_findings.yaml.corrupt.*"))
    assert len(quarantine_files) == 1


def test_load_spec_findings_safe_empty_file(tmp_path):
    """load_spec_findings_safe returns {} for an empty YAML file."""
    mod = _import_mod()
    target = tmp_path / "spec_findings.yaml"
    target.write_text("")
    result = mod.load_spec_findings_safe(target)
    assert result == {}


def test_load_spec_findings_safe_logs_corrupt_event(tmp_path, caplog):
    """load_spec_findings_safe emits structured spec_findings_corrupt log on corrupt file."""
    mod = _import_mod()
    target = tmp_path / "spec_findings.yaml"
    target.write_text(": bad yaml :\n  - [unclosed")
    with caplog.at_level(logging.ERROR):
        mod.load_spec_findings_safe(target)
    assert any("spec_findings_corrupt" in r.message for r in caplog.records), (
        "Expected spec_findings_corrupt in log records"
    )


def test_quarantine_logs_structured_event(tmp_path, caplog):
    """quarantine_corrupt_findings logs a structured spec_findings_corrupt event."""
    mod = _import_mod()
    target = tmp_path / "spec_findings.yaml"
    target.write_text("corrupt data here")
    with caplog.at_level(logging.ERROR):
        mod.quarantine_corrupt_findings(target)
    assert any("spec_findings_corrupt" in r.message for r in caplog.records)


def test_main_function_quarantines_on_corrupt_input(tmp_path):
    """Main feature function: passing corrupt=True triggers quarantine path."""
    fn = _import_func()

    # Write a genuinely corrupt file (mapping-values-not-allowed style)
    target = tmp_path / "spec_findings.yaml"
    target.write_text("key: value\n  bad_indent: here\nkey: : : invalid")

    result = fn(data=None, path=target, quarantine_if_corrupt=True)

    assert result["quarantined"] is True
    assert not target.exists()


def test_main_function_roundtrip_empty_dict(tmp_path):
    """Main feature function handles empty dict without error."""
    fn = _import_func()
    target = tmp_path / "spec_findings.yaml"
    result = fn(data={}, path=target)
    assert result["success"] is True
    loaded = yaml.safe_load(target.read_text())
    assert loaded == {} or loaded is None
