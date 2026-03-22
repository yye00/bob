"""Tests for F041: Implement lesson storage in TITANS memory.

Validates that the store_lesson() function:
- Step 1: Add store_lesson() function using titans_add
- Step 2: Format: trigger_context + lesson + solution
- Step 3: Route to 'lessons' pool explicitly
- Step 4: Include metadata: feature_id, error_type, fix_action
- Step 5: Test: Create lesson, search for it, verify in lessons pool
"""

from unittest.mock import patch

import pytest


# ===================================================================
# Step 1: store_lesson() function exists and uses titans_add
# ===================================================================


class TestStoreLessonExists:
    """Step 1: store_lesson() must exist on TitansMemoryClient and use titans_add."""

    def test_store_lesson_method_exists(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert hasattr(client, "store_lesson")
        assert callable(client.store_lesson)

    def test_store_lesson_is_async(self):
        import inspect

        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert inspect.iscoroutinefunction(client.store_lesson)

    @pytest.mark.asyncio
    async def test_store_lesson_delegates_to_add_memory(self):
        """store_lesson() should internally call add_memory() with pool='lessons'."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        add_memory_calls = []

        async def capture_add_memory(content, pool=None, metadata=None):
            add_memory_calls.append(
                {"content": content, "pool": pool, "metadata": metadata}
            )
            return MemoryResult(
                success=True,
                data={"id": "mem-lesson-1", "content": content},
                raw_text="{}",
            )

        with patch.object(client, "add_memory", side_effect=capture_add_memory):
            result = await client.store_lesson(
                trigger_context="Test trigger",
                lesson="Test lesson",
                solution="Test solution",
            )

        assert result.success is True
        assert len(add_memory_calls) == 1

    @pytest.mark.asyncio
    async def test_store_lesson_uses_titans_add_tool(self):
        """store_lesson() must ultimately call titans_add via the sub-agent."""
        from bob3.titans_memory_client import (
            TOOL_TITANS_ADD,
            MemoryResult,
            TitansMemoryClient,
        )

        client = TitansMemoryClient(workspace="/tmp/test")
        prompts_seen = []

        async def capture_prompt(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(
                success=True,
                data={"id": "mem-lesson-1"},
                raw_text="{}",
            )

        with patch.object(
            client, "_execute_tool_prompt", side_effect=capture_prompt
        ):
            await client.store_lesson(
                trigger_context="Some trigger",
                lesson="Some lesson",
                solution="Some solution",
            )

        assert len(prompts_seen) == 1
        assert TOOL_TITANS_ADD in prompts_seen[0]


# ===================================================================
# Step 2: Format: trigger_context + lesson + solution
# ===================================================================


class TestStoreLessonFormat:
    """Step 2: Content must be formatted as TRIGGER + LESSON + SOLUTION."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_content_contains_trigger(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="Import failed for missing module",
                lesson="Always check dependencies first",
                solution="Add dependency to pyproject.toml",
            )

        content = add_memory_calls[0]
        assert "TRIGGER:" in content
        assert "Import failed for missing module" in content

    @pytest.mark.asyncio
    async def test_content_contains_lesson(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="Trigger text",
                lesson="Always check dependencies first",
                solution="Solution text",
            )

        content = add_memory_calls[0]
        assert "LESSON:" in content
        assert "Always check dependencies first" in content

    @pytest.mark.asyncio
    async def test_content_contains_solution(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="Trigger text",
                lesson="Lesson text",
                solution="Add dependency to pyproject.toml",
            )

        content = add_memory_calls[0]
        assert "SOLUTION:" in content
        assert "Add dependency to pyproject.toml" in content

    @pytest.mark.asyncio
    async def test_content_format_is_structured(self, client):
        """Content should have all three parts in structured format."""
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="SQLite lock timeout",
                lesson="Use WAL mode for concurrent access",
                solution="Enable WAL mode in connection setup",
            )

        content = add_memory_calls[0]
        # All three sections must be present
        assert "TRIGGER: SQLite lock timeout" in content
        assert "LESSON: Use WAL mode for concurrent access" in content
        assert "SOLUTION: Enable WAL mode in connection setup" in content

    @pytest.mark.asyncio
    async def test_content_parts_are_separated(self, client):
        """Each part should be on a separate line."""
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        content = add_memory_calls[0]
        lines = content.strip().split("\n")
        assert len(lines) == 3
        assert lines[0].startswith("TRIGGER:")
        assert lines[1].startswith("LESSON:")
        assert lines[2].startswith("SOLUTION:")


# ===================================================================
# Step 3: Route to 'lessons' pool explicitly
# ===================================================================


class TestStoreLessonPool:
    """Step 3: store_lesson() must explicitly route to the 'lessons' pool."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_add_memory_called_with_lessons_pool(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"content": content, "pool": pool})
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert add_memory_calls[0]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_prompt_contains_lessons_pool(self, client):
        """The prompt sent to the sub-agent must specify the 'lessons' pool."""
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture_prompt(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(
            client, "_execute_tool_prompt", side_effect=capture_prompt
        ):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert len(prompts_seen) == 1
        assert "lessons" in prompts_seen[0]


# ===================================================================
# Step 4: Include metadata: feature_id, error_type, fix_action
# ===================================================================


class TestStoreLessonMetadata:
    """Step 4: store_lesson() must pass metadata including feature_id, error_type, fix_action."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_metadata_includes_feature_id(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
                feature_id="F041",
            )

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["feature_id"] == "F041"

    @pytest.mark.asyncio
    async def test_metadata_includes_error_type(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
                error_type="ImportError",
            )

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["error_type"] == "ImportError"

    @pytest.mark.asyncio
    async def test_metadata_includes_fix_action(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
                fix_action="Added missing import",
            )

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["fix_action"] == "Added missing import"

    @pytest.mark.asyncio
    async def test_all_metadata_fields_together(self, client):
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
                feature_id="F041",
                error_type="ValueError",
                fix_action="Validate input",
            )

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["feature_id"] == "F041"
        assert meta["error_type"] == "ValueError"
        assert meta["fix_action"] == "Validate input"

    @pytest.mark.asyncio
    async def test_no_metadata_when_none_provided(self, client):
        """When no optional metadata is given, metadata should be None."""
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert add_memory_calls[0]["metadata"] is None

    @pytest.mark.asyncio
    async def test_partial_metadata(self, client):
        """Only provided metadata fields should be included."""
        from bob3.titans_memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"}, raw_text="{}")

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
                feature_id="F041",
                # error_type and fix_action not provided
            )

        meta = add_memory_calls[0]["metadata"]
        assert meta is not None
        assert meta["feature_id"] == "F041"
        assert "error_type" not in meta
        assert "fix_action" not in meta


# ===================================================================
# Step 5: Create lesson, search for it, verify in lessons pool
# ===================================================================


class TestStoreLessonFullCycle:
    """Step 5: Full cycle - create lesson, search, verify in lessons pool."""

    @pytest.mark.asyncio
    async def test_store_and_search_lesson_cycle(self):
        """Store a lesson and then search for it in the lessons pool."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        call_sequence = []

        async def track_calls(prompt):
            call_sequence.append(prompt)
            if "titans_add" in prompt:
                return MemoryResult(
                    success=True,
                    data={
                        "id": "mem-lesson-42",
                        "content": "TRIGGER: ...\nLESSON: ...\nSOLUTION: ...",
                        "metadata": {"pool": "lessons", "feature_id": "F041"},
                    },
                    raw_text="{}",
                )
            elif "titans_search" in prompt:
                return MemoryResult(
                    success=True,
                    data=[
                        {
                            "id": "mem-lesson-42",
                            "content": "TRIGGER: DB lock\nLESSON: Use WAL\nSOLUTION: Enable WAL",
                            "metadata": {"pool": "lessons", "feature_id": "F041"},
                            "retrieval_weight": 0.9,
                        }
                    ],
                    raw_text="[]",
                )
            return MemoryResult(success=False, error="unexpected")

        with patch.object(
            client, "_execute_tool_prompt", side_effect=track_calls
        ):
            # Store a lesson
            store_result = await client.store_lesson(
                trigger_context="DB lock timeout during concurrent writes",
                lesson="Use WAL mode for concurrent access",
                solution="Enable WAL mode in connection setup",
                feature_id="F041",
                error_type="OperationalError",
                fix_action="Set journal_mode=WAL",
            )
            assert store_result.success is True
            assert store_result.data["id"] == "mem-lesson-42"

            # Search for the lesson in the lessons pool
            search_result = await client.search_memory(
                query="DB lock WAL mode",
                pool="lessons",
            )
            assert search_result.success is True
            assert isinstance(search_result.data, list)
            assert len(search_result.data) >= 1
            assert search_result.data[0]["id"] == "mem-lesson-42"
            assert search_result.data[0]["metadata"]["pool"] == "lessons"

        # Verify both calls went through
        assert len(call_sequence) == 2
        # First call should be titans_add (from store_lesson)
        assert "titans_add" in call_sequence[0]
        assert "lessons" in call_sequence[0]  # pool must be specified
        # Second call should be titans_search_pool (search with pool filter)
        assert "titans_search" in call_sequence[1]
        assert "lessons" in call_sequence[1]

    @pytest.mark.asyncio
    async def test_store_lesson_returns_memory_result(self):
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake(prompt):
            return MemoryResult(
                success=True,
                data={"id": "mem-99", "content": "stored"},
                raw_text="{}",
            )

        with patch.object(
            client, "_execute_tool_prompt", side_effect=fake
        ):
            result = await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert isinstance(result, MemoryResult)
        assert result.success is True
        assert result.data["id"] == "mem-99"

    @pytest.mark.asyncio
    async def test_store_lesson_propagates_failure(self):
        """If titans_add fails, store_lesson should propagate the failure."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fail(prompt):
            return MemoryResult(
                success=False,
                error="MCP server unavailable",
            )

        with patch.object(
            client, "_execute_tool_prompt", side_effect=fail
        ):
            result = await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert result.success is False
        assert "unavailable" in result.error
