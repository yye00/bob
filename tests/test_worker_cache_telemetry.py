"""Tests for worker cache telemetry in bob.dispatch.

Verifies:
- emit_worker_cache_event returns a well-formed WORKER_CACHE_HIT dict
- spawn_worker_with_cache sets ANTHROPIC_PROMPT_CACHING=1 in the worker env
- Cache telemetry is parsed from worker stdout and emitted
"""

from __future__ import annotations

import json
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
        name="Cache Test Feature",
        description="Feature for cache telemetry tests",
        acceptance_criteria='["File exists: src/bob/dispatch.py"]',
        localization_shortlist=[],
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestEmitWorkerCacheEvent:
    def test_returns_worker_cache_hit_event(self):
        result = emit_worker_cache_event(100, 200)
        assert result["event"] == "WORKER_CACHE_HIT"

    def test_cache_read_recorded(self):
        result = emit_worker_cache_event(42, 0)
        assert result["cache_read"] == 42

    def test_cache_write_recorded(self):
        result = emit_worker_cache_event(0, 99)
        assert result["cache_write"] == 99

    def test_feature_id_included_when_provided(self):
        result = emit_worker_cache_event(10, 20, feature_id="feat-123")
        assert result["feature_id"] == "feat-123"

    def test_feature_id_absent_when_not_provided(self):
        result = emit_worker_cache_event(10, 20)
        assert "feature_id" not in result

    def test_returns_dict(self):
        result = emit_worker_cache_event(0, 0)
        assert isinstance(result, dict)

    def test_both_zero_is_valid(self):
        result = emit_worker_cache_event(0, 0)
        assert result["cache_read"] == 0
        assert result["cache_write"] == 0

    def test_large_values_preserved(self):
        result = emit_worker_cache_event(1_000_000, 2_000_000)
        assert result["cache_read"] == 1_000_000
        assert result["cache_write"] == 2_000_000


class TestSpawnWorkerWithCacheEnv:
    def test_sets_anthropic_prompt_caching_env(self, tmp_path):
        feature = _make_feature()
        captured_env: dict = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured_env.update(env)
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "test prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert captured_env.get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_returns_feature_id_in_result(self, tmp_path):
        feature = _make_feature(id="feat-cache-return-01")

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            result = spawn_worker_with_cache(
                feature, "test prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert result["feature_id"] == "feat-cache-return-01"

    def test_returns_returncode(self, tmp_path):
        feature = _make_feature()

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            result = spawn_worker_with_cache(
                feature, "test prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert "returncode" in result

    def test_cache_telemetry_parsed_from_stdout(self, tmp_path):
        feature = _make_feature(id="feat-cache-parse-01")
        cache_event = json.dumps(
            {"event": "WORKER_CACHE_HIT", "cache_read": 7500, "cache_write": 1000}
        )

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = f"some output\n{cache_event}\nmore output"
            m.stderr = ""
            return m

        emitted_events = []
        original_emit = __import__("bob.dispatch", fromlist=["emit_worker_cache_event"]).emit_worker_cache_event

        def capturing_emit(cache_read, cache_write, *, feature_id=None):
            result = original_emit(cache_read, cache_write, feature_id=feature_id)
            emitted_events.append(result)
            return result

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            with mock.patch("bob.dispatch.emit_worker_cache_event", side_effect=capturing_emit):
                spawn_worker_with_cache(
                    feature, "test prompt", tmp_path, bob_dir=tmp_path / ".bob"
                )

        assert len(emitted_events) == 1
        assert emitted_events[0]["cache_read"] == 7500
        assert emitted_events[0]["cache_write"] == 1000

    def test_extra_env_merged(self, tmp_path):
        feature = _make_feature()
        captured_env: dict = {}

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
                "test prompt",
                tmp_path,
                bob_dir=tmp_path / ".bob",
                env={"MY_CUSTOM_VAR": "hello"},
            )

        assert captured_env.get("MY_CUSTOM_VAR") == "hello"
        # Prompt caching must still be set alongside custom env
        assert captured_env.get("ANTHROPIC_PROMPT_CACHING") == "1"
