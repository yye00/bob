"""Tests for worker prompt-cache enablement in bob.dispatch.

Verifies:
- spawn_worker_with_cache sets ANTHROPIC_PROMPT_CACHING=1 in the worker env
- emit_worker_cache_event produces correct WORKER_CACHE_HIT telemetry
- Cache telemetry is parsed from worker stdout and emitted at worker exit
- spawn_worker_with_cache passes --settings to subprocess
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob.dispatch import (
    emit_worker_cache_event,
    spawn_worker_with_cache,
)


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-cache-01",
        name="Prompt Cache Feature",
        description="Feature to test prompt cache enablement",
        acceptance_criteria='["File exists: src/bob/dispatch.py"]',
        localization_shortlist=[],
        estimated_files_touched=1,
        spec_quality_score=1.0,
        refinement_attempts=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _fake_run_factory(returncode: int = 0, stdout: str = "", stderr: str = ""):
    def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
        m = mock.MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    return fake_run


class TestEmitWorkerCacheEvent:
    def test_returns_correct_event_type(self):
        event = emit_worker_cache_event(100, 200)
        assert event["event"] == "WORKER_CACHE_HIT"

    def test_cache_read_in_result(self):
        event = emit_worker_cache_event(100, 200)
        assert event["cache_read"] == 100

    def test_cache_write_in_result(self):
        event = emit_worker_cache_event(100, 200)
        assert event["cache_write"] == 200

    def test_feature_id_included_when_provided(self):
        event = emit_worker_cache_event(50, 75, feature_id="feat-abc")
        assert event["feature_id"] == "feat-abc"

    def test_no_feature_id_when_not_provided(self):
        event = emit_worker_cache_event(50, 75)
        assert "feature_id" not in event

    def test_returns_dict(self):
        event = emit_worker_cache_event(0, 0)
        assert isinstance(event, dict)


class TestSpawnWorkerWithCacheEnv:
    def test_sets_anthropic_prompt_caching_env(self, tmp_path):
        feature = _make_feature(id="feat-cache-env-01")
        captured_env = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_env.update(env)
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "do stuff", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert captured_env.get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_passes_settings_flag_to_subprocess(self, tmp_path):
        feature = _make_feature(id="feat-cache-settings-01")
        captured_cmd = []

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_cmd.extend(cmd)
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "do stuff", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert "--settings" in captured_cmd

    def test_returns_dict_with_returncode(self, tmp_path):
        feature = _make_feature(id="feat-cache-ret-01")

        with mock.patch("bob.dispatch.subprocess.run", side_effect=_fake_run_factory(0)):
            result = spawn_worker_with_cache(
                feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert "returncode" in result
        assert result["returncode"] == 0

    def test_returns_feature_id_in_result(self, tmp_path):
        feature = _make_feature(id="feat-cache-id-01")

        with mock.patch("bob.dispatch.subprocess.run", side_effect=_fake_run_factory(0)):
            result = spawn_worker_with_cache(
                feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert result["feature_id"] == "feat-cache-id-01"

    def test_emits_cache_event_after_worker(self, tmp_path):
        feature = _make_feature(id="feat-cache-emit-01")
        cache_stdout = json.dumps({"event": "WORKER_CACHE_HIT", "cache_read": 500, "cache_write": 1000})

        emitted_events = []

        real_emit = None

        def fake_emit(cache_read, cache_write, *, feature_id=None):
            emitted_events.append({"cache_read": cache_read, "cache_write": cache_write, "feature_id": feature_id})
            return {"event": "WORKER_CACHE_HIT", "cache_read": cache_read, "cache_write": cache_write}

        with mock.patch("bob.dispatch.subprocess.run", side_effect=_fake_run_factory(0, stdout=cache_stdout)):
            with mock.patch("bob.dispatch.emit_worker_cache_event", side_effect=fake_emit):
                spawn_worker_with_cache(
                    feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
                )

        assert len(emitted_events) == 1
        assert emitted_events[0]["cache_read"] == 500
        assert emitted_events[0]["cache_write"] == 1000

    def test_extra_env_vars_merged(self, tmp_path):
        feature = _make_feature(id="feat-cache-extra-env-01")
        captured_env = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_env.update(env)
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature,
                "prompt",
                tmp_path,
                bob_dir=tmp_path / ".bob",
                env={"MY_CUSTOM_VAR": "hello"},
            )

        assert captured_env.get("MY_CUSTOM_VAR") == "hello"
        assert captured_env.get("ANTHROPIC_PROMPT_CACHING") == "1"
