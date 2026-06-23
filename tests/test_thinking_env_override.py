"""Tests for Vertex-compatible thinking env per spawned model (feature f4f122ce).

Verifies:
- _FORCE_THINKING_SETTINGS is defined and contains alwaysThinkingEnabled
- _FORCE_THINKING_ENV is defined and disables both adaptive and thinking
- _thinking_env_for_model returns the right env for opus/sonnet vs haiku
- CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING and CLAUDE_CODE_DISABLE_THINKING are used
- Integration: bob3.orchestrator.claude_executor exports all required symbols
"""

from __future__ import annotations

import json
import tempfile

import pytest

from bob3.orchestrator.claude_executor import (
    _FORCE_THINKING_ENV,
    _FORCE_THINKING_SETTINGS,
    _thinking_env_for_model,
    _attach_stderr_capture,
)
from claude_code_sdk import ClaudeCodeOptions


# ---------------------------------------------------------------------------
# _FORCE_THINKING_SETTINGS
# ---------------------------------------------------------------------------


class TestForceThinkingSettings:
    """_FORCE_THINKING_SETTINGS must be valid JSON with alwaysThinkingEnabled."""

    def test_is_string(self):
        assert isinstance(_FORCE_THINKING_SETTINGS, str)

    def test_is_valid_json(self):
        parsed = json.loads(_FORCE_THINKING_SETTINGS)
        assert isinstance(parsed, dict)

    def test_contains_always_thinking_enabled(self):
        parsed = json.loads(_FORCE_THINKING_SETTINGS)
        assert "alwaysThinkingEnabled" in parsed

    def test_always_thinking_enabled_is_true(self):
        parsed = json.loads(_FORCE_THINKING_SETTINGS)
        assert parsed["alwaysThinkingEnabled"] is True


# ---------------------------------------------------------------------------
# _FORCE_THINKING_ENV
# ---------------------------------------------------------------------------


class TestForceThinkingEnv:
    """_FORCE_THINKING_ENV must disable both adaptive thinking and thinking."""

    def test_is_dict(self):
        assert isinstance(_FORCE_THINKING_ENV, dict)

    def test_contains_disable_adaptive_thinking(self):
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in _FORCE_THINKING_ENV

    def test_contains_disable_thinking(self):
        assert "CLAUDE_CODE_DISABLE_THINKING" in _FORCE_THINKING_ENV

    def test_both_set_to_1(self):
        assert _FORCE_THINKING_ENV["CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING"] == "1"
        assert _FORCE_THINKING_ENV["CLAUDE_CODE_DISABLE_THINKING"] == "1"


# ---------------------------------------------------------------------------
# _thinking_env_for_model
# ---------------------------------------------------------------------------


class TestThinkingEnvForModel:
    """_thinking_env_for_model must pick the right combination per model."""

    # ---- opus-4-6 / opus-4-7 / sonnet-4-6: adaptive-disable only ----

    def test_opus_4_6_adaptive_disable_only(self):
        env = _thinking_env_for_model("claude-opus-4-6")
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
        assert "CLAUDE_CODE_DISABLE_THINKING" not in env

    def test_opus_4_7_adaptive_disable_only(self):
        env = _thinking_env_for_model("claude-opus-4-7")
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
        assert "CLAUDE_CODE_DISABLE_THINKING" not in env

    def test_sonnet_4_6_adaptive_disable_only(self):
        env = _thinking_env_for_model("claude-sonnet-4-6")
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
        assert "CLAUDE_CODE_DISABLE_THINKING" not in env

    def test_sonnet_4_6_alias_adaptive_disable_only(self):
        # gateway deployment names may use dots instead of dashes
        env = _thinking_env_for_model("Claude-Sonnet-4.6")
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
        assert "CLAUDE_CODE_DISABLE_THINKING" not in env

    def test_opus_4_6_adaptive_set_to_1(self):
        env = _thinking_env_for_model("claude-opus-4-6")
        assert env["CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING"] == "1"

    # ---- haiku-4-5 and unknown models: BOTH env vars ----

    def test_haiku_both_vars(self):
        env = _thinking_env_for_model("claude-haiku-4-5-20251001")
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
        assert "CLAUDE_CODE_DISABLE_THINKING" in env

    def test_haiku_both_vars_set_to_1(self):
        env = _thinking_env_for_model("claude-haiku-4-5-20251001")
        assert env["CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING"] == "1"
        assert env["CLAUDE_CODE_DISABLE_THINKING"] == "1"

    def test_none_model_both_vars(self):
        env = _thinking_env_for_model(None)
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
        assert "CLAUDE_CODE_DISABLE_THINKING" in env

    def test_unknown_model_both_vars(self):
        env = _thinking_env_for_model("some-unknown-model")
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
        assert "CLAUDE_CODE_DISABLE_THINKING" in env

    def test_returns_dict(self):
        env = _thinking_env_for_model("claude-opus-4-6")
        assert isinstance(env, dict)

    def test_all_values_are_strings(self):
        for model in ["claude-opus-4-6", "claude-haiku-4-5-20251001", None]:
            env = _thinking_env_for_model(model)
            for k, v in env.items():
                assert isinstance(v, str), f"env[{k!r}] is not str for model={model!r}"


# ---------------------------------------------------------------------------
# Integration: _attach_stderr_capture injects thinking overrides
# ---------------------------------------------------------------------------


class TestAttachStderrCaptureThinkingInjection:
    """_attach_stderr_capture must inject thinking env+settings at the choke point."""

    def _make_file_buffer(self):
        return tempfile.NamedTemporaryFile(
            mode="w+", encoding="utf-8", delete=False, suffix=".stderr"
        )

    def test_none_options_gets_force_thinking_env(self):
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(None, buf)
            env = result.env or {}
            assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
            assert "CLAUDE_CODE_DISABLE_THINKING" in env
        finally:
            buf.close()

    def test_none_options_gets_force_thinking_settings(self):
        buf = self._make_file_buffer()
        try:
            result = _attach_stderr_capture(None, buf)
            assert result.settings is not None
            assert "alwaysThinkingEnabled" in result.settings
        finally:
            buf.close()

    def test_opus_options_gets_adaptive_disable_only(self):
        buf = self._make_file_buffer()
        try:
            opts = ClaudeCodeOptions(model="claude-opus-4-6")
            result = _attach_stderr_capture(opts, buf)
            env = result.env or {}
            assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
            assert "CLAUDE_CODE_DISABLE_THINKING" not in env
        finally:
            buf.close()

    def test_haiku_options_gets_both_disable_vars(self):
        buf = self._make_file_buffer()
        try:
            opts = ClaudeCodeOptions(model="claude-haiku-4-5-20251001")
            result = _attach_stderr_capture(opts, buf)
            env = result.env or {}
            assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in env
            assert "CLAUDE_CODE_DISABLE_THINKING" in env
        finally:
            buf.close()

    def test_caller_env_merged_not_overwritten(self):
        """Caller-supplied env vars must survive the merge."""
        buf = self._make_file_buffer()
        try:
            opts = ClaudeCodeOptions(
                model="claude-opus-4-6",
                env={"MY_CUSTOM_VAR": "hello"},
            )
            result = _attach_stderr_capture(opts, buf)
            env = result.env or {}
            assert env.get("MY_CUSTOM_VAR") == "hello"
        finally:
            buf.close()


# ---------------------------------------------------------------------------
# Integration: module-level import check
# ---------------------------------------------------------------------------


class TestModuleLevelExports:
    """All required symbols must be importable from claude_executor."""

    def test_force_thinking_settings_importable(self):
        from bob3.orchestrator.claude_executor import _FORCE_THINKING_SETTINGS
        assert _FORCE_THINKING_SETTINGS is not None

    def test_force_thinking_env_importable(self):
        from bob3.orchestrator.claude_executor import _FORCE_THINKING_ENV
        assert _FORCE_THINKING_ENV is not None

    def test_thinking_env_for_model_importable(self):
        from bob3.orchestrator.claude_executor import _thinking_env_for_model
        assert callable(_thinking_env_for_model)

    def test_disable_adaptive_thinking_constant_used(self):
        """CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING must appear in module source."""
        import bob3.orchestrator.claude_executor as mod
        import inspect
        src = inspect.getsource(mod)
        assert "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING" in src

    def test_disable_thinking_constant_used(self):
        """CLAUDE_CODE_DISABLE_THINKING must appear in module source."""
        import bob3.orchestrator.claude_executor as mod
        import inspect
        src = inspect.getsource(mod)
        assert "CLAUDE_CODE_DISABLE_THINKING" in src
