"""Tests for spec_versioning module.

Covers:
- version_spec(spec_dict) -> SHA-256 of canonical YAML
- diff_specs(old, new) -> SpecDiff dataclass
- spec_version recorded in telemetry lines
- spec_version_changed event emission
- BOB_ABORT_ON_SPEC_CHANGE controls abort behavior
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# version_spec
# ---------------------------------------------------------------------------


class TestVersionSpec:
    """version_spec(spec_dict) returns SHA-256 of canonical YAML."""

    def test_returns_64_char_hex_string(self):
        from bob.spec_versioning import version_spec

        result = version_spec({"name": "test", "features": []})
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_dict_same_hash(self):
        from bob.spec_versioning import version_spec

        spec = {"name": "hello", "features": [{"name": "A"}]}
        assert version_spec(spec) == version_spec(spec)

    def test_equal_dicts_different_insertion_order_same_hash(self):
        """Canonical serialization must be order-independent."""
        from bob.spec_versioning import version_spec

        spec_a = {"b": 2, "a": 1}
        spec_b = {"a": 1, "b": 2}
        assert version_spec(spec_a) == version_spec(spec_b)

    def test_different_dicts_different_hash(self):
        from bob.spec_versioning import version_spec

        spec_a = {"name": "Alpha"}
        spec_b = {"name": "Beta"}
        assert version_spec(spec_a) != version_spec(spec_b)

    def test_nested_dicts_canonical_order(self):
        """Nested keys must also be sorted."""
        from bob.spec_versioning import version_spec

        spec_a = {"features": [{"b": 2, "a": 1}]}
        spec_b = {"features": [{"a": 1, "b": 2}]}
        assert version_spec(spec_a) == version_spec(spec_b)

    def test_empty_dict(self):
        from bob.spec_versioning import version_spec

        result = version_spec({})
        expected = hashlib.sha256(yaml.dump({}, sort_keys=True).encode()).hexdigest()
        assert result == expected

    def test_hash_matches_sha256_of_canonical_yaml(self):
        """The hash must be exactly SHA-256 of yaml.dump(spec, sort_keys=True)."""
        from bob.spec_versioning import version_spec

        spec = {"z": "last", "a": "first", "m": [1, 2, 3]}
        canonical = yaml.dump(spec, sort_keys=True)
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        assert version_spec(spec) == expected


# ---------------------------------------------------------------------------
# SpecDiff
# ---------------------------------------------------------------------------


class TestSpecDiff:
    """SpecDiff is a dataclass with added/removed/modified lists."""

    def test_spec_diff_has_expected_fields(self):
        from bob.spec_versioning import SpecDiff

        diff = SpecDiff(added=[], removed=[], modified=[])
        assert hasattr(diff, "added")
        assert hasattr(diff, "removed")
        assert hasattr(diff, "modified")

    def test_spec_diff_is_dataclass_or_pydantic(self):
        from bob.spec_versioning import SpecDiff

        diff = SpecDiff(added=["x"], removed=["y"], modified=["z"])
        assert diff.added == ["x"]
        assert diff.removed == ["y"]
        assert diff.modified == ["z"]


# ---------------------------------------------------------------------------
# diff_specs
# ---------------------------------------------------------------------------


class TestDiffSpecs:
    """diff_specs(old, new) -> SpecDiff showing what changed."""

    def test_no_change_returns_empty_diff(self):
        from bob.spec_versioning import diff_specs

        spec = {"name": "test", "features": [{"name": "A"}]}
        result = diff_specs(spec, spec)
        assert result.added == []
        assert result.removed == []
        assert result.modified == []

    def test_top_level_key_added(self):
        from bob.spec_versioning import diff_specs

        old = {"name": "test"}
        new = {"name": "test", "version": "2.0"}
        result = diff_specs(old, new)
        assert "version" in result.added

    def test_top_level_key_removed(self):
        from bob.spec_versioning import diff_specs

        old = {"name": "test", "version": "1.0"}
        new = {"name": "test"}
        result = diff_specs(old, new)
        assert "version" in result.removed

    def test_top_level_key_value_changed(self):
        from bob.spec_versioning import diff_specs

        old = {"name": "Alpha"}
        new = {"name": "Beta"}
        result = diff_specs(old, new)
        assert "name" in result.modified

    def test_deeply_nested_change_detected(self):
        from bob.spec_versioning import diff_specs

        old = {"features": [{"name": "A", "description": "old"}]}
        new = {"features": [{"name": "A", "description": "new"}]}
        result = diff_specs(old, new)
        assert "features" in result.modified

    def test_both_empty_dicts_no_diff(self):
        from bob.spec_versioning import diff_specs

        result = diff_specs({}, {})
        assert result.added == []
        assert result.removed == []
        assert result.modified == []

    def test_returns_spec_diff_instance(self):
        from bob.spec_versioning import SpecDiff, diff_specs

        result = diff_specs({"a": 1}, {"a": 2})
        assert isinstance(result, SpecDiff)


# ---------------------------------------------------------------------------
# spec_version in telemetry
# ---------------------------------------------------------------------------


class TestSpecVersionInTelemetry:
    """emit_telemetry_line accepts spec_version and writes it to the record."""

    def test_spec_version_field_in_schema_defaults(self):
        """The telemetry schema must include spec_version."""
        from bob.telemetry import _SCHEMA_DEFAULTS

        assert "spec_version" in _SCHEMA_DEFAULTS

    def test_emit_telemetry_writes_spec_version(self, tmp_path, monkeypatch):
        import json

        from bob.telemetry import emit_telemetry_line, get_run_jsonl_path

        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        monkeypatch.chdir(tmp_path)

        emit_telemetry_line("run-001", spec_version="abc123")

        records = [json.loads(line) for line in run_jsonl.read_text().splitlines()]
        assert len(records) == 1
        assert records[0]["spec_version"] == "abc123"

    def test_emit_telemetry_spec_version_null_by_default(self, tmp_path, monkeypatch):
        import json

        from bob.telemetry import emit_telemetry_line

        run_jsonl = tmp_path / ".bob" / "run.jsonl"
        monkeypatch.chdir(tmp_path)

        emit_telemetry_line("run-002")

        records = [json.loads(line) for line in run_jsonl.read_text().splitlines()]
        assert records[0]["spec_version"] is None


# ---------------------------------------------------------------------------
# watch_spec_file / spec_version_changed event
# ---------------------------------------------------------------------------


class TestWatchSpecFile:
    """watch_spec_file(spec_path, run_id) emits spec_version_changed when the file changes."""

    def test_no_event_when_file_unchanged(self, tmp_path):
        """If the file hasn't changed, no spec_version_changed event is emitted."""
        from bob.spec_versioning import watch_spec_file

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(yaml.dump({"name": "stable"}))

        events = []
        watch_spec_file(
            spec_path=spec_path,
            run_id="run-stable",
            on_change=lambda ev: events.append(ev),
        )
        assert events == []

    def test_event_emitted_when_file_changes(self, tmp_path):
        """After file changes, calling watch_spec_file emits spec_version_changed."""
        from bob.spec_versioning import watch_spec_file

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(yaml.dump({"name": "original"}))

        events = []

        # First call: establish baseline
        watch_spec_file(
            spec_path=spec_path,
            run_id="run-change",
            on_change=lambda ev: events.append(ev),
        )
        assert events == []

        # Mutate file
        spec_path.write_text(yaml.dump({"name": "modified"}))

        # Second call: should detect change
        watch_spec_file(
            spec_path=spec_path,
            run_id="run-change",
            on_change=lambda ev: events.append(ev),
        )
        assert len(events) == 1
        assert events[0]["event"] == "spec_version_changed"
        assert "old_version" in events[0]
        assert "new_version" in events[0]

    def test_event_contains_correct_versions(self, tmp_path):
        from bob.spec_versioning import version_spec, watch_spec_file

        spec_a = {"name": "version-a"}
        spec_b = {"name": "version-b"}
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(yaml.dump(spec_a))

        events = []
        watch_spec_file(spec_path=spec_path, run_id="r", on_change=lambda ev: events.append(ev))
        spec_path.write_text(yaml.dump(spec_b))
        watch_spec_file(spec_path=spec_path, run_id="r", on_change=lambda ev: events.append(ev))

        assert len(events) == 1
        assert events[0]["old_version"] == version_spec(spec_a)
        assert events[0]["new_version"] == version_spec(spec_b)


# ---------------------------------------------------------------------------
# BOB_ABORT_ON_SPEC_CHANGE
# ---------------------------------------------------------------------------


class TestAbortOnSpecChange:
    """check_spec_change_abort raises SpecChangedAbort when BOB_ABORT_ON_SPEC_CHANGE=True."""

    def test_raises_when_abort_enabled_and_spec_changed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BOB_ABORT_ON_SPEC_CHANGE", "true")
        from bob.spec_versioning import SpecChangedAbort, check_spec_change_abort

        with pytest.raises(SpecChangedAbort):
            check_spec_change_abort(old_version="abc", new_version="xyz")

    def test_no_raise_when_abort_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BOB_ABORT_ON_SPEC_CHANGE", "false")
        from bob.spec_versioning import check_spec_change_abort

        # Should not raise
        check_spec_change_abort(old_version="abc", new_version="xyz")

    def test_no_raise_when_versions_equal(self, monkeypatch):
        monkeypatch.setenv("BOB_ABORT_ON_SPEC_CHANGE", "true")
        from bob.spec_versioning import check_spec_change_abort

        # Same version — no change, so no abort
        check_spec_change_abort(old_version="abc", new_version="abc")

    def test_default_is_abort_true(self, monkeypatch):
        """When BOB_ABORT_ON_SPEC_CHANGE is unset, default is True (abort)."""
        monkeypatch.delenv("BOB_ABORT_ON_SPEC_CHANGE", raising=False)
        from bob.spec_versioning import SpecChangedAbort, check_spec_change_abort

        with pytest.raises(SpecChangedAbort):
            check_spec_change_abort(old_version="aaa", new_version="bbb")

    def test_spec_changed_abort_is_exception(self):
        from bob.spec_versioning import SpecChangedAbort

        assert issubclass(SpecChangedAbort, Exception)

    def test_abort_message_contains_versions(self, monkeypatch):
        monkeypatch.setenv("BOB_ABORT_ON_SPEC_CHANGE", "true")
        from bob.spec_versioning import SpecChangedAbort, check_spec_change_abort

        with pytest.raises(SpecChangedAbort) as exc_info:
            check_spec_change_abort(old_version="old_hash_val", new_version="new_hash_val")
        assert "old_hash_val" in str(exc_info.value)
        assert "new_hash_val" in str(exc_info.value)
