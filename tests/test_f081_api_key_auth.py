"""Tests for F081: Verify Claude SDK client authentication via CLAUDE_API_KEY.

Validates that Bob3:
- Checks the CLAUDE_API_KEY environment variable
- Passes it to ClaudeCodeOptions via the env dict
- Handles missing key gracefully with an informative error message
- Works correctly when the key is present
"""

import os
import pathlib
from unittest.mock import patch

import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob3" / "orchestrator" / "claude_executor.py"


# ===================================================================
# Step 1: Check CLAUDE_API_KEY environment variable
# ===================================================================


class TestCheckApiKey:
    """Step 1: validate_api_key checks the CLAUDE_API_KEY env var."""

    def test_validate_api_key_function_exists(self):
        from bob3.orchestrator.claude_executor import validate_api_key

        assert callable(validate_api_key)

    def test_returns_key_when_set(self):
        from bob3.orchestrator.claude_executor import validate_api_key

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test-123"}):
            key = validate_api_key()
            assert key == "sk-test-123"

    def test_returns_none_when_not_set(self):
        from bob3.orchestrator.claude_executor import validate_api_key

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            key = validate_api_key()
            assert key is None

    def test_falls_back_to_anthropic_api_key(self):
        from bob3.orchestrator.claude_executor import validate_api_key

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env["ANTHROPIC_API_KEY"] = "sk-ant-test-456"
        with patch.dict(os.environ, env, clear=True):
            key = validate_api_key()
            assert key == "sk-ant-test-456"

    def test_claude_api_key_takes_precedence(self):
        from bob3.orchestrator.claude_executor import validate_api_key

        with patch.dict(os.environ, {
            "CLAUDE_API_KEY": "sk-claude-key",
            "ANTHROPIC_API_KEY": "sk-anthropic-key",
        }):
            key = validate_api_key()
            assert key == "sk-claude-key"


# ===================================================================
# Step 2: Pass to ClaudeSDKClient options
# ===================================================================


class TestPassApiKeyToOptions:
    """Step 2: build_sub_agent_options forwards the API key to env."""

    def test_api_key_passed_via_env(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test-789"}):
            opts = build_sub_agent_options()
            # The API key should be in the env dict
            assert "ANTHROPIC_API_KEY" in opts.env
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-test-789"

    def test_anthropic_key_passed_via_env(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env["ANTHROPIC_API_KEY"] = "sk-ant-test-abc"
        with patch.dict(os.environ, env, clear=True):
            opts = build_sub_agent_options()
            assert "ANTHROPIC_API_KEY" in opts.env
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-ant-test-abc"

    def test_explicit_env_not_overridden(self):
        """If caller passes explicit env with ANTHROPIC_API_KEY, don't override."""
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-from-env"}):
            opts = build_sub_agent_options(
                env={"ANTHROPIC_API_KEY": "sk-explicit"}
            )
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-explicit"

    def test_no_key_no_env_entry(self):
        """If no API key is available, don't add ANTHROPIC_API_KEY to env."""
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            opts = build_sub_agent_options()
            assert "ANTHROPIC_API_KEY" not in opts.env


# ===================================================================
# Step 3: Handle missing key gracefully with error message
# ===================================================================


class TestMissingKeyHandling:
    """Step 3: require_api_key raises a clear error when no key is found."""

    def test_require_api_key_function_exists(self):
        from bob3.orchestrator.claude_executor import require_api_key

        assert callable(require_api_key)

    def test_require_api_key_returns_key_when_present(self):
        from bob3.orchestrator.claude_executor import require_api_key

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-good-key"}):
            key = require_api_key()
            assert key == "sk-good-key"

    def test_require_api_key_raises_when_missing(self):
        from bob3.orchestrator.claude_executor import require_api_key

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError, match="CLAUDE_API_KEY"):
                require_api_key()

    def test_error_message_mentions_both_env_vars(self):
        from bob3.orchestrator.claude_executor import require_api_key

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError) as exc_info:
                require_api_key()
            msg = str(exc_info.value)
            assert "CLAUDE_API_KEY" in msg
            assert "ANTHROPIC_API_KEY" in msg


# ===================================================================
# Step 4: Test: Run without key, verify error message
# ===================================================================


class TestRunWithoutKey:
    """Step 4: Running without a key produces a clear error message."""

    def test_validate_returns_none_no_key(self):
        """validate_api_key returns None when no key env var is set."""
        from bob3.orchestrator.claude_executor import validate_api_key

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            assert validate_api_key() is None

    def test_require_raises_environment_error_no_key(self):
        """require_api_key raises EnvironmentError with helpful message."""
        from bob3.orchestrator.claude_executor import require_api_key

        env = os.environ.copy()
        env.pop("CLAUDE_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError) as exc_info:
                require_api_key()
            msg = str(exc_info.value)
            # Error message should tell user what to do
            assert "set" in msg.lower() or "export" in msg.lower() or "missing" in msg.lower()


# ===================================================================
# Step 5: Test: Run with key, verify authentication works
# ===================================================================


class TestRunWithKey:
    """Step 5: Running with a key correctly forwards it."""

    def test_validate_returns_key_value(self):
        from bob3.orchestrator.claude_executor import validate_api_key

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-valid-key-123"}):
            assert validate_api_key() == "sk-valid-key-123"

    def test_build_options_includes_key_in_env(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-valid-key-456"}):
            opts = build_sub_agent_options()
            assert opts.env.get("ANTHROPIC_API_KEY") == "sk-valid-key-456"

    def test_key_forwarded_with_other_env_vars(self):
        """API key is forwarded alongside other env vars."""
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test-key"}):
            opts = build_sub_agent_options(env={"MY_VAR": "my-value"})
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-test-key"
            assert opts.env["MY_VAR"] == "my-value"

    def test_empty_key_treated_as_missing(self):
        """An empty CLAUDE_API_KEY is treated as not set."""
        from bob3.orchestrator.claude_executor import validate_api_key

        with patch.dict(os.environ, {"CLAUDE_API_KEY": ""}):
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                # Re-set the empty key in the clean environment
                os.environ["CLAUDE_API_KEY"] = ""
                key = validate_api_key()
                assert key is None
