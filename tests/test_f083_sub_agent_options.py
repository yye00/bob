"""Tests for F083: Configure ClaudeCodeOptions for sub-agents (model, cwd, etc.)

Validates that:
- Step 1: Create ClaudeCodeOptions object via build_sub_agent_options
- Step 2: Set model (sonnet, opus, haiku) with alias resolution
- Step 3: Set cwd to project workspace
- Step 4: Set other options as needed (system_prompt, env, tools, etc.)
- Step 5: Spawn agent with specific options, verify they're applied
"""

import asyncio
import os
import pathlib
from unittest.mock import patch

import pytest

from claude_code_sdk import ClaudeCodeOptions


# ===================================================================
# Step 1: Create ClaudeCodeOptions object
# ===================================================================


class TestCreateClaudeCodeOptions:
    """Step 1: build_sub_agent_options creates a ClaudeCodeOptions object."""

    def test_returns_claude_code_options_instance(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options()
        assert isinstance(opts, ClaudeCodeOptions)

    def test_no_args_returns_valid_defaults(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options()
        assert opts.permission_mode == "bypassPermissions"
        assert opts.max_turns is not None
        assert opts.max_turns > 0

    def test_default_max_turns_is_25(self):
        from bob3.orchestrator.claude_executor import (
            build_sub_agent_options,
            DEFAULT_SUB_AGENT_MAX_TURNS,
        )

        opts = build_sub_agent_options()
        assert opts.max_turns == DEFAULT_SUB_AGENT_MAX_TURNS
        assert opts.max_turns == 25

    def test_default_permission_mode_is_bypass(self):
        from bob3.orchestrator.claude_executor import (
            build_sub_agent_options,
            DEFAULT_SUB_AGENT_PERMISSION_MODE,
        )

        opts = build_sub_agent_options()
        assert opts.permission_mode == DEFAULT_SUB_AGENT_PERMISSION_MODE
        assert opts.permission_mode == "bypassPermissions"


# ===================================================================
# Step 2: Set model (sonnet, opus, haiku)
# ===================================================================


class TestSetModel:
    """Step 2: Model aliases resolve to full Claude model IDs."""

    def test_set_model_sonnet(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(model="sonnet")
        assert opts.model is not None
        assert "sonnet" in opts.model
        assert opts.model.startswith("claude-")

    def test_set_model_opus(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(model="opus")
        assert opts.model is not None
        assert "opus" in opts.model
        assert opts.model.startswith("claude-")

    def test_set_model_haiku(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(model="haiku")
        assert opts.model is not None
        assert "haiku" in opts.model
        assert opts.model.startswith("claude-")

    def test_set_model_full_id(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        full_id = "claude-sonnet-4-5-20250929"
        opts = build_sub_agent_options(model=full_id)
        assert opts.model == full_id

    def test_model_none_uses_sdk_default(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(model=None)
        # When model is None, it should not be set (SDK picks default)
        assert opts.model is None

    def test_invalid_model_falls_back_to_default(self, caplog):
        """Robustness: an unknown model name must not crash the
        orchestration. ``build_sub_agent_options`` falls back to
        ``DEFAULT_SUB_AGENT_MODEL`` and logs a warning, rather than
        propagating ValueError up to the run loop where it would leave
        the feature stuck in 'executing'.

        Note: ``resolve_model_name`` itself still raises; the fallback
        is implemented at the ``build_sub_agent_options`` boundary.
        """
        import logging as _logging

        from bob3.orchestrator.claude_executor import (
            DEFAULT_SUB_AGENT_MODEL,
            MODEL_ALIASES,
            build_sub_agent_options,
        )

        with caplog.at_level(_logging.WARNING, logger="bob3.orchestrator.claude_executor"):
            opts = build_sub_agent_options(model="gpt-4-turbo")

        assert opts.model == MODEL_ALIASES[DEFAULT_SUB_AGENT_MODEL]
        assert any(
            "gpt-4-turbo" in rec.getMessage() for rec in caplog.records
        )

    def test_model_alias_case_insensitive(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts_lower = build_sub_agent_options(model="sonnet")
        opts_upper = build_sub_agent_options(model="SONNET")
        assert opts_lower.model == opts_upper.model

    def test_model_aliases_map_to_valid_ids(self):
        from bob3.orchestrator.claude_executor import MODEL_ALIASES, VALID_MODEL_IDS

        for alias, model_id in MODEL_ALIASES.items():
            assert model_id in VALID_MODEL_IDS, (
                f"Alias '{alias}' maps to '{model_id}' which is not in VALID_MODEL_IDS"
            )

    def test_default_sub_agent_model_is_valid_alias(self):
        from bob3.orchestrator.claude_executor import (
            DEFAULT_SUB_AGENT_MODEL,
            MODEL_ALIASES,
        )

        assert DEFAULT_SUB_AGENT_MODEL in MODEL_ALIASES


# ===================================================================
# Step 3: Set cwd to project workspace
# ===================================================================


class TestSetCwd:
    """Step 3: Set cwd to project workspace."""

    def test_cwd_string_path(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(cwd="/home/captain/clawd/work/bob3")
        assert opts.cwd == "/home/captain/clawd/work/bob3"

    def test_cwd_pathlib_path(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        p = pathlib.Path("/home/captain/clawd/work/bob3")
        opts = build_sub_agent_options(cwd=p)
        assert opts.cwd == str(p)

    def test_cwd_none_not_set(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(cwd=None)
        assert opts.cwd is None

    def test_cwd_tmp_path(self, tmp_path):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(cwd=tmp_path)
        assert opts.cwd == str(tmp_path)


# ===================================================================
# Step 4: Set other options as needed
# ===================================================================


class TestSetOtherOptions:
    """Step 4: Various other ClaudeCodeOptions settings."""

    def test_system_prompt(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(system_prompt="You are a test agent.")
        assert opts.system_prompt == "You are a test agent."

    def test_append_system_prompt(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(append_system_prompt="Extra context here.")
        assert opts.append_system_prompt == "Extra context here."

    def test_allowed_tools(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        tools = ["Bash", "Read", "Write"]
        opts = build_sub_agent_options(allowed_tools=tools)
        assert opts.allowed_tools == ["Bash", "Read", "Write"]

    def test_allowed_tools_are_copied(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        tools = ["Bash", "Read"]
        opts = build_sub_agent_options(allowed_tools=tools)
        # Mutating original should not affect options
        tools.append("Write")
        assert "Write" not in opts.allowed_tools

    def test_disallowed_tools(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        tools = ["Edit", "Write"]
        opts = build_sub_agent_options(disallowed_tools=tools)
        assert opts.disallowed_tools == ["Edit", "Write"]

    def test_disallowed_tools_are_copied(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        tools = ["Edit"]
        opts = build_sub_agent_options(disallowed_tools=tools)
        tools.append("Write")
        assert "Write" not in opts.disallowed_tools

    def test_custom_permission_mode(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(permission_mode="default")
        assert opts.permission_mode == "default"

    def test_custom_max_turns(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(max_turns=50)
        assert opts.max_turns == 50

    def test_mcp_servers(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        servers = {
            "test-server": {
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
            }
        }
        opts = build_sub_agent_options(mcp_servers=servers)
        assert "test-server" in opts.mcp_servers

    def test_mcp_servers_are_copied(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        servers = {"s1": {"type": "stdio", "command": "echo"}}
        opts = build_sub_agent_options(mcp_servers=servers)
        servers["s2"] = {"type": "stdio", "command": "test"}
        assert "s2" not in opts.mcp_servers

    def test_env_variables(self):
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        env = {"MY_VAR": "my_value", "OTHER_VAR": "other"}
        opts = build_sub_agent_options(env=env)
        assert opts.env["MY_VAR"] == "my_value"
        assert opts.env["OTHER_VAR"] == "other"

    def test_env_auto_forwards_api_key(self):
        """F081: API key is automatically forwarded to sub-agent env."""
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-test-key"}, clear=False):
            opts = build_sub_agent_options()
            assert "ANTHROPIC_API_KEY" in opts.env
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-test-key"

    def test_env_does_not_override_explicit_anthropic_key(self):
        """If caller already provides ANTHROPIC_API_KEY, don't override it."""
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        with patch.dict(os.environ, {"CLAUDE_API_KEY": "sk-auto"}, clear=False):
            env = {"ANTHROPIC_API_KEY": "sk-explicit"}
            opts = build_sub_agent_options(env=env)
            assert opts.env["ANTHROPIC_API_KEY"] == "sk-explicit"

    def test_multiple_options_combined(self):
        """All options can be combined in a single call."""
        from bob3.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(
            cwd="/tmp/test",
            model="haiku",
            max_turns=10,
            system_prompt="You are a builder.",
            allowed_tools=["Bash", "Read"],
            permission_mode="bypassPermissions",
            mcp_servers={"s": {"type": "stdio", "command": "x"}},
        )
        assert opts.cwd == "/tmp/test"
        assert "haiku" in opts.model
        assert opts.max_turns == 10
        assert opts.system_prompt == "You are a builder."
        assert opts.allowed_tools == ["Bash", "Read"]
        assert opts.permission_mode == "bypassPermissions"
        assert "s" in opts.mcp_servers


# ===================================================================
# Step 5: Spawn agent with specific options, verify they're applied
# ===================================================================


class TestSpawnAgentWithOptions:
    """Step 5: Verify options are correctly passed to claude_code_sdk.query."""

    def test_executor_passes_options_to_query(self):
        """ClaudeExecutor.execute passes options through to stream_query."""
        from bob3.orchestrator.claude_executor import (
            ClaudeExecutor,
            build_sub_agent_options,
        )
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = []

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            yield AssistantMessage(
                content=[TextBlock(text="done")], model="test"
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        opts = build_sub_agent_options(
            model="haiku",
            cwd="/tmp/test-workspace",
            max_turns=15,
            system_prompt="Test system prompt",
        )

        async def _run():
            executor = ClaudeExecutor(default_options=opts)
            with patch("bob3.orchestrator.claude_executor.query", mock_query):
                await executor.execute("test prompt")

        asyncio.run(_run())

        assert len(captured_options) == 1
        passed_opts = captured_options[0]
        assert passed_opts is opts
        assert "haiku" in passed_opts.model
        assert passed_opts.cwd == "/tmp/test-workspace"
        assert passed_opts.max_turns == 15
        assert passed_opts.system_prompt == "Test system prompt"

    def test_executor_per_call_options_override_default(self):
        """Per-call options override default_options in executor."""
        from bob3.orchestrator.claude_executor import (
            ClaudeExecutor,
            build_sub_agent_options,
        )
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = []

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            yield AssistantMessage(
                content=[TextBlock(text="done")], model="test"
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        default_opts = build_sub_agent_options(model="sonnet", max_turns=25)
        override_opts = build_sub_agent_options(model="opus", max_turns=50)

        async def _run():
            executor = ClaudeExecutor(default_options=default_opts)
            with patch("bob3.orchestrator.claude_executor.query", mock_query):
                await executor.execute("test", options=override_opts)

        asyncio.run(_run())

        assert len(captured_options) == 1
        passed_opts = captured_options[0]
        assert passed_opts is override_opts
        assert "opus" in passed_opts.model
        assert passed_opts.max_turns == 50

    def test_spawn_sub_agent_passes_options(self, monkeypatch):
        """spawn_sub_agent forwards options to stream_query.

        With ``PERPLEXITY_API_KEY`` unset bob3 does not need to merge in
        any MCP servers, so the original options object should be passed
        through untouched. (When the key is set, bob3 may build a new
        ClaudeCodeOptions with an extra mcp_servers entry; that
        behaviour is covered by the perplexity injection tests.)
        """
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from bob3.orchestrator.claude_executor import (
            build_sub_agent_options,
            spawn_sub_agent,
        )
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = []

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            yield AssistantMessage(
                content=[TextBlock(text="implemented")], model="test"
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=200,
                duration_api_ms=180,
                is_error=False,
                num_turns=2,
                session_id="spawn-s1",
                total_cost_usd=0.05,
                usage=None,
                result=None,
            )

        opts = build_sub_agent_options(
            model="haiku",
            cwd="/tmp/spawn-workspace",
            max_turns=10,
        )

        # Mock db functions so we don't need a real database
        mock_agent_run = type("MockRun", (), {"id": "run-123"})()

        async def _run():
            with (
                patch("bob3.orchestrator.claude_executor.query", mock_query),
                patch("bob3.db.create_agent_run", return_value=mock_agent_run),
                patch("bob3.db.update_agent_run", return_value=mock_agent_run),
            ):
                result = await spawn_sub_agent(
                    project_id="proj-1",
                    purpose="implement_feature",
                    prompt="Build feature X",
                    options=opts,
                )
                return result

        result = asyncio.run(_run())

        assert len(captured_options) == 1
        passed_opts = captured_options[0]
        assert passed_opts is opts
        assert "haiku" in passed_opts.model
        assert passed_opts.cwd == "/tmp/spawn-workspace"
        assert passed_opts.max_turns == 10

    def test_research_agent_uses_configured_options(self):
        """spawn_research_agent builds options with Perplexity MCP and model."""
        from bob3.orchestrator.claude_executor import spawn_research_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = []

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            yield AssistantMessage(
                content=[TextBlock(text="research results")], model="test"
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=300,
                duration_api_ms=280,
                is_error=False,
                num_turns=3,
                session_id="research-s1",
                total_cost_usd=0.08,
                usage=None,
                result=None,
            )

        mock_agent_run = type("MockRun", (), {"id": "run-456"})()

        async def _run():
            with (
                patch("bob3.orchestrator.claude_executor.query", mock_query),
                patch("bob3.db.create_agent_run", return_value=mock_agent_run),
                patch("bob3.db.update_agent_run", return_value=mock_agent_run),
                patch.dict(os.environ, {"PERPLEXITY_API_KEY": "pplx-test"}, clear=False),
            ):
                result = await spawn_research_agent(
                    project_id="proj-1",
                    query="How to implement TDD?",
                    max_turns=8,
                )
                return result

        result = asyncio.run(_run())

        assert len(captured_options) == 1
        passed_opts = captured_options[0]
        assert isinstance(passed_opts, ClaudeCodeOptions)
        # Research agent uses default model
        assert passed_opts.model is not None
        # System prompt is set for research
        assert passed_opts.system_prompt is not None
        assert "research" in passed_opts.system_prompt.lower()
        # Max turns is passed through
        assert passed_opts.max_turns == 8
        # Permission mode is bypass
        assert passed_opts.permission_mode == "bypassPermissions"

    def test_rca_agent_uses_configured_options(self):
        """spawn_rca_agent builds options with RCA system prompt and model."""
        from bob3.orchestrator.claude_executor import spawn_rca_agent
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        captured_options = []

        async def mock_query(*, prompt, options=None, transport=None):
            captured_options.append(options)
            yield AssistantMessage(
                content=[TextBlock(text='```json\n{"blame_target": "implementation", "recommended_action": "fix_code", "root_cause": "missing null check"}\n```')],
                model="test",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=400,
                duration_api_ms=380,
                is_error=False,
                num_turns=3,
                session_id="rca-s1",
                total_cost_usd=0.06,
                usage=None,
                result=None,
            )

        mock_agent_run = type("MockRun", (), {"id": "run-789"})()

        async def _run():
            with (
                patch("bob3.orchestrator.claude_executor.query", mock_query),
                patch("bob3.db.create_agent_run", return_value=mock_agent_run),
                patch("bob3.db.update_agent_run", return_value=mock_agent_run),
            ):
                result = await spawn_rca_agent(
                    project_id="proj-1",
                    failure_evidence="TypeError: cannot read property 'x'",
                    error_type="test_failure",
                    error_message="TypeError at line 42",
                    max_turns=5,
                )
                return result

        result = asyncio.run(_run())

        assert len(captured_options) == 1
        passed_opts = captured_options[0]
        assert isinstance(passed_opts, ClaudeCodeOptions)
        assert passed_opts.model is not None
        assert passed_opts.system_prompt is not None
        assert "rca" in passed_opts.system_prompt.lower() or "root cause" in passed_opts.system_prompt.lower()
        assert passed_opts.max_turns == 5
        assert passed_opts.permission_mode == "bypassPermissions"
