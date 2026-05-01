"""Tests for F016: Bob3 Memory in-process client (formerly TITANS).

Validates that the memory_client module:
- Step 1: Provides memory_client.py wrapper module
- Step 2: Implements add_memory(content, pool) via the BobMemory backend
- Step 3: Implements search_memory(query, pool) via the BobMemory backend
- Step 4: Implements record_feedback(memory_id, success)
- Step 5: Tests the memory add/search/feedback cycle
- Step 6: Verifies memories persist across sessions (client re-creation)

The sub-agent based TITANS integration has been replaced with an
in-process mem0ai + Ollama + Qdrant stack, so tests use a stub
BobMemory backend to verify client behavior.
"""

import pathlib
from typing import Any
from unittest.mock import MagicMock

import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob3" / "memory_client.py"


class _StubBackend:
    """A stub BobMemory backend that records calls for tests."""

    def __init__(self) -> None:
        self.add_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []
        self.feedback_calls: list[tuple[str, bool]] = []
        self.store: dict[str, dict[str, Any]] = {}
        self._next_id = 0
        self.search_results: list[dict[str, Any]] = []
        self.raise_add: Exception | None = None
        self.raise_search: Exception | None = None

    def _new_id(self) -> str:
        self._next_id += 1
        return f"stub-{self._next_id}"

    def add(self, content, *, pool=None, metadata=None):
        self.add_calls.append(
            {"content": content, "pool": pool, "metadata": metadata or {}}
        )
        if self.raise_add:
            raise self.raise_add
        mem_id = self._new_id()
        record = {
            "id": mem_id,
            "content": content,
            "pool": pool or "facts",
            "metadata": dict(metadata or {}),
        }
        self.store[mem_id] = record
        return record

    def search(self, query, *, pool=None, limit=10, include_archived=False):
        self.search_calls.append(
            {
                "query": query,
                "pool": pool,
                "limit": limit,
                "include_archived": include_archived,
            }
        )
        if self.raise_search:
            raise self.raise_search
        return list(self.search_results)

    def record_feedback(self, memory_id, success):
        self.feedback_calls.append((memory_id, success))
        return memory_id in self.store

    def get(self, memory_id):
        return self.store.get(memory_id)

    def get_stats(self):
        return {"total": len(self.store), "pools": {}, "statuses": {}}

    def archive(self, memory_id):
        return memory_id in self.store

    def demote(self, memory_id):
        return memory_id in self.store

    def get_demotion_candidates(self, *, min_times_applied=5, max_usefulness=0.3, limit=50):
        return []


# ===================================================================
# Step 1: Module exists and is importable
# ===================================================================


class TestModuleExists:
    """Step 1: src/bob3/memory_client.py must exist and be importable."""

    def test_module_file_exists(self):
        assert MODULE_PATH.is_file(), f"Expected {MODULE_PATH} to exist"

    def test_module_is_non_empty(self):
        content = MODULE_PATH.read_text()
        assert len(content.strip()) > 200, "Module appears to be a stub"

    def test_module_is_importable(self):
        import bob3.memory_client

        assert bob3.memory_client is not None

    def test_memory_client_class_exists(self):
        from bob3.memory_client import BobMemoryClient

        assert BobMemoryClient is not None

    def test_memory_result_class_exists(self):
        from bob3.memory_client import MemoryResult

        assert MemoryResult is not None

    def test_valid_pools_constant_exists(self):
        from bob3.memory import VALID_POOLS

        assert isinstance(VALID_POOLS, (set, frozenset))
        assert "facts" in VALID_POOLS
        assert "preferences" in VALID_POOLS
        assert "lessons" in VALID_POOLS
        assert "context" in VALID_POOLS

    def test_classify_pool_function_exists(self):
        from bob3.memory import _classify_pool

        assert callable(_classify_pool)


# ===================================================================
# Step 2: add_memory(content, pool) via the BobMemory backend
# ===================================================================


class TestAddMemory:
    """Step 2: add_memory() must call the BobMemory backend's add()."""

    @pytest.fixture
    def backend(self):
        return _StubBackend()

    @pytest.fixture
    def client(self, backend):
        from bob3.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test-workspace", backend=backend)

    @pytest.mark.asyncio
    async def test_add_memory_calls_backend_add(self, client, backend):
        result = await client.add_memory(content="Test memory", pool="facts")
        assert result.success is True
        assert len(backend.add_calls) == 1

    @pytest.mark.asyncio
    async def test_add_memory_passes_content(self, client, backend):
        await client.add_memory(content="SQLite WAL mode improves reads", pool="facts")
        assert backend.add_calls[0]["content"] == "SQLite WAL mode improves reads"

    @pytest.mark.asyncio
    async def test_add_memory_passes_pool(self, client, backend):
        await client.add_memory(content="test", pool="lessons")
        assert backend.add_calls[0]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_add_memory_with_metadata(self, client, backend):
        await client.add_memory(
            content="test",
            pool="facts",
            metadata={"feature_id": "F016"},
        )
        assert backend.add_calls[0]["metadata"]["feature_id"] == "F016"

    @pytest.mark.asyncio
    async def test_add_memory_without_pool(self, client, backend):
        """When no pool is specified, backend auto-routes."""
        result = await client.add_memory(content="something general")
        assert result.success is True
        assert backend.add_calls[0]["pool"] is None

    @pytest.mark.asyncio
    async def test_add_memory_invalid_pool_raises(self, client):
        with pytest.raises(ValueError, match="Invalid memory pool"):
            await client.add_memory(content="test", pool="invalid_pool")

    @pytest.mark.asyncio
    async def test_add_memory_returns_memory_result(self, client, backend):
        from bob3.memory_client import MemoryResult

        result = await client.add_memory(content="hello", pool="facts")
        assert isinstance(result, MemoryResult)
        assert result.success is True
        assert result.data["id"] == "stub-1"

    @pytest.mark.asyncio
    async def test_add_memory_backend_error_returns_failure(self, client, backend):
        backend.raise_add = RuntimeError("backend down")
        result = await client.add_memory(content="x", pool="facts")
        assert result.success is False
        assert "backend down" in result.error


# ===================================================================
# Step 3: search_memory(query, pool) via the BobMemory backend
# ===================================================================


class TestSearchMemory:
    """Step 3: search_memory() must call the BobMemory backend's search()."""

    @pytest.fixture
    def backend(self):
        return _StubBackend()

    @pytest.fixture
    def client(self, backend):
        from bob3.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test-workspace", backend=backend)

    @pytest.mark.asyncio
    async def test_search_memory_calls_backend(self, client, backend):
        result = await client.search_memory(query="test query")
        assert result.success is True
        assert len(backend.search_calls) == 1

    @pytest.mark.asyncio
    async def test_search_memory_without_pool(self, client, backend):
        await client.search_memory(query="SQLite concurrency")
        assert backend.search_calls[0]["pool"] is None
        assert backend.search_calls[0]["query"] == "SQLite concurrency"

    @pytest.mark.asyncio
    async def test_search_memory_with_pool(self, client, backend):
        await client.search_memory(query="SQLite concurrency", pool="facts")
        assert backend.search_calls[0]["pool"] == "facts"

    @pytest.mark.asyncio
    async def test_search_memory_passes_limit(self, client, backend):
        await client.search_memory(query="test", limit=5)
        assert backend.search_calls[0]["limit"] == 5

    @pytest.mark.asyncio
    async def test_search_memory_returns_list_data(self, client, backend):
        backend.search_results = [
            {"id": "mem-1", "content": "first result", "score": 0.9},
            {"id": "mem-2", "content": "second result", "score": 0.7},
        ]
        result = await client.search_memory(query="test")
        assert isinstance(result.data, list)
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_search_memory_invalid_pool_raises(self, client):
        with pytest.raises(ValueError, match="Invalid memory pool"):
            await client.search_memory(query="test", pool="not_a_pool")


# ===================================================================
# Step 4: record_feedback(memory_id, success)
# ===================================================================


class TestRecordFeedback:
    """Step 4: record_feedback() must call the backend's record_feedback()."""

    @pytest.fixture
    def backend(self):
        b = _StubBackend()
        # Pre-populate so feedback returns True
        b.store["mem-1"] = {"id": "mem-1", "content": "", "pool": "facts", "metadata": {}}
        b.store["mem-abc"] = {"id": "mem-abc", "content": "", "pool": "facts", "metadata": {}}
        b.store["mem-xyz-123"] = {"id": "mem-xyz-123", "content": "", "pool": "facts", "metadata": {}}
        return b

    @pytest.fixture
    def client(self, backend):
        from bob3.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test-workspace", backend=backend)

    @pytest.mark.asyncio
    async def test_record_feedback_calls_backend(self, client, backend):
        result = await client.record_feedback(memory_id="mem-1", success=True)
        assert result.success is True
        assert backend.feedback_calls == [("mem-1", True)]

    @pytest.mark.asyncio
    async def test_record_feedback_passes_memory_id(self, client, backend):
        await client.record_feedback(memory_id="mem-xyz-123", success=False)
        assert backend.feedback_calls[0][0] == "mem-xyz-123"

    @pytest.mark.asyncio
    async def test_record_feedback_success_true(self, client, backend):
        await client.record_feedback(memory_id="mem-1", success=True)
        assert backend.feedback_calls[0][1] is True

    @pytest.mark.asyncio
    async def test_record_feedback_success_false(self, client, backend):
        await client.record_feedback(memory_id="mem-1", success=False)
        assert backend.feedback_calls[0][1] is False


# ===================================================================
# Step 5: Test memory add/search/feedback cycle
# ===================================================================


class TestMemoryCycle:
    """Step 5: Full add -> search -> feedback cycle works end-to-end."""

    @pytest.fixture
    def backend(self):
        return _StubBackend()

    @pytest.fixture
    def client(self, backend):
        from bob3.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test-workspace", backend=backend)

    @pytest.mark.asyncio
    async def test_add_then_search_then_feedback_cycle(self, client, backend):
        """Simulates a complete memory lifecycle: add, search, feedback."""
        # Step A: Add a memory
        add_result = await client.add_memory(
            content="WAL mode lesson",
            pool="lessons",
        )
        assert add_result.success is True
        memory_id = add_result.data["id"]

        # Set up the stub's search results to return the stored memory
        backend.search_results = [
            {"id": memory_id, "content": "WAL mode lesson", "score": 0.8}
        ]

        # Step B: Search for the memory
        search_result = await client.search_memory(
            query="WAL mode",
            pool="lessons",
        )
        assert search_result.success is True
        assert isinstance(search_result.data, list)
        assert len(search_result.data) >= 1

        # Step C: Record positive feedback on the found memory
        feedback_result = await client.record_feedback(
            memory_id=memory_id,
            success=True,
        )
        assert feedback_result.success is True

        # Verify backend saw all three operations
        assert len(backend.add_calls) == 1
        assert len(backend.search_calls) == 1
        assert len(backend.feedback_calls) == 1


# ===================================================================
# Step 6: Verify memories persist across sessions (client re-creation)
# ===================================================================


class TestPersistenceAcrossSessions:
    """Step 6: Memories should persist when a new client is created.

    In the in-process model, persistence comes from a shared backend
    instance (or, in production, from the underlying Qdrant store).
    """

    @pytest.mark.asyncio
    async def test_memory_accessible_from_new_client(self):
        """A memory added by one client should be searchable by another
        client sharing the same backend."""
        from bob3.memory_client import BobMemoryClient

        shared_backend = _StubBackend()

        # Session 1: Add a memory
        client1 = BobMemoryClient(workspace="/tmp/session1", backend=shared_backend)
        add_result = await client1.add_memory(
            content="important lesson",
            pool="lessons",
        )
        assert add_result.success is True
        memory_id = add_result.data["id"]

        # Prime search results so the second client can find it
        shared_backend.search_results = [
            {"id": memory_id, "content": "important lesson", "score": 0.9}
        ]

        # Session 2: New client searches for same memory
        client2 = BobMemoryClient(workspace="/tmp/session2", backend=shared_backend)
        search_result = await client2.search_memory(
            query="important lesson",
            pool="lessons",
        )
        assert search_result.success is True
        assert isinstance(search_result.data, list)
        assert len(search_result.data) >= 1
        assert search_result.data[0]["id"] == memory_id

    def test_client_is_stateless_wrapper(self):
        """BobMemoryClient should be a stateless wrapper - no local cache."""
        from bob3.memory_client import BobMemoryClient

        backend = _StubBackend()
        client = BobMemoryClient(workspace="/tmp/test", backend=backend)
        # Client should have no memory storage attributes
        assert not hasattr(client, "_cache")
        assert not hasattr(client, "_memories")
        assert not hasattr(client, "_store")


# ===================================================================
# Helper function tests
# ===================================================================


class TestClassifyPool:
    """Tests for the _classify_pool() local classifier (formerly route_to_pool)."""

    def test_routes_bug_content_to_lessons(self):
        from bob3.memory import _classify_pool

        result = _classify_pool("Bug fix: the error was caused by a missing import")
        assert result == "lessons"

    def test_routes_convention_content_to_preferences(self):
        from bob3.memory import _classify_pool

        result = _classify_pool("Always use snake_case naming convention for functions")
        assert result == "preferences"

    def test_routes_session_content_to_context(self):
        from bob3.memory import _classify_pool

        result = _classify_pool("Currently working on feature F016 in this session")
        assert result == "context"

    def test_ambiguous_content_defaults_to_facts(self):
        from bob3.memory import _classify_pool

        # Content with no clear matches defaults to facts
        result = _classify_pool("something completely unrelated to any keywords")
        assert result == "facts"


class TestValidatePool:
    """Tests for pool validation."""

    def test_valid_pools_accepted(self):
        from bob3.memory_client import _validate_pool

        _validate_pool("facts")
        _validate_pool("preferences")
        _validate_pool("lessons")
        _validate_pool("context")
        _validate_pool(None)  # None = auto-route

    def test_invalid_pool_raises(self):
        from bob3.memory_client import _validate_pool

        with pytest.raises(ValueError, match="Invalid memory pool"):
            _validate_pool("nonexistent")


class TestMemoryResult:
    """Tests for the MemoryResult dataclass."""

    def test_default_values(self):
        from bob3.memory_client import MemoryResult

        r = MemoryResult(success=True)
        assert r.success is True
        assert r.data is None
        assert r.error == ""
        assert r.raw_text == ""

    def test_success_with_data(self):
        from bob3.memory_client import MemoryResult

        r = MemoryResult(success=True, data={"id": "x"})
        assert r.data == {"id": "x"}

    def test_failure_with_error(self):
        from bob3.memory_client import MemoryResult

        r = MemoryResult(success=False, error="connection failed")
        assert r.success is False
        assert "connection" in r.error


class TestClientConstruction:
    """Tests for BobMemoryClient construction and configuration."""

    def test_client_accepts_workspace(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/some/path", backend=_StubBackend())
        assert client.workspace == "/some/path"

    def test_client_accepts_pathlib_workspace(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(
            workspace=pathlib.Path("/some/path"), backend=_StubBackend()
        )
        assert client.workspace == "/some/path"

    def test_client_default_max_turns(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/tmp", backend=_StubBackend())
        assert client.max_turns == 3

    def test_client_custom_max_turns(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(
            workspace="/tmp", max_turns=5, backend=_StubBackend()
        )
        assert client.max_turns == 5

    def test_client_exposes_backend(self):
        from bob3.memory_client import BobMemoryClient

        backend = _StubBackend()
        client = BobMemoryClient(workspace="/tmp", backend=backend)
        assert client._backend is backend
