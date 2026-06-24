"""Tests for F082: Async message streaming from Claude SDK client.

Validates that the streaming implementation:
- Step 1: Uses async for loop over SDK query responses
- Step 2: Handles AssistantMessage types (text extraction, tool use tracking)
- Step 3: Handles ResultMessage types (metadata, cost, duration)
- Step 4: Handles error messages (ResultMessage with is_error=True)
- Step 5: Full streaming integration - all message types processed correctly
"""

import asyncio
import inspect
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from claude_code_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob" / "orchestrator" / "claude_executor.py"


# ===================================================================
# Helpers
# ===================================================================


async def _make_stream(messages):
    """Create an async iterator from a list of messages."""
    for msg in messages:
        yield msg


# ===================================================================
# Step 1: Async for loop over SDK query responses
# ===================================================================


class TestAsyncStreamLoop:
    """Step 1: stream_query uses async for over sdk query."""

    def test_stream_query_is_async_generator(self):
        from bob.orchestrator.claude_executor import stream_query

        assert inspect.isasyncgenfunction(stream_query)

    def test_stream_query_yields_messages(self):
        from bob.orchestrator.claude_executor import stream_query

        messages = [
            AssistantMessage(
                content=[TextBlock(text="hello")], model="test-model"
            ),
            ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            ),
        ]

        async def mock_query(*, prompt, options=None, transport=None):
            for m in messages:
                yield m

        async def _run():
            collected = []
            with patch("bob.orchestrator.claude_executor.query", mock_query):
                async for msg in stream_query("test"):
                    collected.append(msg)
            return collected

        collected = asyncio.run(_run())
        assert len(collected) == 2
        assert isinstance(collected[0], AssistantMessage)
        assert isinstance(collected[1], ResultMessage)

    def test_stream_query_preserves_message_order(self):
        from bob.orchestrator.claude_executor import stream_query

        messages = [
            AssistantMessage(
                content=[TextBlock(text="first")], model="m"
            ),
            AssistantMessage(
                content=[TextBlock(text="second")], model="m"
            ),
            AssistantMessage(
                content=[TextBlock(text="third")], model="m"
            ),
            ResultMessage(
                subtype="success",
                duration_ms=200,
                duration_api_ms=180,
                is_error=False,
                num_turns=3,
                session_id="s2",
                total_cost_usd=0.02,
                usage=None,
                result=None,
            ),
        ]

        async def mock_query(*, prompt, options=None, transport=None):
            for m in messages:
                yield m

        async def _run():
            texts = []
            with patch("bob.orchestrator.claude_executor.query", mock_query):
                async for msg in stream_query("test"):
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                texts.append(block.text)
            return texts

        texts = asyncio.run(_run())
        assert texts == ["first", "second", "third"]

    def test_stream_query_handles_empty_stream(self):
        from bob.orchestrator.claude_executor import stream_query

        async def mock_query(*, prompt, options=None, transport=None):
            return
            yield  # noqa: unreachable - makes this an async generator

        async def _run():
            collected = []
            with patch("bob.orchestrator.claude_executor.query", mock_query):
                async for msg in stream_query("test"):
                    collected.append(msg)
            return collected

        collected = asyncio.run(_run())
        assert collected == []


# ===================================================================
# Step 2: Handle AssistantMessage types
# ===================================================================


class TestAssistantMessageHandling:
    """Step 2: AssistantMessage text extraction and tool tracking."""

    def test_text_blocks_extracted(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = AssistantMessage(
            content=[TextBlock(text="Hello world")], model="test"
        )
        process_message(msg, result)
        assert result.text == "Hello world"

    def test_multiple_text_blocks_joined(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = AssistantMessage(
            content=[
                TextBlock(text="Line 1"),
                TextBlock(text="Line 2"),
            ],
            model="test",
        )
        process_message(msg, result)
        assert "Line 1" in result.text
        assert "Line 2" in result.text

    def test_tool_use_blocks_tracked(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = AssistantMessage(
            content=[
                ToolUseBlock(id="tu1", name="Bash", input={"command": "ls"}),
                ToolUseBlock(id="tu2", name="Read", input={"file_path": "/tmp"}),
            ],
            model="test",
        )
        process_message(msg, result)
        assert "Bash" in result.tool_uses
        assert "Read" in result.tool_uses

    def test_mixed_content_blocks(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = AssistantMessage(
            content=[
                TextBlock(text="Let me check"),
                ToolUseBlock(id="tu1", name="Bash", input={"command": "ls"}),
                TextBlock(text="Found the file"),
            ],
            model="test",
        )
        process_message(msg, result)
        assert "Let me check" in result.text
        assert "Found the file" in result.text
        assert "Bash" in result.tool_uses

    def test_consecutive_assistant_messages_accumulate(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        process_message(
            AssistantMessage(content=[TextBlock(text="First")], model="m"),
            result,
        )
        process_message(
            AssistantMessage(content=[TextBlock(text="Second")], model="m"),
            result,
        )
        assert "First" in result.text
        assert "Second" in result.text

    def test_assistant_message_appended_to_messages_list(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = AssistantMessage(
            content=[TextBlock(text="tracked")], model="test"
        )
        process_message(msg, result)
        assert msg in result.messages

    def test_empty_content_blocks_handled(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = AssistantMessage(content=[], model="test")
        process_message(msg, result)
        assert result.text == ""
        assert result.tool_uses == []


# ===================================================================
# Step 3: Handle ResultMessage types
# ===================================================================


class TestResultMessageHandling:
    """Step 3: ResultMessage metadata, cost, and duration handling."""

    def test_success_result_populates_metadata(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="success",
            duration_ms=5000,
            duration_api_ms=4500,
            is_error=False,
            num_turns=10,
            session_id="session-abc",
            total_cost_usd=0.25,
            usage=None,
            result=None,
        )
        process_message(msg, result)

        assert result.duration_ms == 5000
        assert result.num_turns == 10
        assert result.session_id == "session-abc"
        assert result.total_cost_usd == 0.25
        assert result.is_error is False

    def test_result_message_appended_to_messages_list(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = ResultMessage(
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
        process_message(msg, result)
        assert msg in result.messages

    def test_result_with_none_cost(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="s1",
            total_cost_usd=None,
            usage=None,
            result=None,
        )
        process_message(msg, result)
        assert result.total_cost_usd is None

    def test_result_overwrites_previous_metadata(self):
        """If multiple ResultMessages arrive, the last one wins."""
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg1 = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="first",
            total_cost_usd=0.01,
            usage=None,
            result=None,
        )
        msg2 = ResultMessage(
            subtype="success",
            duration_ms=200,
            duration_api_ms=180,
            is_error=False,
            num_turns=3,
            session_id="second",
            total_cost_usd=0.05,
            usage=None,
            result=None,
        )
        process_message(msg1, result)
        process_message(msg2, result)
        assert result.session_id == "second"
        assert result.duration_ms == 200
        assert result.num_turns == 3


# ===================================================================
# Step 4: Handle error messages (ResultMessage with is_error=True)
# ===================================================================


class TestErrorMessageHandling:
    """Step 4: Error handling via ResultMessage with is_error=True.

    The Claude SDK does not have a separate ErrorMessage type.
    Errors are conveyed through ResultMessage with is_error=True.
    """

    def test_error_result_sets_is_error(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="error",
            duration_ms=500,
            duration_api_ms=400,
            is_error=True,
            num_turns=1,
            session_id="err-sess",
            total_cost_usd=0.01,
            usage=None,
            result="Rate limit exceeded",
        )
        process_message(msg, result)
        assert result.is_error is True

    def test_error_result_captures_error_message(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="error",
            duration_ms=500,
            duration_api_ms=400,
            is_error=True,
            num_turns=1,
            session_id="err-sess",
            total_cost_usd=0.01,
            usage=None,
            result="Connection timed out",
        )
        process_message(msg, result)
        assert result.error_message == "Connection timed out"

    def test_error_result_still_records_metadata(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="error",
            duration_ms=300,
            duration_api_ms=250,
            is_error=True,
            num_turns=2,
            session_id="err-meta",
            total_cost_usd=0.03,
            usage=None,
            result="API error",
        )
        process_message(msg, result)
        assert result.duration_ms == 300
        assert result.num_turns == 2
        assert result.session_id == "err-meta"
        assert result.total_cost_usd == 0.03

    def test_error_with_none_result_no_error_message(self):
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            process_message,
        )

        result = ExecutionResult()
        msg = ResultMessage(
            subtype="error",
            duration_ms=100,
            duration_api_ms=80,
            is_error=True,
            num_turns=0,
            session_id="err-none",
            total_cost_usd=None,
            usage=None,
            result=None,
        )
        process_message(msg, result)
        assert result.is_error is True
        assert result.error_message == ""

    def test_error_callback_fires_on_error_result(self):
        from bob.orchestrator.claude_executor import MessageStreamHandler

        errors_seen = []

        def on_error(msg, result):
            errors_seen.append(msg)

        async def _run():
            handler = MessageStreamHandler()
            handler.on_error = on_error

            messages = [
                ResultMessage(
                    subtype="error",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=True,
                    num_turns=0,
                    session_id="err",
                    total_cost_usd=None,
                    usage=None,
                    result="boom",
                ),
            ]
            await handler.consume(_make_stream(messages))

        asyncio.run(_run())
        assert len(errors_seen) == 1

    def test_error_callback_not_fired_on_success(self):
        from bob.orchestrator.claude_executor import MessageStreamHandler

        errors_seen = []

        def on_error(msg, result):
            errors_seen.append(msg)

        async def _run():
            handler = MessageStreamHandler()
            handler.on_error = on_error

            messages = [
                ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="ok",
                    total_cost_usd=0.01,
                    usage=None,
                    result=None,
                ),
            ]
            await handler.consume(_make_stream(messages))

        asyncio.run(_run())
        assert len(errors_seen) == 0


# ===================================================================
# Step 5: Full streaming integration - all types handled
# ===================================================================


class TestStreamingIntegration:
    """Step 5: End-to-end streaming with all message types."""

    def test_full_conversation_stream(self):
        """Simulate a full agent conversation with mixed message types."""
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            MessageStreamHandler,
        )

        messages = [
            SystemMessage(subtype="init", data={"session": "test"}),
            AssistantMessage(
                content=[TextBlock(text="I'll help with that.")],
                model="test-model",
            ),
            AssistantMessage(
                content=[
                    TextBlock(text="Let me run a command."),
                    ToolUseBlock(id="tu1", name="Bash", input={"command": "ls"}),
                ],
                model="test-model",
            ),
            UserMessage(content="Tool result: file1.py file2.py"),
            AssistantMessage(
                content=[TextBlock(text="I found the files.")],
                model="test-model",
            ),
            ResultMessage(
                subtype="success",
                duration_ms=3000,
                duration_api_ms=2800,
                is_error=False,
                num_turns=5,
                session_id="full-sess",
                total_cost_usd=0.15,
                usage=None,
                result=None,
            ),
        ]

        async def _run():
            handler = MessageStreamHandler()
            result = await handler.consume(_make_stream(messages))
            return result

        result = asyncio.run(_run())

        # Text accumulated from AssistantMessages
        assert "I'll help with that." in result.text
        assert "Let me run a command." in result.text
        assert "I found the files." in result.text

        # Tool uses tracked
        assert "Bash" in result.tool_uses

        # Metadata from ResultMessage
        assert result.duration_ms == 3000
        assert result.num_turns == 5
        assert result.session_id == "full-sess"
        assert result.total_cost_usd == 0.15
        assert result.is_error is False

        # All messages recorded
        assert len(result.messages) == 6

    def test_error_conversation_stream(self):
        """Simulate a conversation that ends in error."""
        from bob.orchestrator.claude_executor import (
            ExecutionResult,
            MessageStreamHandler,
        )

        messages = [
            AssistantMessage(
                content=[TextBlock(text="Starting work...")],
                model="test-model",
            ),
            ResultMessage(
                subtype="error",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=True,
                num_turns=1,
                session_id="err-sess",
                total_cost_usd=0.02,
                usage=None,
                result="Context window exceeded",
            ),
        ]

        async def _run():
            handler = MessageStreamHandler()
            result = await handler.consume(_make_stream(messages))
            return result

        result = asyncio.run(_run())

        assert "Starting work..." in result.text
        assert result.is_error is True
        assert result.error_message == "Context window exceeded"
        assert result.session_id == "err-sess"
        assert len(result.messages) == 2

    def test_executor_streams_full_conversation(self):
        """ClaudeExecutor.execute consumes stream and returns result."""
        from bob.orchestrator.claude_executor import (
            ClaudeExecutor,
            ExecutionResult,
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="Streaming response")],
                model="test-model",
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1800,
                is_error=False,
                num_turns=4,
                session_id="exec-sess",
                total_cost_usd=0.10,
                usage=None,
                result=None,
            )

        async def _run():
            executor = ClaudeExecutor()
            with patch("bob.orchestrator.claude_executor.query", mock_query):
                result = await executor.execute("Stream test")
            return result

        result = asyncio.run(_run())
        assert isinstance(result, ExecutionResult)
        assert "Streaming response" in result.text
        assert result.session_id == "exec-sess"
        assert result.num_turns == 4
        assert result.is_error is False

    def test_executor_handles_error_stream(self):
        """ClaudeExecutor.execute handles error results from stream."""
        from bob.orchestrator.claude_executor import (
            ClaudeExecutor,
            ExecutionResult,
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="error",
                duration_ms=500,
                duration_api_ms=400,
                is_error=True,
                num_turns=0,
                session_id="exec-err",
                total_cost_usd=0.005,
                usage=None,
                result="Authentication failed",
            )

        async def _run():
            executor = ClaudeExecutor()
            with patch("bob.orchestrator.claude_executor.query", mock_query):
                result = await executor.execute("Error test")
            return result

        result = asyncio.run(_run())
        assert isinstance(result, ExecutionResult)
        assert result.is_error is True
        assert result.error_message == "Authentication failed"

    def test_handler_callback_receives_all_types(self):
        """MessageStreamHandler fires correct callbacks per type."""
        from bob.orchestrator.claude_executor import MessageStreamHandler

        assistant_msgs = []
        result_msgs = []
        error_msgs = []
        system_msgs = []
        user_msgs = []
        any_msgs = []

        def on_assistant(msg, result):
            assistant_msgs.append(msg)

        def on_result(msg, result):
            result_msgs.append(msg)

        def on_error(msg, result):
            error_msgs.append(msg)

        def on_system(msg, result):
            system_msgs.append(msg)

        def on_user(msg, result):
            user_msgs.append(msg)

        def on_any(msg, result):
            any_msgs.append(msg)

        messages = [
            SystemMessage(subtype="init", data={}),
            AssistantMessage(
                content=[TextBlock(text="hello")], model="m"
            ),
            UserMessage(content="tool output"),
            AssistantMessage(
                content=[TextBlock(text="goodbye")], model="m"
            ),
            ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=2,
                session_id="cb",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            ),
        ]

        async def _run():
            handler = MessageStreamHandler()
            handler.on_assistant_message = on_assistant
            handler.on_result_message = on_result
            handler.on_error = on_error
            handler.on_system_message = on_system
            handler.on_user_message = on_user
            handler.on_any_message = on_any
            await handler.consume(_make_stream(messages))

        asyncio.run(_run())

        assert len(assistant_msgs) == 2
        assert len(result_msgs) == 1
        assert len(error_msgs) == 0  # no error in this stream
        assert len(system_msgs) == 1
        assert len(user_msgs) == 1
        assert len(any_msgs) == 5  # all messages

    def test_async_callbacks_supported(self):
        """MessageStreamHandler supports async callbacks."""
        from bob.orchestrator.claude_executor import MessageStreamHandler

        called = []

        async def async_callback(msg, result):
            called.append("async")

        messages = [
            AssistantMessage(
                content=[TextBlock(text="async test")], model="m"
            ),
        ]

        async def _run():
            handler = MessageStreamHandler()
            handler.on_assistant_message = async_callback
            await handler.consume(_make_stream(messages))

        asyncio.run(_run())
        assert called == ["async"]

    def test_on_message_callback_in_executor(self):
        """ClaudeExecutor.execute passes on_message callback through."""
        from bob.orchestrator.claude_executor import ClaudeExecutor

        seen = []

        def on_message(msg, result):
            seen.append(type(msg).__name__)

        async def mock_query(*, prompt, options=None, transport=None):
            yield AssistantMessage(
                content=[TextBlock(text="test")], model="m"
            )
            yield ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="cb-sess",
                total_cost_usd=0.01,
                usage=None,
                result=None,
            )

        async def _run():
            executor = ClaudeExecutor()
            with patch("bob.orchestrator.claude_executor.query", mock_query):
                await executor.execute("callback test", on_message=on_message)

        asyncio.run(_run())
        assert "AssistantMessage" in seen
        assert "ResultMessage" in seen
