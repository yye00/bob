"""Tests for F006: Claude executor using claude-code-sdk.

Validates that the executor module:
- Uses ONLY claude-code-sdk (no subprocess, no CLI, no anthropic SDK)
- Provides ClaudeExecutor with async execution
- Correctly processes SDK message types
- Builds ClaudeCodeOptions with Bob defaults
- Extracts text/tool info from content blocks
"""

import ast
import asyncio
import inspect
import os
import pathlib
import re
import textwrap
from dataclasses import fields as dataclass_fields
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import paths under test
# ---------------------------------------------------------------------------

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob" / "orchestrator" / "claude_executor.py"


# ===================================================================
# Step 1: File exists
# ===================================================================


class TestFileExists:
    """Step 1: src/bob/orchestrator/claude_executor.py must exist."""

    def test_module_file_exists(self):
        assert MODULE_PATH.is_file(), f"Expected {MODULE_PATH} to exist"

    def test_module_is_non_empty(self):
        content = MODULE_PATH.read_text()
        assert len(content.strip()) > 100, "Module appears to be a stub"


# ===================================================================
# Step 2: Imports from claude_code_sdk
# ===================================================================


class TestImports:
    """Step 2: Module imports from claude_code_sdk, not anthropic."""

    def test_imports_from_claude_code_sdk(self):
        source = MODULE_PATH.read_text()
        assert "from claude_code_sdk import" in source or "import claude_code_sdk" in source

    def test_imports_claude_sdk_client(self):
        from bob.orchestrator.claude_executor import ClaudeCodeOptions
        from claude_code_sdk import ClaudeCodeOptions as SdkOptions

        assert ClaudeCodeOptions is SdkOptions

    def test_imports_message_types(self):
        from bob.orchestrator import claude_executor as mod

        assert hasattr(mod, "AssistantMessage")
        assert hasattr(mod, "ResultMessage")

    def test_no_anthropic_import(self):
        source = MODULE_PATH.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("anthropic"), (
                        "Must not import anthropic SDK"
                    )
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith("anthropic"), (
                        "Must not import from anthropic"
                    )


# ===================================================================
# Step 5: No subprocess / CLI usage
# ===================================================================


class TestNoSubprocessUsage:
    """Step 5: MANDATORY - no subprocess, os.system, os.popen, Popen."""

    def test_no_subprocess_in_source(self):
        source = MODULE_PATH.read_text()
        # Strip comment lines and docstrings before checking for forbidden patterns
        code_lines = [
            line for line in source.splitlines()
            if not line.strip().startswith("#") and not line.strip().startswith('"""') and not line.strip().startswith("'''")
        ]
        code_only = "\n".join(code_lines)
        forbidden = ["os.system", "os.popen", "Popen"]
        for pattern in forbidden:
            assert pattern not in code_only, (
                f"Found forbidden '{pattern}' in claude_executor.py"
            )
        # Check for actual subprocess usage (imports/calls), not mentions in comments
        assert not re.search(r'^\s*(import\s+subprocess|from\s+subprocess\b)', source, re.MULTILINE), (
            "Found forbidden subprocess import in claude_executor.py"
        )
        assert not re.search(r'\bsubprocess\.', code_only), (
            "Found forbidden subprocess usage in claude_executor.py"
        )

    def test_no_subprocess_import(self):
        source = MODULE_PATH.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess", "Must not import subprocess"
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "subprocess" not in node.module, (
                        "Must not import from subprocess"
                    )

    def test_no_cli_invocation_patterns(self):
        source = MODULE_PATH.read_text()
        cli_patterns = [
            r"subprocess\.run",
            r"subprocess\.Popen",
            r"subprocess\.call",
            r"os\.system\(",
            r"os\.popen\(",
            r"Popen\(",
            r"'claude'\s*,\s*'-p'",
            r'"claude"\s*,\s*"-p"',
        ]
        for pat in cli_patterns:
            assert not re.search(pat, source), (
                f"Found forbidden CLI pattern: {pat}"
            )


# ===================================================================
# Step 6: Imports only from claude_code_sdk
# ===================================================================


class TestOnlyClaudeCodeSDK:
    """Step 6: MANDATORY - imports only from claude_code_sdk, not anthropic."""

    def test_no_anthropic_sdk_objects_used(self):
        source = MODULE_PATH.read_text()
        assert "from anthropic" not in source
        assert "import anthropic" not in source


# ===================================================================
# Core functionality: ExecutionResult
# ===================================================================


class TestExecutionResult:
    """ExecutionResult dataclass holds execution metadata."""

    def test_can_create_default(self):
        from bob.orchestrator.claude_executor import ExecutionResult

        result = ExecutionResult()
        assert result.text == ""
        assert result.is_error is False
        assert result.error_message == ""
        assert result.duration_ms == 0
        assert result.num_turns == 0
        assert result.session_id == ""
        assert result.total_cost_usd is None
        assert result.tool_uses == []
        assert result.messages == []

    def test_is_dataclass(self):
        from bob.orchestrator.claude_executor import ExecutionResult
        import dataclasses

        assert dataclasses.is_dataclass(ExecutionResult)

    def test_has_required_fields(self):
        from bob.orchestrator.claude_executor import ExecutionResult

        field_names = {f.name for f in dataclass_fields(ExecutionResult)}
        required = {"text", "is_error", "error_message", "duration_ms",
                     "num_turns", "session_id", "total_cost_usd",
                     "tool_uses", "messages"}
        assert required.issubset(field_names)


# ===================================================================
# Core functionality: extract_text_from_blocks
# ===================================================================


class TestExtractTextFromBlocks:
    """Text extraction from SDK content blocks."""

    def test_extracts_text_blocks(self):
        from bob.orchestrator.claude_executor import extract_text_from_blocks
        from claude_code_sdk import TextBlock

        blocks = [TextBlock(text="hello"), TextBlock(text="world")]
        result = extract_text_from_blocks(blocks)
        assert "hello" in result
        assert "world" in result

    def test_skips_tool_use_blocks(self):
        from bob.orchestrator.claude_executor import extract_text_from_blocks
        from claude_code_sdk import TextBlock, ToolUseBlock

        blocks = [
            TextBlock(text="hello"),
            ToolUseBlock(id="1", name="Bash", input={"command": "ls"}),
        ]
        result = extract_text_from_blocks(blocks)
        assert "hello" in result
        assert "Bash" not in result

    def test_empty_blocks_returns_empty(self):
        from bob.orchestrator.claude_executor import extract_text_from_blocks

        assert extract_text_from_blocks([]) == ""


# ===================================================================
# Core functionality: extract_tool_names
# ===================================================================


class TestExtractToolNames:
    """Tool name extraction from content blocks."""

    def test_extracts_tool_names(self):
        from bob.orchestrator.claude_executor import extract_tool_names
        from claude_code_sdk import ToolUseBlock, TextBlock

        blocks = [
            TextBlock(text="hello"),
            ToolUseBlock(id="1", name="Bash", input={}),
            ToolUseBlock(id="2", name="Read", input={}),
        ]
        names = extract_tool_names(blocks)
        assert names == ["Bash", "Read"]

    def test_empty_blocks_returns_empty_list(self):
        from bob.orchestrator.claude_executor import extract_tool_names

        assert extract_tool_names([]) == []


# ===================================================================
# Core functionality: process_message
# ===================================================================


class TestProcessMessage:
    """Message processing updates ExecutionResult in place."""

    def test_assistant_message_accumulates_text(self):
        from bob.orchestrator.claude_executor import process_message, ExecutionResult
        from claude_code_sdk import AssistantMessage, TextBlock

        result = ExecutionResult()
        msg = AssistantMessage(
            content=[TextBlock(text="Hello from Claude")],
            model="claude-sonnet-4-5-20250929",
        )
        process_message(msg, result)
        assert "Hello from Claude" in result.text
        assert msg in result.messages

    def test_assistant_message_accumulates_tool_uses(self):
        from bob.orchestrator.claude_executor import process_message, ExecutionResult
        from claude_code_sdk import AssistantMessage, ToolUseBlock

        result = ExecutionResult()
        msg = AssistantMessage(
            content=[ToolUseBlock(id="1", name="Bash", input={})],
            model="claude-sonnet-4-5-20250929",
        )
        process_message(msg, result)
        assert "Bash" in result.tool_uses

    def test_result_message_records_metadata(self):
        from bob.orchestrator.claude_executor import process_message, ExecutionResult
        from claude_code_sdk import ResultMessage

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="success",
            duration_ms=1234,
            duration_api_ms=1000,
            is_error=False,
            num_turns=3,
            session_id="sess-123",
            total_cost_usd=0.05,
            usage=None,
            result=None,
        )
        process_message(msg, result)
        assert result.duration_ms == 1234
        assert result.num_turns == 3
        assert result.session_id == "sess-123"
        assert result.total_cost_usd == 0.05
        assert result.is_error is False

    def test_error_result_message(self):
        from bob.orchestrator.claude_executor import process_message, ExecutionResult
        from claude_code_sdk import ResultMessage

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="error",
            duration_ms=500,
            duration_api_ms=400,
            is_error=True,
            num_turns=1,
            session_id="sess-err",
            total_cost_usd=0.01,
            usage=None,
            result="Something went wrong",
        )
        process_message(msg, result)
        assert result.is_error is True
        assert "Something went wrong" in result.error_message

    def test_multiple_assistant_messages_concatenated(self):
        from bob.orchestrator.claude_executor import process_message, ExecutionResult
        from claude_code_sdk import AssistantMessage, TextBlock

        result = ExecutionResult()
        process_message(
            AssistantMessage(content=[TextBlock(text="First")], model="m"), result
        )
        process_message(
            AssistantMessage(content=[TextBlock(text="Second")], model="m"), result
        )
        assert "First" in result.text
        assert "Second" in result.text


# ===================================================================
# Core functionality: Model resolution
# ===================================================================


class TestModelResolution:
    """Model aliases resolve to full model IDs."""

    def test_resolve_sonnet(self):
        from bob.orchestrator.claude_executor import resolve_model_name

        result = resolve_model_name("sonnet")
        assert "sonnet" in result.lower()
        assert "claude-" in result.lower()

    def test_resolve_opus(self):
        from bob.orchestrator.claude_executor import resolve_model_name

        result = resolve_model_name("opus")
        assert "opus" in result.lower()
        assert "claude-" in result.lower()

    def test_resolve_haiku(self):
        from bob.orchestrator.claude_executor import resolve_model_name

        result = resolve_model_name("haiku")
        assert "haiku" in result.lower()
        assert "claude-" in result.lower()

    def test_resolve_none_returns_none(self):
        from bob.orchestrator.claude_executor import resolve_model_name

        assert resolve_model_name(None) is None

    def test_resolve_full_id_passthrough(self):
        from bob.orchestrator.claude_executor import resolve_model_name

        full_id = "claude-sonnet-4-5-20250929"
        assert resolve_model_name(full_id) == full_id

    def test_resolve_unknown_raises(self):
        from bob.orchestrator.claude_executor import resolve_model_name

        with pytest.raises(ValueError, match="Unknown model"):
            resolve_model_name("gpt-4")


# ===================================================================
# Core functionality: build_sub_agent_options
# ===================================================================


class TestBuildSubAgentOptions:
    """build_sub_agent_options builds ClaudeCodeOptions."""

    def test_returns_claude_code_options(self):
        from bob.orchestrator.claude_executor import build_sub_agent_options
        from claude_code_sdk import ClaudeCodeOptions

        opts = build_sub_agent_options()
        assert isinstance(opts, ClaudeCodeOptions)

    def test_default_permission_mode(self):
        from bob.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options()
        assert opts.permission_mode == "bypassPermissions"

    def test_default_max_turns(self):
        from bob.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options()
        assert opts.max_turns is not None
        assert opts.max_turns > 0

    def test_custom_cwd(self, tmp_path):
        from bob.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(cwd=tmp_path)
        assert opts.cwd == str(tmp_path)

    def test_custom_model(self):
        from bob.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(model="opus")
        assert "opus" in opts.model.lower()

    def test_mcp_servers_forwarded(self):
        from bob.orchestrator.claude_executor import build_sub_agent_options

        servers = {"test-server": {"type": "stdio", "command": "echo"}}
        opts = build_sub_agent_options(mcp_servers=servers)
        assert "test-server" in opts.mcp_servers

    def test_system_prompt(self):
        from bob.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(system_prompt="You are a test agent")
        assert opts.system_prompt == "You are a test agent"

    def test_append_system_prompt(self):
        from bob.orchestrator.claude_executor import build_sub_agent_options

        opts = build_sub_agent_options(append_system_prompt="Extra context")
        assert opts.append_system_prompt == "Extra context"


# ===================================================================
# Core functionality: stream_query wrapper
# ===================================================================


class TestStreamQuery:
    """stream_query wraps claude_code_sdk.query."""

    def test_stream_query_is_async_generator(self):
        from bob.orchestrator.claude_executor import stream_query

        assert inspect.isasyncgenfunction(stream_query)


# ===================================================================
# Core functionality: MessageStreamHandler
# ===================================================================


class TestMessageStreamHandler:
    """MessageStreamHandler dispatches messages to callbacks."""

    def test_can_create_handler(self):
        from bob.orchestrator.claude_executor import MessageStreamHandler

        handler = MessageStreamHandler()
        assert handler.on_assistant_message is None
        assert handler.on_result_message is None
        assert handler.on_error is None

    def test_consume_returns_execution_result(self):
        from bob.orchestrator.claude_executor import (
            MessageStreamHandler,
            ExecutionResult,
        )
        from claude_code_sdk import ResultMessage

        async def _run():
            handler = MessageStreamHandler()

            async def _stream():
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

            result = await handler.consume(_stream())
            assert isinstance(result, ExecutionResult)
            assert result.session_id == "s1"
            return result

        asyncio.run(_run())

    def test_assistant_callback_fires(self):
        from bob.orchestrator.claude_executor import MessageStreamHandler
        from claude_code_sdk import AssistantMessage, TextBlock

        callback_called = []

        def on_assistant(msg, result):
            callback_called.append(msg)

        async def _run():
            handler = MessageStreamHandler()
            handler.on_assistant_message = on_assistant

            async def _stream():
                yield AssistantMessage(
                    content=[TextBlock(text="hi")], model="m"
                )

            await handler.consume(_stream())

        asyncio.run(_run())
        assert len(callback_called) == 1

    def test_error_callback_fires_on_error_result(self):
        from bob.orchestrator.claude_executor import MessageStreamHandler
        from claude_code_sdk import ResultMessage

        errors = []

        def on_error(msg, result):
            errors.append(msg)

        async def _run():
            handler = MessageStreamHandler()
            handler.on_error = on_error

            async def _stream():
                yield ResultMessage(
                    subtype="error",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=True,
                    num_turns=0,
                    session_id="err",
                    total_cost_usd=None,
                    usage=None,
                    result="fail",
                )

            await handler.consume(_stream())

        asyncio.run(_run())
        assert len(errors) == 1


# ===================================================================
# Core functionality: ClaudeExecutor high-level class
# ===================================================================


class TestClaudeExecutor:
    """ClaudeExecutor high-level class wraps SDK for Bob."""

    def test_can_instantiate(self):
        from bob.orchestrator.claude_executor import ClaudeExecutor

        executor = ClaudeExecutor()
        assert executor is not None

    def test_has_execute_method(self):
        from bob.orchestrator.claude_executor import ClaudeExecutor

        executor = ClaudeExecutor()
        assert hasattr(executor, "execute")
        assert asyncio.iscoroutinefunction(executor.execute)

    def test_execute_accepts_prompt_and_options(self):
        from bob.orchestrator.claude_executor import ClaudeExecutor

        sig = inspect.signature(ClaudeExecutor.execute)
        params = list(sig.parameters.keys())
        assert "prompt" in params

    def test_executor_with_custom_options(self):
        from bob.orchestrator.claude_executor import ClaudeExecutor
        from claude_code_sdk import ClaudeCodeOptions

        opts = ClaudeCodeOptions(max_turns=10, permission_mode="bypassPermissions")
        executor = ClaudeExecutor(default_options=opts)
        assert executor.default_options is opts

    @pytest.mark.asyncio
    async def test_execute_returns_execution_result(self):
        """Execute returns an ExecutionResult by consuming the SDK stream."""
        from bob.orchestrator.claude_executor import ClaudeExecutor, ExecutionResult
        from claude_code_sdk import AssistantMessage, ResultMessage, TextBlock

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Mock response")],
                model="claude-sonnet-4-5-20250929",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=500,
                duration_api_ms=400,
                is_error=False,
                num_turns=2,
                session_id="mock-sess",
                total_cost_usd=0.03,
                usage=None,
                result=None,
            )

        executor = ClaudeExecutor()
        with patch("bob.orchestrator.claude_executor.query", mock_query):
            result = await executor.execute("test prompt")

        assert isinstance(result, ExecutionResult)
        assert "Mock response" in result.text
        assert result.session_id == "mock-sess"
        assert result.num_turns == 2
        assert result.is_error is False


# ===================================================================
# Robustness: build_sub_agent_options with an unknown model name
# ===================================================================


class TestBuildSubAgentOptionsUnknownModel:
    """Unknown model names should NOT crash the orchestration. Instead,
    ``build_sub_agent_options`` falls back to ``DEFAULT_SUB_AGENT_MODEL``
    and logs a warning. Otherwise a typo or stale alias would propagate
    an unhandled ``ValueError`` and end the feature in 'executing'."""

    def test_unknown_model_falls_back_to_default(self, caplog):
        import logging as _logging

        from bob.orchestrator.claude_executor import (
            DEFAULT_SUB_AGENT_MODEL,
            MODEL_ALIASES,
            build_sub_agent_options,
        )

        with caplog.at_level(_logging.WARNING, logger="bob.orchestrator.claude_executor"):
            opts = build_sub_agent_options(model="not-a-real-model")

        # Did NOT raise; fell back to default model id.
        expected = MODEL_ALIASES[DEFAULT_SUB_AGENT_MODEL]
        assert opts.model == expected
        # Warning was logged.
        assert any(
            "not-a-real-model" in rec.getMessage() for rec in caplog.records
        ), "Expected a warning mentioning the unknown model"


# ===================================================================
# Robustness: ClaudeExecutor.execute strips parent-session env vars
# ===================================================================


class TestExecuteStripsParentSessionEnv:
    """``ClaudeExecutor.execute`` must strip Claude Code parent-session
    env vars for the duration of the SDK call. Otherwise calling
    ``.execute()`` from inside a Claude Code session leaks
    CLAUDECODE/CLAUDE_CODE_SESSION_ID into the spawned subprocess and
    triggers a nested-session conflict."""

    @pytest.mark.asyncio
    async def test_execute_strips_parent_session_env(self, monkeypatch):
        from bob.orchestrator.claude_executor import ClaudeExecutor

        # Simulate running inside a Claude Code parent session.
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-sess")
        monkeypatch.setenv("CLAUDE_CODE_IDE_WEBSOCKET_URI", "ws://x")

        seen_env: dict[str, str] = {}

        async def mock_query(*, prompt, options=None, transport=None):
            # Snapshot os.environ at the point the SDK would build its
            # subprocess env. The strip context manager must be active.
            seen_env.update(os.environ)
            from claude_code_sdk import ResultMessage
            yield ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=0,
                session_id="s",
                total_cost_usd=0.0,
                usage=None,
                result=None,
            )

        executor = ClaudeExecutor()
        with patch("bob.orchestrator.claude_executor.query", mock_query):
            await executor.execute("hi")

        # All three parent-session vars must have been stripped DURING
        # the call.
        assert "CLAUDECODE" not in seen_env
        assert "CLAUDE_CODE_SESSION_ID" not in seen_env
        assert "CLAUDE_CODE_IDE_WEBSOCKET_URI" not in seen_env

        # And restored AFTER the call.
        assert os.environ.get("CLAUDECODE") == "1"
        assert os.environ.get("CLAUDE_CODE_SESSION_ID") == "parent-sess"
        assert os.environ.get("CLAUDE_CODE_IDE_WEBSOCKET_URI") == "ws://x"
