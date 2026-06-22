"""Tests for bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per.

Feature 5b6febb0: Claude-Code worker leverage — enable prompt cache, slim per-worker context,
re-declare settings.

ACs tested:
  - Function defined: claude_code_worker_leverage_enable_prompt_cache_slim_per
  - File exists: src/bob3/claude_code_worker_leverage_enable_prompt_cache_slim_per.py
  - pytest: this file::test_claude_code_worker_leverage_enable_prompt_cache_slim_per
  - integration: bob3.orchestrator.run_loop
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per import (
    claude_code_worker_leverage_enable_prompt_cache_slim_per,
    apply_worker_leverage,
    build_worker_context,
    emit_perm_prompt_event,
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


# ── Main entry point ──────────────────────────────────────────────────────────

def test_claude_code_worker_leverage_enable_prompt_cache_slim_per():
    """Primary AC: function exists and is callable."""
    assert callable(claude_code_worker_leverage_enable_prompt_cache_slim_per)


class TestMainFunction:
    def test_returns_dict(self, tmp_path):
        feature = _make_feature(id="feat-main-01")
        result = claude_code_worker_leverage_enable_prompt_cache_slim_per(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        assert isinstance(result, dict)

    def test_result_has_settings_path(self, tmp_path):
        feature = _make_feature(id="feat-main-02")
        result = claude_code_worker_leverage_enable_prompt_cache_slim_per(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        assert "settings_path" in result

    def test_result_has_worker_md_path(self, tmp_path):
        feature = _make_feature(id="feat-main-03")
        result = claude_code_worker_leverage_enable_prompt_cache_slim_per(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        assert "worker_md_path" in result

    def test_settings_file_created(self, tmp_path):
        feature = _make_feature(id="feat-main-04")
        claude_code_worker_leverage_enable_prompt_cache_slim_per(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        settings_path = tmp_path / ".bob3" / "features" / "feat-main-04" / "settings.json"
        assert settings_path.exists()

    def test_worker_md_file_created(self, tmp_path):
        feature = _make_feature(id="feat-main-05")
        claude_code_worker_leverage_enable_prompt_cache_slim_per(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        worker_md = tmp_path / ".bob3" / "features" / "WORKER.md"
        assert worker_md.exists()

    def test_result_has_env_vars(self, tmp_path):
        feature = _make_feature(id="feat-main-06")
        result = claude_code_worker_leverage_enable_prompt_cache_slim_per(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        assert "env" in result

    def test_prompt_caching_env_var_in_result(self, tmp_path):
        feature = _make_feature(id="feat-main-07")
        result = claude_code_worker_leverage_enable_prompt_cache_slim_per(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        env = result["env"]
        assert env.get("ANTHROPIC_PROMPT_CACHING") == "1"


# ── apply_worker_leverage ────────────────────────────────────────────────────

class TestApplyWorkerLeverage:
    def test_returns_dict(self, tmp_path):
        feature = _make_feature(id="feat-awl-01")
        result = apply_worker_leverage(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        assert isinstance(result, dict)

    def test_settings_path_is_path(self, tmp_path):
        feature = _make_feature(id="feat-awl-02")
        result = apply_worker_leverage(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        assert isinstance(result["settings_path"], Path)

    def test_env_contains_caching_flag(self, tmp_path):
        feature = _make_feature(id="feat-awl-03")
        result = apply_worker_leverage(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        assert result["env"].get("ANTHROPIC_PROMPT_CACHING") == "1"

    def test_extra_allow_merged_into_settings(self, tmp_path):
        feature = _make_feature(id="feat-awl-04")
        apply_worker_leverage(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
            extra_allow=["Bash(make*)"],
        )
        settings_path = tmp_path / ".bob3" / "features" / "feat-awl-04" / "settings.json"
        data = json.loads(settings_path.read_text())
        assert "Bash(make*)" in data["permissions"]["allow"]

    def test_worker_md_content_includes_feature_name(self, tmp_path):
        feature = _make_feature(id="feat-awl-05", name="Special Feature Name")
        apply_worker_leverage(
            feature=feature,
            workspace=str(tmp_path),
            bob3_dir=tmp_path / ".bob3",
        )
        worker_md = tmp_path / ".bob3" / "features" / "WORKER.md"
        content = worker_md.read_text()
        assert "Special Feature Name" in content


# ── build_worker_context ──────────────────────────────────────────────────────

class TestBuildWorkerContext:
    def test_returns_dict(self):
        feature = _make_feature()
        result = build_worker_context(feature=feature, workspace="/tmp/ws")
        assert isinstance(result, dict)

    def test_has_worker_md_content(self):
        feature = _make_feature(name="Context Test")
        result = build_worker_context(feature=feature, workspace="/tmp/ws")
        assert "worker_md" in result
        assert "Context Test" in result["worker_md"]

    def test_has_env_dict(self):
        feature = _make_feature()
        result = build_worker_context(feature=feature, workspace="/tmp/ws")
        assert "env" in result
        assert isinstance(result["env"], dict)

    def test_env_has_caching_key(self):
        feature = _make_feature()
        result = build_worker_context(feature=feature, workspace="/tmp/ws")
        assert "ANTHROPIC_PROMPT_CACHING" in result["env"]

    def test_worker_md_contains_workspace(self):
        feature = _make_feature()
        result = build_worker_context(feature=feature, workspace="/workspace/bob99")
        assert "/workspace/bob99" in result["worker_md"]

    def test_worker_md_contains_acs(self):
        feature = _make_feature(acceptance_criteria='["pytest: tests/test_foo.py", "File exists: src/foo.py"]')
        result = build_worker_context(feature=feature, workspace="/tmp")
        assert "tests/test_foo.py" in result["worker_md"]


# ── emit_perm_prompt_event ────────────────────────────────────────────────────

class TestEmitPermPromptEvent:
    def test_returns_dict(self):
        event = emit_perm_prompt_event(feature_id="feat-001", tool="Bash(ls*)")
        assert isinstance(event, dict)

    def test_event_key(self):
        event = emit_perm_prompt_event(feature_id="feat-001", tool="Read(*)")
        assert event["event"] == "WORKER_PERM_PROMPT"

    def test_feature_id_in_event(self):
        event = emit_perm_prompt_event(feature_id="feat-xyz", tool="Write(*)")
        assert event["feature_id"] == "feat-xyz"

    def test_tool_in_event(self):
        event = emit_perm_prompt_event(feature_id="feat-001", tool="Bash(pytest*)")
        assert event["tool"] == "Bash(pytest*)"

    def test_logs_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per"):
            emit_perm_prompt_event(feature_id="feat-001", tool="Bash(rm*)")
        assert any("WORKER_PERM_PROMPT" in r.message for r in caplog.records)


# ── Integration: bob3.orchestrator.run_loop ───────────────────────────────────

class TestRunLoopIntegration:
    def test_module_importable_from_run_loop(self):
        """The integration AC requires the module to be imported in run_loop."""
        import bob3.orchestrator.run_loop as rl
        assert hasattr(rl, "_claude_code_worker_leverage_integrated")

    def test_function_importable_from_module(self):
        from bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per import (
            claude_code_worker_leverage_enable_prompt_cache_slim_per,
        )
        assert callable(claude_code_worker_leverage_enable_prompt_cache_slim_per)

    def test_apply_worker_leverage_importable(self):
        from bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per import apply_worker_leverage
        assert callable(apply_worker_leverage)

    def test_build_worker_context_importable(self):
        from bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per import build_worker_context
        assert callable(build_worker_context)

    def test_emit_perm_prompt_event_importable(self):
        from bob3.claude_code_worker_leverage_enable_prompt_cache_slim_per import emit_perm_prompt_event
        assert callable(emit_perm_prompt_event)
