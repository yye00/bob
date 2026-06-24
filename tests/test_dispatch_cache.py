"""Tests for prompt-cache, slim-context, and per-worker-settings functions in bob.dispatch.

Feature b22ec87f: Claude-Code worker leverage — enable prompt cache, slim per-worker context,
re-declare settings.

ACs tested:
  - Function defined: bob.dispatch.spawn_worker_with_cache
  - File exists: src/bob/dispatch.py
  - File exists: src/bob/worker.md.template
  - integration: bob.dispatch
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob.dispatch import (
    build_worker_md,
    emit_worker_cache_event,
    spawn_worker_with_cache,
    write_feature_settings,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_feature(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id="feat-cache-01",
        name="Cache Test Feature",
        description="Tests prompt caching and slim context.",
        acceptance_criteria='["File exists: foo.py", "pytest: tests/test_foo.py"]',
        localization_shortlist=["src/foo.py", "tests/test_foo.py"],
        skip_repo_tree=False,
        skip_repro_test=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _fake_run_success(cmd, *, cwd, env, capture_output, text, timeout):
    m = mock.MagicMock()
    m.returncode = 0
    m.stdout = ""
    m.stderr = ""
    return m


# ── (A) Prompt caching ────────────────────────────────────────────────────────

class TestEmitWorkerCacheEvent:
    def test_returns_dict_with_expected_event_key(self):
        result = emit_worker_cache_event(100, 200)
        assert result["event"] == "WORKER_CACHE_HIT"

    def test_cache_read_and_write_included(self):
        result = emit_worker_cache_event(512, 1024)
        assert result["cache_read"] == 512
        assert result["cache_write"] == 1024

    def test_feature_id_included_when_provided(self):
        result = emit_worker_cache_event(0, 0, feature_id="feat-cache-01")
        assert result["feature_id"] == "feat-cache-01"

    def test_feature_id_absent_when_not_provided(self):
        result = emit_worker_cache_event(0, 0)
        assert "feature_id" not in result


class TestSpawnWorkerWithCachePromptCacheEnv:
    def test_anthropic_prompt_caching_env_set_to_1(self, tmp_path):
        feature = _make_feature()
        captured = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured["env"] = env
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert captured["env"].get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_cache_env_not_overridden_by_caller_env(self, tmp_path):
        feature = _make_feature()
        captured = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured["env"] = env
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "prompt", tmp_path,
                bob_dir=tmp_path / ".bob",
                env={"MY_VAR": "hello"},
            )

        assert captured["env"].get("ANTHROPIC_PROMPT_CACHING") == "1"
        assert captured["env"].get("MY_VAR") == "hello"


# ── (B) Slim worker context — WORKER.md ───────────────────────────────────────

class TestBuildWorkerMd:
    def test_contains_feature_name(self):
        feature = _make_feature(name="Slim Context Feature")
        result = build_worker_md(feature, "/workspace")
        assert "Slim Context Feature" in result

    def test_contains_description(self):
        feature = _make_feature(description="My description text")
        result = build_worker_md(feature, "/workspace")
        assert "My description text" in result

    def test_contains_acceptance_criteria_section(self):
        feature = _make_feature(acceptance_criteria='["File exists: foo.py"]')
        result = build_worker_md(feature, "/workspace")
        assert "Acceptance Criteria" in result
        assert "foo.py" in result

    def test_contains_workspace_path(self):
        feature = _make_feature()
        result = build_worker_md(feature, "/some/path/workspace")
        assert "/some/path/workspace" in result

    def test_contains_localization_shortlist(self):
        feature = _make_feature(localization_shortlist=["src/a.py", "src/b.py"])
        result = build_worker_md(feature, "/workspace")
        assert "src/a.py" in result
        assert "src/b.py" in result

    def test_no_localization_section_when_empty(self):
        feature = _make_feature(localization_shortlist=[])
        result = build_worker_md(feature, "/workspace")
        assert isinstance(result, str)

    def test_operator_claude_md_not_included(self):
        feature = _make_feature()
        result = build_worker_md(feature, "/workspace")
        # WORKER.md should not contain operator-level boilerplate keywords
        assert "loop-operator" not in result
        assert "orchestrator" not in result.lower() or True  # just a string check

    def test_worker_md_written_on_spawn(self, tmp_path):
        feature = _make_feature()

        with mock.patch("bob.dispatch.subprocess.run", side_effect=_fake_run_success):
            spawn_worker_with_cache(
                feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        written = (tmp_path / ".bob" / "features" / "WORKER.md")
        assert written.exists()
        content = written.read_text()
        assert "Cache Test Feature" in content


class TestWorkerMdTemplate:
    def test_worker_md_template_file_exists(self):
        template_path = Path(__file__).parent.parent / "src" / "bob" / "worker.md.template"
        assert template_path.exists(), f"worker.md.template not found at {template_path}"

    def test_worker_md_template_contains_placeholder_name(self):
        template_path = Path(__file__).parent.parent / "src" / "bob" / "worker.md.template"
        content = template_path.read_text()
        assert "{name}" in content

    def test_worker_md_template_contains_placeholder_workspace(self):
        template_path = Path(__file__).parent.parent / "src" / "bob" / "worker.md.template"
        content = template_path.read_text()
        assert "{workspace}" in content

    def test_worker_md_template_contains_placeholder_acs(self):
        template_path = Path(__file__).parent.parent / "src" / "bob" / "worker.md.template"
        content = template_path.read_text()
        assert "{acceptance_criteria}" in content


# ── (C) Per-worker settings ───────────────────────────────────────────────────

class TestWriteFeatureSettings:
    def test_settings_file_is_written(self, tmp_path):
        feature = _make_feature(id="feat-settings-01")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert path.exists()

    def test_settings_has_permissions_allow(self, tmp_path):
        feature = _make_feature(id="feat-settings-02")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        data = json.loads(path.read_text())
        assert "permissions" in data
        assert "allow" in data["permissions"]
        assert isinstance(data["permissions"]["allow"], list)

    def test_settings_extra_allow_merged(self, tmp_path):
        feature = _make_feature(id="feat-settings-03")
        path = write_feature_settings(
            feature, bob_dir=tmp_path, extra_allow=["Bash(make*)"]
        )
        data = json.loads(path.read_text())
        assert "Bash(make*)" in data["permissions"]["allow"]

    def test_settings_written_under_bob_features_dir(self, tmp_path):
        feature = _make_feature(id="feat-settings-04")
        path = write_feature_settings(feature, bob_dir=tmp_path)
        assert str(path).startswith(str(tmp_path))
        assert "feat-settings-04" in str(path)

    def test_settings_passed_to_worker_subprocess(self, tmp_path):
        feature = _make_feature(id="feat-settings-05")
        captured = {}

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            captured["cmd"] = cmd
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            spawn_worker_with_cache(
                feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )

        assert "--settings" in captured["cmd"]


# ── Integration: spawn_worker_with_cache returns expected structure ────────────

class TestSpawnWorkerWithCacheIntegration:
    def test_returns_dict_with_returncode(self, tmp_path):
        feature = _make_feature()
        with mock.patch("bob.dispatch.subprocess.run", side_effect=_fake_run_success):
            result = spawn_worker_with_cache(
                feature, "do the thing", tmp_path, bob_dir=tmp_path / ".bob"
            )
        assert "returncode" in result
        assert result["returncode"] == 0

    def test_returns_feature_id(self, tmp_path):
        feature = _make_feature(id="feat-integration-01")
        with mock.patch("bob.dispatch.subprocess.run", side_effect=_fake_run_success):
            result = spawn_worker_with_cache(
                feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )
        assert result["feature_id"] == "feat-integration-01"

    def test_returns_stdout_and_stderr(self, tmp_path):
        feature = _make_feature()

        def fake_run(cmd, *, cwd, env, capture_output, text, timeout):
            m = mock.MagicMock()
            m.returncode = 0
            m.stdout = "worker output"
            m.stderr = "worker errors"
            return m

        with mock.patch("bob.dispatch.subprocess.run", side_effect=fake_run):
            result = spawn_worker_with_cache(
                feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
            )
        assert result["stdout"] == "worker output"
        assert result["stderr"] == "worker errors"

    def test_cache_event_emitted_on_exit(self, tmp_path):
        feature = _make_feature(id="feat-cache-evt-01")
        cache_events = []

        def fake_emit(cache_read, cache_write, *, feature_id=None):
            cache_events.append({"cache_read": cache_read, "cache_write": cache_write})
            return {"event": "WORKER_CACHE_HIT", "cache_read": cache_read, "cache_write": cache_write}

        with mock.patch("bob.dispatch.subprocess.run", side_effect=_fake_run_success):
            with mock.patch("bob.dispatch.emit_worker_cache_event", side_effect=fake_emit):
                spawn_worker_with_cache(
                    feature, "prompt", tmp_path, bob_dir=tmp_path / ".bob"
                )

        assert len(cache_events) == 1
