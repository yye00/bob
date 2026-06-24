"""Tests for prompt-cache enablement in bob.dispatch.spawn_worker.

Verifies that spawn_worker (and spawn_worker_with_cache) set ANTHROPIC_PROMPT_CACHING=1
and emit WORKER_CACHE_HIT telemetry events as per feature d6ee0f3a (F-R7-608).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob.dispatch import (
    emit_worker_cache_event,
    spawn_worker,
    spawn_worker_with_cache,
)


def _make_feature(
    *,
    id: str = "feat-cache-01",
    name: str = "Cache Test Feature",
    description: str = "Tests prompt caching",
    acceptance_criteria: str = '["File exists: foo.py"]',
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


class TestEmitWorkerCacheEvent:
    def test_returns_dict_with_event_key(self):
        result = emit_worker_cache_event(100, 200)
        assert result["event"] == "WORKER_CACHE_HIT"

    def test_cache_read_in_result(self):
        result = emit_worker_cache_event(100, 200)
        assert result["cache_read"] == 100

    def test_cache_write_in_result(self):
        result = emit_worker_cache_event(100, 200)
        assert result["cache_write"] == 200

    def test_feature_id_included_when_provided(self):
        result = emit_worker_cache_event(0, 0, feature_id="feat-xyz")
        assert result["feature_id"] == "feat-xyz"

    def test_feature_id_absent_when_not_provided(self):
        result = emit_worker_cache_event(0, 0)
        assert "feature_id" not in result

    def test_zero_values_allowed(self):
        result = emit_worker_cache_event(0, 0)
        assert result["cache_read"] == 0
        assert result["cache_write"] == 0


class TestSpawnWorkerPromptCache:
    def test_spawn_worker_sets_prompt_caching_env(self, tmp_path):
        feature = _make_feature(id="feat-env-01")
        captured_env = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_env.update(env)
            fake = mock.MagicMock()
            fake.returncode = 0
            fake.stdout = ""
            fake.stderr = ""
            return fake

        with mock.patch("subprocess.run", side_effect=fake_run):
            spawn_worker(
                feature,
                "do something",
                str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )

        assert captured_env.get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_spawn_worker_with_cache_sets_prompt_caching_env(self, tmp_path):
        feature = _make_feature(id="feat-env-02")
        captured_env = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_env.update(env)
            fake = mock.MagicMock()
            fake.returncode = 0
            fake.stdout = ""
            fake.stderr = ""
            return fake

        with mock.patch("subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature,
                "do something",
                str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )

        assert captured_env.get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_spawn_worker_emits_cache_event(self, tmp_path):
        feature = _make_feature(id="feat-event-01")

        worker_stdout = json.dumps({
            "event": "WORKER_CACHE_HIT",
            "cache_read": 5000,
            "cache_write": 1000,
        })

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            fake = mock.MagicMock()
            fake.returncode = 0
            fake.stdout = worker_stdout
            fake.stderr = ""
            return fake

        with mock.patch("subprocess.run", side_effect=fake_run):
            with mock.patch("bob.dispatch.emit_worker_cache_event") as mock_emit:
                mock_emit.return_value = {}
                spawn_worker(
                    feature,
                    "do something",
                    str(tmp_path),
                    bob_dir=tmp_path / ".bob",
                )
            mock_emit.assert_called_once()

    def test_spawn_worker_returns_feature_id(self, tmp_path):
        feature = _make_feature(id="feat-ret-01")

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            fake = mock.MagicMock()
            fake.returncode = 0
            fake.stdout = ""
            fake.stderr = ""
            return fake

        with mock.patch("subprocess.run", side_effect=fake_run):
            result = spawn_worker(
                feature,
                "do something",
                str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )

        assert result["feature_id"] == "feat-ret-01"

    def test_spawn_worker_passes_settings_flag(self, tmp_path):
        feature = _make_feature(id="feat-settings-01")
        captured_cmd = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_cmd.extend(cmd)
            fake = mock.MagicMock()
            fake.returncode = 0
            fake.stdout = ""
            fake.stderr = ""
            return fake

        with mock.patch("subprocess.run", side_effect=fake_run):
            spawn_worker(
                feature,
                "do something",
                str(tmp_path),
                bob_dir=tmp_path / ".bob",
            )

        assert "--settings" in captured_cmd

    def test_spawn_worker_raises_on_none_feature(self, tmp_path):
        with pytest.raises(ValueError):
            spawn_worker(None, "prompt", str(tmp_path), bob_dir=tmp_path / ".bob")
