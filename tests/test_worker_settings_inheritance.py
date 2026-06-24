"""Tests for per-worker settings.json generation in bob.dispatch.

Verifies:
- write_feature_settings creates settings.json with correct permissions
- spawn_worker_with_cache passes --settings to the worker subprocess
- Extra allow patterns are merged with defaults
- Settings file is created under .bob/features/<feature_id>/settings.json
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob.dispatch import (
    write_feature_settings,
    spawn_worker_with_cache,
)


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-settings-01",
        name="Settings Test Feature",
        description="Feature for settings inheritance tests",
        acceptance_criteria='["File exists: src/bob/dispatch.py"]',
        localization_shortlist=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestWriteFeatureSettings:
    def test_creates_settings_file(self, tmp_path):
        feature = _make_feature(id="feat-s-create-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert path.exists()

    def test_settings_file_under_feature_id_dir(self, tmp_path):
        feature = _make_feature(id="feat-s-path-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert "feat-s-path-01" in str(path)

    def test_settings_json_has_permissions_key(self, tmp_path):
        feature = _make_feature(id="feat-s-perms-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "permissions" in data

    def test_settings_json_has_allow_list(self, tmp_path):
        feature = _make_feature(id="feat-s-allow-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "allow" in data["permissions"]
        assert isinstance(data["permissions"]["allow"], list)

    def test_default_permissions_non_empty(self, tmp_path):
        feature = _make_feature(id="feat-s-default-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        # Default permissions must contain at least Read, Write, Edit
        allow = data["permissions"]["allow"]
        assert len(allow) > 0

    def test_extra_allow_appended(self, tmp_path):
        feature = _make_feature(id="feat-s-extra-01")
        path = write_feature_settings(
            feature, bob_dir=tmp_path, extra_allow=["Bash(npm:*)"]
        )
        data = json.loads(path.read_text())
        assert "Bash(npm:*)" in data["permissions"]["allow"]

    def test_extra_allow_added_to_defaults_not_replace(self, tmp_path):
        feature = _make_feature(id="feat-s-extra-02")
        path = write_feature_settings(
            feature, bob_dir=tmp_path, extra_allow=["Bash(make:*)"]
        )
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert "Bash(make:*)" in allow
        # Default entries must still be present
        assert len(allow) > 1

    def test_multiple_extra_allow_all_present(self, tmp_path):
        feature = _make_feature(id="feat-s-extra-03")
        extra = ["Bash(pytest:*)", "Bash(git:*)"]
        path = write_feature_settings(feature, bob_dir=tmp_path, extra_allow=extra)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        for pattern in extra:
            assert pattern in allow

    def test_settings_file_is_valid_json(self, tmp_path):
        feature = _make_feature(id="feat-s-json-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        # Should not raise
        data = json.loads(path.read_text())
        assert data

    def test_settings_dir_created_if_missing(self, tmp_path):
        bob_dir = tmp_path / ".bob"
        # Do not pre-create the directory
        feature = _make_feature(id="feat-s-mkdir-01")
        path = write_feature_settings(feature, bob_dir=bob_dir)
        assert path.exists()

    def test_different_features_get_different_paths(self, tmp_path):
        f1 = _make_feature(id="feat-s-diff-01")
        f2 = _make_feature(id="feat-s-diff-02")
        path1 = write_feature_settings(f1, bob_dir=tmp_path)
        path2 = write_feature_settings(f2, bob_dir=tmp_path)
        assert path1 != path2


class TestSpawnWorkerWithCacheSettingsFlag:
    def test_settings_flag_passed_to_subprocess(self, tmp_path):
        feature = _make_feature(id="feat-spawn-settings-01")
        captured_cmd: list = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_cmd.extend(cmd)
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "test prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert "--settings" in captured_cmd

    def test_settings_path_exists_when_passed(self, tmp_path):
        feature = _make_feature(id="feat-spawn-settings-02")
        settings_path_used: list = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            if "--settings" in cmd:
                idx = cmd.index("--settings")
                settings_path_used.append(cmd[idx + 1])
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "test prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert len(settings_path_used) == 1
        assert Path(settings_path_used[0]).exists()

    def test_worker_md_written_before_subprocess(self, tmp_path):
        feature = _make_feature(id="feat-spawn-md-01")
        bob_dir = tmp_path / ".bob"
        worker_md_found: list = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            # Check that WORKER.md was written by the time subprocess.run is called
            md_path = bob_dir / "features" / "WORKER.md"
            worker_md_found.append(md_path.exists())
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "test prompt", tmp_path, bob_dir=bob_dir
            )

        assert worker_md_found == [True]

    def test_extra_allow_forwarded_to_settings(self, tmp_path):
        feature = _make_feature(id="feat-spawn-extra-01")
        settings_paths: list = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            if "--settings" in cmd:
                idx = cmd.index("--settings")
                settings_paths.append(cmd[idx + 1])
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature,
                "test prompt",
                tmp_path,
                bob_dir=tmp_path / ".bob",
                extra_allow=["Bash(make:*)"],
            )

        assert len(settings_paths) == 1
        data = json.loads(Path(settings_paths[0]).read_text())
        assert "Bash(make:*)" in data["permissions"]["allow"]
