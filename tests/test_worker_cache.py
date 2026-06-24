"""Tests for bob.dispatch.spawn_worker_with_cache and related worker leverage helpers.

Feature baff13cd-486b-400b-8f2d-76955c255e32: Claude-Code worker leverage —
enable prompt cache, slim per-worker context, re-declare settings.

ACs tested:
  - Function defined: bob.dispatch.spawn_worker_with_cache
  - File exists: .bob/features/WORKER.md
  - File exists: .bob/features/<id>/settings.json
  - integration: bob.dispatch
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob.dispatch import (
    spawn_worker_with_cache,
    build_worker_md,
    write_feature_settings,
    emit_worker_cache_event,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_feature(
    *,
    id: str = "feat-001",
    name: str = "Test Feature",
    description: str = "A test feature",
    acceptance_criteria: str | None = '["File exists: foo.py"]',
    localization_shortlist: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        localization_shortlist=localization_shortlist or [],
        skip_repo_tree=False,
        skip_repro_test=False,
    )


# ── (A) emit_worker_cache_event ───────────────────────────────────────────────

class TestEmitWorkerCacheEvent:
    def test_returns_dict_with_event_key(self):
        event = emit_worker_cache_event(cache_read=1000, cache_write=500)
        assert event["event"] == "WORKER_CACHE_HIT"

    def test_includes_cache_read_and_write(self):
        event = emit_worker_cache_event(cache_read=1234, cache_write=567)
        assert event["cache_read"] == 1234
        assert event["cache_write"] == 567

    def test_optional_feature_id(self):
        event = emit_worker_cache_event(cache_read=0, cache_write=0, feature_id="feat-abc")
        assert event["feature_id"] == "feat-abc"

    def test_no_feature_id_key_when_absent(self):
        event = emit_worker_cache_event(cache_read=0, cache_write=0)
        assert "feature_id" not in event

    def test_zero_values_are_valid(self):
        event = emit_worker_cache_event(cache_read=0, cache_write=0)
        assert event["cache_read"] == 0
        assert event["cache_write"] == 0

    def test_logs_the_event(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger="bob.dispatch"):
            emit_worker_cache_event(cache_read=100, cache_write=50)
        assert any("WORKER_CACHE_HIT" in r.message for r in caplog.records)


# ── (B) build_worker_md ───────────────────────────────────────────────────────

class TestBuildWorkerMd:
    def test_contains_feature_title(self):
        feature = _make_feature(name="My Feature")
        md = build_worker_md(feature, workspace="/some/path")
        assert "My Feature" in md

    def test_contains_feature_description(self):
        feature = _make_feature(description="Some interesting description")
        md = build_worker_md(feature, workspace="/some/path")
        assert "Some interesting description" in md

    def test_contains_workspace(self):
        feature = _make_feature()
        md = build_worker_md(feature, workspace="/workspace/bob65")
        assert "/workspace/bob65" in md

    def test_contains_acceptance_criteria(self):
        feature = _make_feature(acceptance_criteria='["File exists: src/foo.py", "pytest: tests/test_foo.py"]')
        md = build_worker_md(feature, workspace="/some/path")
        assert "src/foo.py" in md

    def test_contains_localization_shortlist_when_provided(self):
        feature = _make_feature(localization_shortlist=["src/bob/foo.py", "src/bob/bar.py"])
        md = build_worker_md(feature, workspace="/some/path")
        assert "src/bob/foo.py" in md
        assert "src/bob/bar.py" in md

    def test_empty_localization_shortlist_does_not_crash(self):
        feature = _make_feature(localization_shortlist=[])
        md = build_worker_md(feature, workspace="/some/path")
        assert isinstance(md, str)

    def test_none_acceptance_criteria_does_not_crash(self):
        feature = _make_feature(acceptance_criteria=None)
        md = build_worker_md(feature, workspace="/some/path")
        assert isinstance(md, str)

    def test_returns_string(self):
        feature = _make_feature()
        result = build_worker_md(feature, workspace="/tmp")
        assert isinstance(result, str)
        assert len(result) > 0


# ── (C) write_feature_settings ───────────────────────────────────────────────

class TestWriteFeatureSettings:
    def test_creates_settings_json(self, tmp_path):
        feature = _make_feature(id="feat-xyz")
        settings_path = write_feature_settings(feature, bob_dir=tmp_path)
        assert settings_path.exists()

    def test_settings_json_is_valid_json(self, tmp_path):
        feature = _make_feature(id="feat-xyz")
        settings_path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(settings_path.read_text())
        assert isinstance(data, dict)

    def test_settings_json_path_under_feature_id_dir(self, tmp_path):
        feature = _make_feature(id="feat-abc")
        settings_path = write_feature_settings(feature, bob_dir=tmp_path)
        assert "feat-abc" in str(settings_path)
        assert settings_path.name == "settings.json"

    def test_settings_contain_permissions_allow(self, tmp_path):
        feature = _make_feature()
        settings_path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(settings_path.read_text())
        assert "permissions" in data
        assert "allow" in data["permissions"]

    def test_settings_allow_is_list(self, tmp_path):
        feature = _make_feature()
        settings_path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(settings_path.read_text())
        assert isinstance(data["permissions"]["allow"], list)

    def test_settings_directory_created_if_absent(self, tmp_path):
        feature = _make_feature(id="feat-new")
        # tmp_path/features/feat-new should not exist yet
        settings_path = write_feature_settings(feature, bob_dir=tmp_path)
        assert settings_path.parent.is_dir()

    def test_returns_path_object(self, tmp_path):
        feature = _make_feature()
        result = write_feature_settings(feature, bob_dir=tmp_path)
        assert isinstance(result, Path)


# ── (D) spawn_worker_with_cache ───────────────────────────────────────────────

class TestSpawnWorkerWithCache:
    """Tests for the main spawn_worker_with_cache entry-point."""

    def _make_call(self, tmp_path, feature=None, **kwargs):
        if feature is None:
            feature = _make_feature(id="feat-spawn-01")
        with mock.patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout='{"event":"WORKER_CACHE_HIT","cache_read":500,"cache_write":100}',
                stderr="",
            )
            result = spawn_worker_with_cache(
                feature=feature,
                prompt="Implement the feature.",
                workspace=str(tmp_path),
                bob_dir=tmp_path / ".bob",
                **kwargs,
            )
        return result, mock_run

    def test_returns_dict(self, tmp_path):
        result, _ = self._make_call(tmp_path)
        assert isinstance(result, dict)

    def test_result_has_returncode(self, tmp_path):
        result, _ = self._make_call(tmp_path)
        assert "returncode" in result

    def test_subprocess_called(self, tmp_path):
        _, mock_run = self._make_call(tmp_path)
        assert mock_run.called

    def test_claude_flag_in_command(self, tmp_path):
        _, mock_run = self._make_call(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert any("claude" in str(arg) for arg in cmd)

    def test_settings_flag_passed_to_claude(self, tmp_path):
        _, mock_run = self._make_call(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "--settings" in cmd

    def test_settings_file_created_before_spawn(self, tmp_path):
        feature = _make_feature(id="feat-spawn-02")
        with mock.patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
            spawn_worker_with_cache(
                feature=feature,
                prompt="Do the thing.",
                workspace=str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )
        settings_path = tmp_path / ".bob" / "features" / "feat-spawn-02" / "settings.json"
        assert settings_path.exists()

    def test_worker_md_created_before_spawn(self, tmp_path):
        feature = _make_feature(id="feat-spawn-03")
        with mock.patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
            spawn_worker_with_cache(
                feature=feature,
                prompt="Do the thing.",
                workspace=str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )
        worker_md = tmp_path / ".bob" / "features" / "WORKER.md"
        assert worker_md.exists()

    def test_prompt_caching_env_var_set(self, tmp_path):
        feature = _make_feature(id="feat-spawn-04")
        with mock.patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
            spawn_worker_with_cache(
                feature=feature,
                prompt="Do the thing.",
                workspace=str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )
        call_kwargs = mock_run.call_args[1]
        env = call_kwargs.get("env", {})
        assert env.get("ANTHROPIC_PROMPT_CACHING") == "1" or env.get("CLAUDE_PROMPT_CACHING") == "1"

    def test_result_contains_feature_id(self, tmp_path):
        feature = _make_feature(id="feat-result-check")
        with mock.patch("bob.dispatch.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
            result = spawn_worker_with_cache(
                feature=feature,
                prompt="Do the thing.",
                workspace=str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )
        assert result.get("feature_id") == "feat-result-check"


# ── Integration: bob.dispatch module surface ─────────────────────────────────

class TestBobDispatchIntegration:
    """Verify the integration AC: bob.dispatch exports all new symbols."""

    def test_spawn_worker_with_cache_importable(self):
        from bob.dispatch import spawn_worker_with_cache  # noqa: PLC0415
        assert callable(spawn_worker_with_cache)

    def test_build_worker_md_importable(self):
        from bob.dispatch import build_worker_md  # noqa: PLC0415
        assert callable(build_worker_md)

    def test_write_feature_settings_importable(self):
        from bob.dispatch import write_feature_settings  # noqa: PLC0415
        assert callable(write_feature_settings)

    def test_emit_worker_cache_event_importable(self):
        from bob.dispatch import emit_worker_cache_event  # noqa: PLC0415
        assert callable(emit_worker_cache_event)

    def test_spawn_worker_with_cache_in_all(self):
        import bob.dispatch as d  # noqa: PLC0415
        assert "spawn_worker_with_cache" in d.__all__

    def test_build_worker_md_in_all(self):
        import bob.dispatch as d  # noqa: PLC0415
        assert "build_worker_md" in d.__all__

    def test_write_feature_settings_in_all(self):
        import bob.dispatch as d  # noqa: PLC0415
        assert "write_feature_settings" in d.__all__

    def test_emit_worker_cache_event_in_all(self):
        import bob.dispatch as d  # noqa: PLC0415
        assert "emit_worker_cache_event" in d.__all__
