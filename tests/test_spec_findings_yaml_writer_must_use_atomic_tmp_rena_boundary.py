"""Boundary tests for bob3.spec_findings atomic_write and quarantine_corrupted.

Feature b37d0f34-5d02-4fdc-be9b-b205e2839fcb

Boundary case: empty, zero, or minimum input returns a well-defined result
rather than raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob3.spec_findings import atomic_write, quarantine_corrupted, load_safe


class TestAtomicWriteBoundary:
    def test_empty_dict_does_not_raise(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({}, target)
        assert target.exists()

    def test_empty_dict_produces_valid_yaml(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({}, target)
        content = target.read_text(encoding="utf-8")
        loaded = yaml.safe_load(content)
        assert loaded is None or loaded == {}

    def test_single_key_dict(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"k": "v"}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_deeply_nested_dict(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"a": {"b": {"c": {"d": "leaf"}}}}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_dict_with_empty_list(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        data = {"findings": []}
        atomic_write(data, target)
        loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_single_character_string_path(self, tmp_path):
        target = tmp_path / "x"
        atomic_write({"z": 1}, str(target))
        assert target.exists()

    def test_path_with_no_extension(self, tmp_path):
        target = tmp_path / "findings"
        atomic_write({"data": True}, target)
        assert target.exists()

    def test_target_in_existing_dir_succeeds(self, tmp_path):
        target = tmp_path / "spec_findings.yaml"
        atomic_write({"found": "yes"}, target)
        assert target.exists()


class TestQuarantineCorruptedBoundary:
    def test_nonexistent_file_returns_empty_dict(self, tmp_path):
        result = quarantine_corrupted(tmp_path / "never_existed.yaml")
        assert result == {}

    def test_empty_file_quarantines_and_returns_empty(self, tmp_path):
        """Empty file is a degenerate (zero-content) case — quarantine it."""
        p = tmp_path / "spec_findings.yaml"
        p.write_text("", encoding="utf-8")
        result = quarantine_corrupted(p)
        assert result == {}
        assert not p.exists()

    def test_file_with_single_newline_quarantines(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("\n", encoding="utf-8")
        result = quarantine_corrupted(p)
        assert result == {}
        assert not p.exists()

    def test_string_path_accepted(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("data: here", encoding="utf-8")
        result = quarantine_corrupted(str(p))
        assert result == {}

    def test_returns_dict_type(self, tmp_path):
        result = quarantine_corrupted(tmp_path / "nonexistent.yaml")
        assert isinstance(result, dict)


class TestLoadSafeBoundary:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        result = load_safe(tmp_path / "missing.yaml")
        assert result == {}

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

    def test_minimum_valid_yaml_dict(self, tmp_path):
        p = tmp_path / "spec_findings.yaml"
        p.write_text("k: v\n", encoding="utf-8")
        result = load_safe(p)
        assert result == {"k": "v"}

    def test_always_returns_dict(self, tmp_path):
        for content in ["", "null\n", "k: v\n"]:
            p = tmp_path / "spec_findings.yaml"
            p.write_text(content, encoding="utf-8")
            result = load_safe(p)
            assert isinstance(result, dict), f"Expected dict for content={content!r}"
