"""Tests for per-worker settings re-declaration (bob3.dispatch.write_feature_settings).

Verifies that write_feature_settings writes a valid settings.json under
.bob3/features/<id>/settings.json with the correct permission structure.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bob3.dispatch import write_feature_settings


def _make_feature(
    *,
    id: str = "feat-settings-01",
    name: str = "Settings Feature",
) -> SimpleNamespace:
    return SimpleNamespace(id=id, name=name)


class TestWriteFeatureSettings:
    def test_creates_settings_file(self, tmp_path):
        feature = _make_feature(id="feat-ws-01")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        assert path.exists()

    def test_settings_file_at_correct_path(self, tmp_path):
        feature = _make_feature(id="feat-ws-02")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        expected = tmp_path / "features" / "feat-ws-02" / "settings.json"
        assert path == expected

    def test_settings_file_is_valid_json(self, tmp_path):
        feature = _make_feature(id="feat-ws-03")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert isinstance(data, dict)

    def test_settings_has_permissions_key(self, tmp_path):
        feature = _make_feature(id="feat-ws-04")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "permissions" in data

    def test_settings_has_allow_list(self, tmp_path):
        feature = _make_feature(id="feat-ws-05")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "allow" in data["permissions"]
        assert isinstance(data["permissions"]["allow"], list)

    def test_settings_allow_list_nonempty(self, tmp_path):
        feature = _make_feature(id="feat-ws-06")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert len(data["permissions"]["allow"]) > 0

    def test_settings_has_deny_list(self, tmp_path):
        feature = _make_feature(id="feat-ws-07")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "deny" in data["permissions"]

    def test_extra_allow_patterns_included(self, tmp_path):
        feature = _make_feature(id="feat-ws-08")
        extra = ["Bash(custom_tool*)"]
        path = write_feature_settings(feature, bob3_dir=tmp_path, extra_allow=extra)
        data = json.loads(path.read_text())
        assert "Bash(custom_tool*)" in data["permissions"]["allow"]

    def test_parent_dirs_created(self, tmp_path):
        feature = _make_feature(id="feat-ws-09")
        bob3_dir = tmp_path / "nonexistent" / ".bob3"
        path = write_feature_settings(feature, bob3_dir=bob3_dir)
        assert path.exists()

    def test_returns_path_object(self, tmp_path):
        feature = _make_feature(id="feat-ws-10")
        result = write_feature_settings(feature, bob3_dir=tmp_path)
        assert isinstance(result, Path)

    def test_default_permissions_include_bash_python(self, tmp_path):
        feature = _make_feature(id="feat-ws-11")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("python" in p.lower() for p in allow)

    def test_default_permissions_include_read(self, tmp_path):
        feature = _make_feature(id="feat-ws-12")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert any("Read" in p for p in allow)

    def test_overwrite_existing_file(self, tmp_path):
        feature = _make_feature(id="feat-ws-13")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        path.write_text('{"stale": true}')
        write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "permissions" in data
        assert "stale" not in data
