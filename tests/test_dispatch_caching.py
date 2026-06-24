"""Tests for prompt-cache worker leverage in bob3.dispatch.

AC: pytest: tests/test_dispatch_caching.py

Tests coverage:
  - emit_worker_cache_event returns correct event dict structure
  - enable_worker_prompt_cache sets ANTHROPIC_PROMPT_CACHING=1
  - spawn_worker sets the cache env var for every worker invocation
  - Telemetry event includes cache_read, cache_write, and optionally feature_id
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest import mock

import pytest

from bob3.dispatch import (
    emit_worker_cache_event,
    enable_worker_prompt_cache,
    spawn_worker,
)


def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-cache-01",
        name="Caching Feature",
        description="Tests prompt-cache telemetry.",
        acceptance_criteria='["pytest: tests/test_dispatch_caching.py"]',
        localization_shortlist=[],
        skip_repo_tree=False,
        skip_repro_test=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestEmitWorkerCacheEvent:
    def test_returns_dict(self):
        result = emit_worker_cache_event(10, 20)
        assert isinstance(result, dict)

    def test_event_key_is_worker_cache_hit(self):
        result = emit_worker_cache_event(10, 20)
        assert result["event"] == "WORKER_CACHE_HIT"

    def test_cache_read_in_result(self):
        result = emit_worker_cache_event(100, 0)
        assert result["cache_read"] == 100

    def test_cache_write_in_result(self):
        result = emit_worker_cache_event(0, 200)
        assert result["cache_write"] == 200

    def test_feature_id_included_when_provided(self):
        result = emit_worker_cache_event(5, 10, feature_id="feat-abc")
        assert result["feature_id"] == "feat-abc"

    def test_feature_id_absent_when_not_provided(self):
        result = emit_worker_cache_event(5, 10)
        assert "feature_id" not in result

    def test_event_is_json_serialisable(self):
        result = emit_worker_cache_event(42, 99, feature_id="feat-xyz")
        serialised = json.dumps(result)
        parsed = json.loads(serialised)
        assert parsed["event"] == "WORKER_CACHE_HIT"
        assert parsed["cache_read"] == 42
        assert parsed["cache_write"] == 99

    def test_zero_values_do_not_raise(self):
        result = emit_worker_cache_event(0, 0)
        assert result["cache_read"] == 0
        assert result["cache_write"] == 0

    def test_large_values_preserved(self):
        large = 10**8
        result = emit_worker_cache_event(large, large)
        assert result["cache_read"] == large
        assert result["cache_write"] == large


class TestEnableWorkerPromptCache:
    def test_returns_dict(self):
        result = enable_worker_prompt_cache()
        assert isinstance(result, dict)

    def test_sets_anthropic_prompt_caching(self):
        result = enable_worker_prompt_cache()
        assert result.get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_merges_with_existing_env(self):
        base = {"MY_VAR": "hello", "OTHER": "world"}
        result = enable_worker_prompt_cache(base)
        assert result["MY_VAR"] == "hello"
        assert result["OTHER"] == "world"
        assert result["ANTHROPIC_PROMPT_CACHING"] == "1"

    def test_none_env_produces_cache_var(self):
        result = enable_worker_prompt_cache(None)
        assert result["ANTHROPIC_PROMPT_CACHING"] == "1"

    def test_does_not_mutate_input_dict(self):
        base = {"EXISTING": "value"}
        enable_worker_prompt_cache(base)
        assert "ANTHROPIC_PROMPT_CACHING" not in base

    def test_existing_prompt_caching_var_is_overwritten(self):
        base = {"ANTHROPIC_PROMPT_CACHING": "0"}
        result = enable_worker_prompt_cache(base)
        assert result["ANTHROPIC_PROMPT_CACHING"] == "1"


class TestSpawnWorkerCacheIntegration:
    """spawn_worker must pass ANTHROPIC_PROMPT_CACHING=1 to the worker process."""

    def test_spawn_worker_passes_cache_env_var(self, tmp_path):
        """spawn_worker should set ANTHROPIC_PROMPT_CACHING in subprocess env."""
        feature = _make_feature()
        bob3_dir = tmp_path / ".bob3"
        bob3_dir.mkdir()

        captured_env: dict[str, str] = {}

        def fake_run(cmd, **kwargs):
            captured_env.update(kwargs.get("env") or {})
            result = mock.MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with mock.patch("subprocess.run", side_effect=fake_run):
            spawn_worker(feature, "do something", tmp_path, bob3_dir=bob3_dir)

        assert captured_env.get("ANTHROPIC_PROMPT_CACHING") == "1", (
            "spawn_worker must set ANTHROPIC_PROMPT_CACHING=1 in the worker env "
            "(addresses Issue #29966 — prompt caching disabled by default in sub-agents)"
        )

    def test_spawn_worker_none_feature_raises_value_error(self, tmp_path):
        bob3_dir = tmp_path / ".bob3"
        with pytest.raises(ValueError):
            spawn_worker(None, "prompt", tmp_path, bob3_dir=bob3_dir)
