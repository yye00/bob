"""Tests for F016: TITANS Memory MCP integration.

Validates that the titans_memory_client module:
- Step 1: Provides titans_memory_client.py wrapper module
- Step 2: Implements add_memory(content, pool) using titans_add
- Step 3: Implements search_memory(query, pool) using titans_search
- Step 4: Implements record_feedback(memory_id, success) using titans_record_feedback
- Step 5: Tests the memory add/search/feedback cycle
- Step 6: Verifies memories persist across sessions (client re-creation)
"""

import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob3" / "titans_memory_client.py"


# ===================================================================
# Step 1: Module exists and is importable
# ===================================================================


class TestModuleExists:
    """Step 1: src/bob3/titans_memory_client.py must exist and be importable."""

    def test_module_file_exists(self):
        assert MODULE_PATH.is_file(), f"Expected {MODULE_PATH} to exist"

    def test_module_is_non_empty(self):
        content = MODULE_PATH.read_text()
        assert len(content.strip()) > 200, "Module appears to be a stub"

    def test_module_is_importable(self):
        import bob3.titans_memory_client

        assert bob3.titans_memory_client is not None

    def test_titans_memory_client_class_exists(self):
        from bob3.titans_memory_client import TitansMemoryClient

        assert TitansMemoryClient is not None

    def test_memory_result_class_exists(self):
        from bob3.titans_memory_client import MemoryResult

        assert MemoryResult is not None

    def test_valid_pools_constant_exists(self):
        from bob3.titans_memory_client import VALID_POOLS

        assert isinstance(VALID_POOLS, (set, frozenset))
        assert "facts" in VALID_POOLS
        assert "preferences" in VALID_POOLS
        assert "lessons" in VALID_POOLS
        assert "context" in VALID_POOLS

    def test_tool_name_constants_exist(self):
        from bob3.titans_memory_client import (
            TOOL_TITANS_ADD,
            TOOL_TITANS_RECORD_FEEDBACK,
            TOOL_TITANS_SEARCH,
        )

        assert "titans_add" in TOOL_TITANS_ADD
        assert "titans_search" in TOOL_TITANS_SEARCH
        assert "titans_record_feedback" in TOOL_TITANS_RECORD_FEEDBACK

    def test_route_to_pool_function_exists(self):
        from bob3.titans_memory_client import route_to_pool

        assert callable(route_to_pool)


# ===================================================================
# Step 2: add_memory(content, pool) using titans_add
# ===================================================================


class TestAddMemory:
    """Step 2: add_memory() must call titans_add MCP tool via sub-agent."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test-workspace")

    @pytest.fixture
    def mock_execute(self):
        """Patch _execute_tool_prompt to return a successful MemoryResult."""
        from bob3.titans_memory_client import MemoryResult

        async def fake_execute(prompt):
            return MemoryResult(
                success=True,
                data={"id": "mem-123", "content": "test content", "metadata": {"pool": "facts"}},
                raw_text='{"id": "mem-123"}',
            )

        return fake_execute

    @pytest.mark.asyncio
    async def test_add_memory_calls_execute_tool_prompt(self, client, mock_execute):
        with patch.object(client, "_execute_tool_prompt", side_effect=mock_execute) as mock:
            result = await client.add_memory(content="Test memory", pool="facts")
            mock.assert_called_once()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_add_memory_prompt_contains_titans_add_tool(self, client, mock_execute):
        from bob3.titans_memory_client import TOOL_TITANS_ADD

        prompts_seen = []

        async def capture_prompt(prompt):
            prompts_seen.append(prompt)
            return mock_execute(prompt)

        # Need to actually await mock_execute
        from bob3.titans_memory_client import MemoryResult

        async def capture_and_return(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(
                success=True,
                data={"id": "mem-123"},
                raw_text="{}",
            )

        with patch.object(client, "_execute_tool_prompt", side_effect=capture_and_return):
            await client.add_memory(content="Test memory", pool="facts")

        assert len(prompts_seen) == 1
        assert TOOL_TITANS_ADD in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_add_memory_prompt_contains_content(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={"id": "mem-1"}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.add_memory(content="SQLite WAL mode improves reads", pool="facts")

        assert "SQLite WAL mode improves reads" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_add_memory_prompt_contains_pool(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={"id": "mem-1"}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.add_memory(content="test", pool="lessons")

        assert "lessons" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_add_memory_with_metadata(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={"id": "mem-1"}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.add_memory(
                content="test",
                pool="facts",
                metadata={"feature_id": "F016"},
            )

        assert "feature_id" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_add_memory_without_pool(self, client):
        """When no pool is specified, titans_add still works (auto-route)."""
        from bob3.titans_memory_client import MemoryResult

        async def fake(prompt):
            return MemoryResult(success=True, data={"id": "mem-1"}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=fake):
            result = await client.add_memory(content="something general")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_add_memory_invalid_pool_raises(self, client):
        with pytest.raises(ValueError, match="Invalid memory pool"):
            await client.add_memory(content="test", pool="invalid_pool")

    @pytest.mark.asyncio
    async def test_add_memory_returns_memory_result(self, client):
        from bob3.titans_memory_client import MemoryResult

        async def fake(prompt):
            return MemoryResult(
                success=True,
                data={"id": "mem-abc", "content": "hello"},
                raw_text='{"id": "mem-abc"}',
            )

        with patch.object(client, "_execute_tool_prompt", side_effect=fake):
            result = await client.add_memory(content="hello", pool="facts")

        assert isinstance(result, MemoryResult)
        assert result.success is True
        assert result.data["id"] == "mem-abc"


# ===================================================================
# Step 3: search_memory(query, pool) using titans_search
# ===================================================================


class TestSearchMemory:
    """Step 3: search_memory() must call titans_search or titans_search_pool."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test-workspace")

    @pytest.mark.asyncio
    async def test_search_memory_calls_execute_tool_prompt(self, client):
        from bob3.titans_memory_client import MemoryResult

        async def fake(prompt):
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=fake) as mock:
            result = await client.search_memory(query="test query")
            mock.assert_called_once()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_search_memory_without_pool_uses_titans_search(self, client):
        from bob3.titans_memory_client import TOOL_TITANS_SEARCH, MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.search_memory(query="SQLite concurrency")

        assert TOOL_TITANS_SEARCH in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_search_memory_with_pool_uses_titans_search_pool(self, client):
        from bob3.titans_memory_client import TOOL_TITANS_SEARCH_POOL, MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.search_memory(query="SQLite concurrency", pool="facts")

        assert TOOL_TITANS_SEARCH_POOL in prompts_seen[0]
        assert "facts" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_search_memory_prompt_contains_query(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.search_memory(query="WAL mode performance")

        assert "WAL mode performance" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_search_memory_prompt_contains_limit(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.search_memory(query="test", limit=5)

        assert "5" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_search_memory_returns_list_data(self, client):
        from bob3.titans_memory_client import MemoryResult

        mock_results = [
            {"id": "mem-1", "content": "first result", "retrieval_weight": 0.9},
            {"id": "mem-2", "content": "second result", "retrieval_weight": 0.7},
        ]

        async def fake(prompt):
            return MemoryResult(success=True, data=mock_results, raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=fake):
            result = await client.search_memory(query="test")

        assert isinstance(result.data, list)
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_search_memory_invalid_pool_raises(self, client):
        with pytest.raises(ValueError, match="Invalid memory pool"):
            await client.search_memory(query="test", pool="not_a_pool")


# ===================================================================
# Step 4: record_feedback(memory_id, success) using titans_record_feedback
# ===================================================================


class TestRecordFeedback:
    """Step 4: record_feedback() must call titans_record_feedback MCP tool."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test-workspace")

    @pytest.mark.asyncio
    async def test_record_feedback_calls_execute_tool_prompt(self, client):
        from bob3.titans_memory_client import MemoryResult

        async def fake(prompt):
            return MemoryResult(
                success=True,
                data={"id": "mem-1", "metadata": {"usefulness_score": 0.8}},
                raw_text="{}",
            )

        with patch.object(client, "_execute_tool_prompt", side_effect=fake) as mock:
            result = await client.record_feedback(memory_id="mem-1", success=True)
            mock.assert_called_once()
            assert result.success is True

    @pytest.mark.asyncio
    async def test_record_feedback_prompt_contains_tool_name(self, client):
        from bob3.titans_memory_client import TOOL_TITANS_RECORD_FEEDBACK, MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.record_feedback(memory_id="mem-abc", success=True)

        assert TOOL_TITANS_RECORD_FEEDBACK in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_record_feedback_prompt_contains_memory_id(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.record_feedback(memory_id="mem-xyz-123", success=False)

        assert "mem-xyz-123" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_record_feedback_success_true(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.record_feedback(memory_id="mem-1", success=True)

        assert "true" in prompts_seen[0].lower()

    @pytest.mark.asyncio
    async def test_record_feedback_success_false(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.record_feedback(memory_id="mem-1", success=False)

        assert "false" in prompts_seen[0].lower()


# ===================================================================
# Step 5: Test memory add/search/feedback cycle
# ===================================================================


class TestMemoryCycle:
    """Step 5: Full add -> search -> feedback cycle works end-to-end."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test-workspace")

    @pytest.mark.asyncio
    async def test_add_then_search_then_feedback_cycle(self, client):
        """Simulates a complete memory lifecycle: add, search, feedback."""
        from bob3.titans_memory_client import MemoryResult

        call_sequence = []

        async def track_calls(prompt):
            call_sequence.append(prompt)
            # Return appropriate data based on which tool is being called
            if "titans_add" in prompt:
                return MemoryResult(
                    success=True,
                    data={"id": "mem-cycle-1", "content": "WAL mode lesson"},
                    raw_text="{}",
                )
            elif "titans_search" in prompt:
                return MemoryResult(
                    success=True,
                    data=[{"id": "mem-cycle-1", "content": "WAL mode lesson", "retrieval_weight": 0.8}],
                    raw_text="[]",
                )
            elif "titans_record_feedback" in prompt:
                return MemoryResult(
                    success=True,
                    data={"id": "mem-cycle-1", "metadata": {"usefulness_score": 0.85}},
                    raw_text="{}",
                )
            return MemoryResult(success=False, error="unexpected tool call")

        with patch.object(client, "_execute_tool_prompt", side_effect=track_calls):
            # Step A: Add a memory
            add_result = await client.add_memory(
                content="WAL mode lesson",
                pool="lessons",
            )
            assert add_result.success is True
            assert add_result.data["id"] == "mem-cycle-1"

            # Step B: Search for the memory
            search_result = await client.search_memory(
                query="WAL mode",
                pool="lessons",
            )
            assert search_result.success is True
            assert isinstance(search_result.data, list)
            assert len(search_result.data) >= 1

            # Step C: Record positive feedback on the found memory
            memory_id = search_result.data[0]["id"]
            feedback_result = await client.record_feedback(
                memory_id=memory_id,
                success=True,
            )
            assert feedback_result.success is True

        # Verify all three operations were called
        assert len(call_sequence) == 3
        assert "titans_add" in call_sequence[0]
        assert "titans_search" in call_sequence[1]
        assert "titans_record_feedback" in call_sequence[2]


# ===================================================================
# Step 6: Verify memories persist across sessions (client re-creation)
# ===================================================================


class TestPersistenceAcrossSessions:
    """Step 6: Memories should persist when a new client is created."""

    @pytest.mark.asyncio
    async def test_memory_accessible_from_new_client(self):
        """A memory added by one client should be searchable by another."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        # Simulated shared memory store
        stored_memories = []

        async def session1_execute(prompt):
            if "titans_add" in prompt:
                memory = {"id": "persist-1", "content": "important lesson"}
                stored_memories.append(memory)
                return MemoryResult(success=True, data=memory, raw_text="{}")
            return MemoryResult(success=False, error="unexpected")

        async def session2_execute(prompt):
            if "titans_search" in prompt:
                # Return the memory that was added in session 1
                return MemoryResult(
                    success=True,
                    data=stored_memories.copy(),
                    raw_text="[]",
                )
            return MemoryResult(success=False, error="unexpected")

        # Session 1: Add a memory
        client1 = TitansMemoryClient(workspace="/tmp/session1")
        with patch.object(client1, "_execute_tool_prompt", side_effect=session1_execute):
            add_result = await client1.add_memory(
                content="important lesson",
                pool="lessons",
            )
            assert add_result.success is True

        # Session 2: New client searches for same memory
        client2 = TitansMemoryClient(workspace="/tmp/session2")
        with patch.object(client2, "_execute_tool_prompt", side_effect=session2_execute):
            search_result = await client2.search_memory(
                query="important lesson",
                pool="lessons",
            )
            assert search_result.success is True
            assert isinstance(search_result.data, list)
            assert len(search_result.data) >= 1
            assert search_result.data[0]["id"] == "persist-1"

    @pytest.mark.asyncio
    async def test_client_is_stateless_wrapper(self):
        """TitansMemoryClient should be a stateless wrapper - no local cache."""
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        # Client should have no memory storage attributes
        assert not hasattr(client, "_cache")
        assert not hasattr(client, "_memories")
        assert not hasattr(client, "_store")


# ===================================================================
# Helper function tests
# ===================================================================


class TestRouteToPool:
    """Tests for the route_to_pool() local classifier."""

    def test_routes_api_content_to_facts(self):
        from bob3.titans_memory_client import route_to_pool

        result = route_to_pool("The API endpoint returns a JSON response")
        assert result == "facts"

    def test_routes_bug_content_to_lessons(self):
        from bob3.titans_memory_client import route_to_pool

        result = route_to_pool("Bug fix: the error was caused by a missing import")
        assert result == "lessons"

    def test_routes_convention_content_to_preferences(self):
        from bob3.titans_memory_client import route_to_pool

        result = route_to_pool("Always use snake_case naming convention for functions")
        assert result == "preferences"

    def test_routes_progress_content_to_context(self):
        from bob3.titans_memory_client import route_to_pool

        result = route_to_pool("Current session progress: working on feature F016")
        assert result == "context"

    def test_empty_content_defaults_to_context(self):
        from bob3.titans_memory_client import route_to_pool

        assert route_to_pool("") == "context"
        assert route_to_pool("   ") == "context"

    def test_ambiguous_content_uses_priority(self):
        from bob3.titans_memory_client import route_to_pool

        # Content with no clear matches defaults to context
        result = route_to_pool("something completely unrelated to any keywords")
        assert result == "context"


class TestValidatePool:
    """Tests for pool validation."""

    def test_valid_pools_accepted(self):
        from bob3.titans_memory_client import _validate_pool

        _validate_pool("facts")
        _validate_pool("preferences")
        _validate_pool("lessons")
        _validate_pool("context")
        _validate_pool(None)  # None = auto-route

    def test_invalid_pool_raises(self):
        from bob3.titans_memory_client import _validate_pool

        with pytest.raises(ValueError, match="Invalid memory pool"):
            _validate_pool("nonexistent")


class TestExtractJsonFromText:
    """Tests for the JSON extraction helper."""

    def test_extracts_raw_json(self):
        from bob3.titans_memory_client import _extract_json_from_text

        result = _extract_json_from_text('{"id": "mem-1", "content": "hello"}')
        assert result == {"id": "mem-1", "content": "hello"}

    def test_extracts_json_from_code_fence(self):
        from bob3.titans_memory_client import _extract_json_from_text

        text = 'Here is the result:\n```json\n{"id": "mem-2"}\n```\nDone.'
        result = _extract_json_from_text(text)
        assert result == {"id": "mem-2"}

    def test_extracts_json_array(self):
        from bob3.titans_memory_client import _extract_json_from_text

        text = '[{"id": "mem-1"}, {"id": "mem-2"}]'
        result = _extract_json_from_text(text)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_extracts_embedded_json(self):
        from bob3.titans_memory_client import _extract_json_from_text

        text = 'The result is {"id": "mem-3"} as expected.'
        result = _extract_json_from_text(text)
        assert result == {"id": "mem-3"}

    def test_returns_none_for_no_json(self):
        from bob3.titans_memory_client import _extract_json_from_text

        result = _extract_json_from_text("No JSON here at all")
        assert result is None

    def test_returns_none_for_empty_string(self):
        from bob3.titans_memory_client import _extract_json_from_text

        result = _extract_json_from_text("")
        assert result is None


class TestMemoryResult:
    """Tests for the MemoryResult dataclass."""

    def test_default_values(self):
        from bob3.titans_memory_client import MemoryResult

        r = MemoryResult(success=True)
        assert r.success is True
        assert r.data is None
        assert r.error == ""
        assert r.raw_text == ""

    def test_success_with_data(self):
        from bob3.titans_memory_client import MemoryResult

        r = MemoryResult(success=True, data={"id": "x"})
        assert r.data == {"id": "x"}

    def test_failure_with_error(self):
        from bob3.titans_memory_client import MemoryResult

        r = MemoryResult(success=False, error="connection failed")
        assert r.success is False
        assert "connection" in r.error


class TestClientConstruction:
    """Tests for TitansMemoryClient construction and configuration."""

    def test_client_accepts_workspace(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/some/path")
        assert client.workspace == "/some/path"

    def test_client_accepts_pathlib_workspace(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace=pathlib.Path("/some/path"))
        assert client.workspace == "/some/path"

    def test_client_default_max_turns(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp")
        assert client.max_turns == 3

    def test_client_custom_max_turns(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp", max_turns=5)
        assert client.max_turns == 5


class TestExecuteToolPrompt:
    """Tests for the _execute_tool_prompt internal method."""

    @pytest.mark.asyncio
    async def test_handles_executor_exception(self):
        """_execute_tool_prompt should catch and wrap executor errors."""
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp")

        with patch.object(client, "_build_executor") as mock_build:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
            mock_build.return_value = mock_executor

            result = await client._execute_tool_prompt("test prompt")
            assert result.success is False
            assert "connection lost" in result.error

    @pytest.mark.asyncio
    async def test_handles_error_result(self):
        """_execute_tool_prompt should detect is_error from executor result."""
        from bob3.orchestrator.claude_executor import ExecutionResult
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp")

        exec_result = ExecutionResult(
            text="Error occurred",
            is_error=True,
            error_message="Tool not found",
        )

        with patch.object(client, "_build_executor") as mock_build:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=exec_result)
            mock_build.return_value = mock_executor

            result = await client._execute_tool_prompt("test prompt")
            assert result.success is False
            assert "Tool not found" in result.error

    @pytest.mark.asyncio
    async def test_parses_json_from_successful_result(self):
        """_execute_tool_prompt should parse JSON from successful text."""
        from bob3.orchestrator.claude_executor import ExecutionResult
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp")

        exec_result = ExecutionResult(
            text='{"id": "mem-ok", "content": "hello"}',
            is_error=False,
        )

        with patch.object(client, "_build_executor") as mock_build:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=exec_result)
            mock_build.return_value = mock_executor

            result = await client._execute_tool_prompt("test prompt")
            assert result.success is True
            assert result.data == {"id": "mem-ok", "content": "hello"}

    @pytest.mark.asyncio
    async def test_returns_raw_text_when_no_json(self):
        """If no JSON found, return raw text as data (still success)."""
        from bob3.orchestrator.claude_executor import ExecutionResult
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp")

        exec_result = ExecutionResult(
            text="Memory was added successfully.",
            is_error=False,
        )

        with patch.object(client, "_build_executor") as mock_build:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=exec_result)
            mock_build.return_value = mock_executor

            result = await client._execute_tool_prompt("test prompt")
            assert result.success is True
            assert result.data == "Memory was added successfully."

    @pytest.mark.asyncio
    async def test_returns_failure_on_empty_response(self):
        """Empty response from executor should return failure."""
        from bob3.orchestrator.claude_executor import ExecutionResult
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp")

        exec_result = ExecutionResult(text="", is_error=False)

        with patch.object(client, "_build_executor") as mock_build:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=exec_result)
            mock_build.return_value = mock_executor

            result = await client._execute_tool_prompt("test prompt")
            assert result.success is False
            assert "Empty response" in result.error


class TestBuildExecutor:
    """Tests for _build_executor which configures the ClaudeExecutor."""

    def test_build_executor_returns_claude_executor(self):
        from bob3.orchestrator.claude_executor import ClaudeExecutor
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        executor = client._build_executor()
        assert isinstance(executor, ClaudeExecutor)

    def test_build_executor_configures_options(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        executor = client._build_executor()
        # Executor should have default_options set with MCP config
        assert executor.default_options is not None
