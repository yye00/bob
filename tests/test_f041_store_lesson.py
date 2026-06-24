"""Tests for F041: Lesson storage in Bob memory (formerly TITANS).

Validates that the store_lesson() function:
- Step 1: Add store_lesson() function using the memory backend
- Step 2: Format: trigger_context + lesson + solution
- Step 3: Route to 'lessons' pool explicitly
- Step 4: Include metadata: feature_id, error_type, fix_action
- Step 5: Test: Create lesson, search for it, verify in lessons pool
"""

from unittest.mock import patch

import pytest


class _StubBackend:
    """Minimal stub BobMemory backend for store_lesson tests."""

    def __init__(self):
        self.add_calls = []
        self.search_calls = []
        self.search_results: list = []

    def add(self, content, *, pool=None, metadata=None):
        self.add_calls.append(
            {"content": content, "pool": pool, "metadata": metadata}
        )
        return {
            "id": f"stub-{len(self.add_calls)}",
            "content": content,
            "pool": pool or "facts",
            "metadata": metadata or {},
        }

    def search(self, query, *, pool=None, limit=10, include_archived=False):
        self.search_calls.append(
            {"query": query, "pool": pool, "limit": limit}
        )
        return list(self.search_results)

    def record_feedback(self, memory_id, success):
        return True

    def get(self, memory_id):
        return None

    def get_stats(self):
        return {"total": 0, "pools": {}, "statuses": {}}

    def archive(self, memory_id):
        return True

    def demote(self, memory_id):
        return True

    def get_demotion_candidates(self, **kwargs):
        return []


# ===================================================================
# Step 1: store_lesson() function exists
# ===================================================================


class TestStoreLessonExists:
    """Step 1: store_lesson() must exist on BobMemoryClient."""

    def test_store_lesson_method_exists(self):
        from bob.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())
        assert hasattr(client, "store_lesson")
        assert callable(client.store_lesson)

    def test_store_lesson_is_async(self):
        import inspect

        from bob.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())
        assert inspect.iscoroutinefunction(client.store_lesson)

    @pytest.mark.asyncio
    async def test_store_lesson_delegates_to_add_memory(self):
        """store_lesson() should internally call add_memory() with pool='lessons'."""
        from bob.memory_client import BobMemoryClient, MemoryResult

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

        add_memory_calls = []

        async def capture_add_memory(content, pool=None, metadata=None):
            add_memory_calls.append(
                {"content": content, "pool": pool, "metadata": metadata}
            )
            return MemoryResult(
                success=True,
                data={"id": "mem-lesson-1", "content": content},
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
    async def test_store_lesson_hits_backend_add(self):
        """store_lesson() must ultimately call the backend's add()."""
        from bob.memory_client import BobMemoryClient

        backend = _StubBackend()
        client = BobMemoryClient(workspace="/tmp/test", backend=backend)

        await client.store_lesson(
            trigger_context="Some trigger",
            lesson="Some lesson",
            solution="Some solution",
        )

        assert len(backend.add_calls) == 1
        assert backend.add_calls[0]["pool"] == "lessons"


# ===================================================================
# Step 2: Format: trigger_context + lesson + solution
# ===================================================================


class TestStoreLessonFormat:
    """Step 2: Content must be formatted as TRIGGER + LESSON + SOLUTION."""

    @pytest.fixture
    def client(self):
        from bob.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

    @pytest.mark.asyncio
    async def test_content_contains_trigger(self, client):
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"})

        with patch.object(client, "add_memory", side_effect=capture):
            await client.store_lesson(
                trigger_context="SQLite lock timeout",
                lesson="Use WAL mode for concurrent access",
                solution="Enable WAL mode in connection setup",
            )

        content = add_memory_calls[0]
        assert "TRIGGER: SQLite lock timeout" in content
        assert "LESSON: Use WAL mode for concurrent access" in content
        assert "SOLUTION: Enable WAL mode in connection setup" in content

    @pytest.mark.asyncio
    async def test_content_parts_are_separated(self, client):
        """Each part should be on a separate line."""
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append(content)
            return MemoryResult(success=True, data={"id": "m1"})

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
    def client_with_backend(self):
        from bob.memory_client import BobMemoryClient

        backend = _StubBackend()
        return BobMemoryClient(workspace="/tmp/test", backend=backend), backend

    @pytest.mark.asyncio
    async def test_add_memory_called_with_lessons_pool(self, client_with_backend):
        client, backend = client_with_backend
        await client.store_lesson(
            trigger_context="T",
            lesson="L",
            solution="S",
        )
        assert backend.add_calls[0]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_backend_add_receives_lessons_pool(self, client_with_backend):
        """The backend.add() must be called with pool='lessons'."""
        client, backend = client_with_backend
        await client.store_lesson(
            trigger_context="T",
            lesson="L",
            solution="S",
        )
        assert backend.add_calls[0]["pool"] == "lessons"


# ===================================================================
# Step 4: Include metadata: feature_id, error_type, fix_action
# ===================================================================


class TestStoreLessonMetadata:
    """Step 4: store_lesson() must pass metadata including feature_id, error_type, fix_action."""

    @pytest.fixture
    def client(self):
        from bob.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

    @pytest.mark.asyncio
    async def test_metadata_includes_feature_id(self, client):
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import MemoryResult

        add_memory_calls = []

        async def capture(content, pool=None, metadata=None):
            add_memory_calls.append({"metadata": metadata})
            return MemoryResult(success=True, data={"id": "m1"})

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
        from bob.memory_client import BobMemoryClient

        backend = _StubBackend()
        client = BobMemoryClient(workspace="/tmp/test", backend=backend)

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
        stored_id = store_result.data["id"]

        # The backend should now "return" this memory on search
        backend.search_results = [
            {
                "id": stored_id,
                "content": (
                    "TRIGGER: DB lock timeout during concurrent writes\n"
                    "LESSON: Use WAL mode for concurrent access\n"
                    "SOLUTION: Enable WAL mode in connection setup"
                ),
                "pool": "lessons",
                "score": 0.9,
                "metadata": {
                    "pool": "lessons",
                    "feature_id": "F041",
                },
            }
        ]

        # Search for the lesson in the lessons pool
        search_result = await client.search_memory(
            query="DB lock WAL mode",
            pool="lessons",
        )
        assert search_result.success is True
        assert isinstance(search_result.data, list)
        assert len(search_result.data) >= 1
        assert search_result.data[0]["id"] == stored_id
        assert search_result.data[0]["metadata"]["pool"] == "lessons"

        # Verify backend saw both operations
        assert len(backend.add_calls) == 1
        assert backend.add_calls[0]["pool"] == "lessons"
        assert len(backend.search_calls) == 1
        assert backend.search_calls[0]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_store_lesson_returns_memory_result(self):
        from bob.memory_client import BobMemoryClient, MemoryResult

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

        result = await client.store_lesson(
            trigger_context="T",
            lesson="L",
            solution="S",
        )

        assert isinstance(result, MemoryResult)
        assert result.success is True
        assert "id" in result.data

    @pytest.mark.asyncio
    async def test_store_lesson_propagates_failure(self):
        """If the backend.add raises, store_lesson should return failure."""
        from bob.memory_client import BobMemoryClient

        backend = _StubBackend()

        def raise_add(*args, **kwargs):
            raise RuntimeError("backend unavailable")

        backend.add = raise_add
        client = BobMemoryClient(workspace="/tmp/test", backend=backend)

        result = await client.store_lesson(
            trigger_context="T",
            lesson="L",
            solution="S",
        )

        assert result.success is False
        assert "unavailable" in result.error
