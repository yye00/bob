"""Tests for per-worker settings redeclaration in bob3.dispatch.

Verifies that per-feature settings.json is written and passed via --settings
at dispatch time, ensuring workers do NOT rely on parent settings.json
inheritance (Claude Code issue #27661).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob3.dispatch import (
    write_feature_settings,
    spawn_worker_with_cache,
)


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-redecl-01",
        name="Settings Redeclaration Feature",
        description="Feature to test per-worker settings redeclaration",
        acceptance_criteria='["File exists: src/bob3/dispatch.py"]',
        localization_shortlist=[],
        estimated_files_touched=1,
        spec_quality_score=1.0,
        refinement_attempts=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestWriteFeatureSettingsRedeclaration:
    def test_settings_file_created_under_bob3_features(self, tmp_path):
        feature = _make_feature(id="feat-redecl-create-01")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        assert path.exists()
        assert str(path).startswith(str(tmp_path))

    def test_settings_file_contains_permissions(self, tmp_path):
        feature = _make_feature(id="feat-redecl-perms-01")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "permissions" in data

    def test_settings_file_has_allow_list(self, tmp_path):
        feature = _make_feature(id="feat-redecl-allow-01")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert isinstance(allow, list)
        assert len(allow) > 0

    def test_settings_file_has_deny_list(self, tmp_path):
        feature = _make_feature(id="feat-redecl-deny-01")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "deny" in data["permissions"]

    def test_extra_allow_patterns_merged_with_defaults(self, tmp_path):
        feature = _make_feature(id="feat-redecl-extra-01")
        path = write_feature_settings(
            feature, bob3_dir=tmp_path, extra_allow=["Read(tests/*)", "Bash(pytest*)"]
        )
        data = json.loads(path.read_text())
        allow = data["permissions"]["allow"]
        assert "Read(tests/*)" in allow
        assert "Bash(pytest*)" in allow

    def test_settings_written_per_feature_id(self, tmp_path):
        feat_a = _make_feature(id="feat-redecl-pa-01")
        feat_b = _make_feature(id="feat-redecl-pb-01")
        path_a = write_feature_settings(feat_a, bob3_dir=tmp_path)
        path_b = write_feature_settings(feat_b, bob3_dir=tmp_path)
        assert "feat-redecl-pa-01" in str(path_a)
        assert "feat-redecl-pb-01" in str(path_b)
        assert path_a != path_b

    def test_settings_json_is_valid_json(self, tmp_path):
        feature = _make_feature(id="feat-redecl-json-01")
        path = write_feature_settings(feature, bob3_dir=tmp_path)
        content = path.read_text()
        parsed = json.loads(content)
        assert isinstance(parsed, dict)


class TestSpawnWorkerWithCacheSettingsPath:
    def test_settings_flag_passed_to_subprocess(self, tmp_path):
        feature = _make_feature(id="feat-redecl-spawn-01")
        captured_cmd = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_cmd.extend(cmd)
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob3.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "run", tmp_path, bob3_dir=tmp_path / ".bob3"
            )

        assert "--settings" in captured_cmd

    def test_settings_path_points_to_existing_file(self, tmp_path):
        feature = _make_feature(id="feat-redecl-spawn-exists-01")
        captured_cmd = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_cmd.extend(cmd)
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob3.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "run", tmp_path, bob3_dir=tmp_path / ".bob3"
            )

        idx = captured_cmd.index("--settings")
        settings_path = Path(captured_cmd[idx + 1])
        assert settings_path.exists()

    def test_settings_file_has_valid_permissions(self, tmp_path):
        feature = _make_feature(id="feat-redecl-spawn-valid-01")
        written_settings_path = None

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            nonlocal written_settings_path
            if "--settings" in cmd:
                idx = cmd.index("--settings")
                written_settings_path = Path(cmd[idx + 1])
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob3.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "run", tmp_path, bob3_dir=tmp_path / ".bob3"
            )

        assert written_settings_path is not None
        data = json.loads(written_settings_path.read_text())
        assert "permissions" in data
        assert "allow" in data["permissions"]

    def test_independent_settings_per_worker_invocation(self, tmp_path):
        feat_a = _make_feature(id="feat-redecl-ind-a")
        feat_b = _make_feature(id="feat-redecl-ind-b")
        paths_seen = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            if "--settings" in cmd:
                idx = cmd.index("--settings")
                paths_seen.append(cmd[idx + 1])
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob3.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(feat_a, "run", tmp_path, bob3_dir=tmp_path / ".bob3")
            spawn_worker_with_cache(feat_b, "run", tmp_path, bob3_dir=tmp_path / ".bob3")

        assert len(paths_seen) == 2
        assert paths_seen[0] != paths_seen[1]
