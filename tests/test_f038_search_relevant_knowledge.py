"""Tests for F038: Implement TITANS memory search before implementation.

Validates that search_relevant_knowledge():
- Step 1: Add search_relevant_knowledge() function
- Step 2: Call titans_search with feature context
- Step 3: Search multiple pools: facts, lessons, context
- Step 4: Return ranked results by retrieval_weight
- Step 5: Test: Add knowledge, search for it, verify found
"""

from unittest.mock import patch

import pytest


# ===================================================================
# Step 1: search_relevant_knowledge() function exists
# ===================================================================


class TestSearchRelevantKnowledgeExists:
    """Step 1: search_relevant_knowledge() must exist on TitansMemoryClient."""

    def test_method_exists(self):
        from bob.memory_client import BobMemoryClient as TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert hasattr(client, "search_relevant_knowledge")
        assert callable(client.search_relevant_knowledge)

    def test_method_is_async(self):
        import inspect

        from bob.memory_client import BobMemoryClient as TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert inspect.iscoroutinefunction(client.search_relevant_knowledge)

    def test_method_accepts_feature_name_and_description(self):
        """search_relevant_knowledge() must accept feature_name and description."""
        import inspect

        from bob.memory_client import BobMemoryClient as TitansMemoryClient

        sig = inspect.signature(TitansMemoryClient.search_relevant_knowledge)
        params = list(sig.parameters.keys())
        assert "feature_name" in params
        assert "description" in params

    def test_method_accepts_optional_feature_id(self):
        """search_relevant_knowledge() should accept an optional feature_id."""
        import inspect

        from bob.memory_client import BobMemoryClient as TitansMemoryClient

        sig = inspect.signature(TitansMemoryClient.search_relevant_knowledge)
        params = sig.parameters
        assert "feature_id" in params
        # Should have a default (optional)
        assert params["feature_id"].default is not inspect.Parameter.empty


# ===================================================================
# Step 2: Call titans_search with feature context
# ===================================================================


class TestSearchWithFeatureContext:
    """Step 2: Must call titans_search with feature context as query."""

    @pytest.fixture
    def client(self):
        from bob.memory_client import BobMemoryClient as TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_search_uses_feature_name_in_query(self, client):
        from bob.memory_client import MemoryResult

        search_calls = []

        async def capture_search(query, pool=None, limit=10):
            search_calls.append({"query": query, "pool": pool, "limit": limit})
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Database Connection Pool",
                description="Implement connection pooling for SQLite",
            )

        # At least one search call should contain the feature name
        all_queries = [c["query"] for c in search_calls]
        has_feature_name = any("Database Connection Pool" in q for q in all_queries)
        assert has_feature_name, f"Feature name not found in queries: {all_queries}"

    @pytest.mark.asyncio
    async def test_search_uses_description_in_query(self, client):
        from bob.memory_client import MemoryResult

        search_calls = []

        async def capture_search(query, pool=None, limit=10):
            search_calls.append({"query": query, "pool": pool, "limit": limit})
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="DB Pool",
                description="Implement connection pooling for SQLite",
            )

        all_queries = " ".join(c["query"] for c in search_calls)
        # Description content should appear in at least one query
        assert "connection pooling" in all_queries.lower() or "SQLite" in all_queries

    @pytest.mark.asyncio
    async def test_delegates_to_search_memory(self, client):
        """search_relevant_knowledge() must call search_memory()."""
        from bob.memory_client import MemoryResult

        search_calls = []

        async def capture_search(query, pool=None, limit=10):
            search_calls.append({"query": query, "pool": pool})
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Test Feature",
                description="A test description",
            )

        assert len(search_calls) > 0, "search_memory was never called"


# ===================================================================
# Step 3: Search multiple pools: facts, lessons, context
# ===================================================================


class TestSearchMultiplePools:
    """Step 3: Must search at least facts, lessons, and context pools."""

    @pytest.fixture
    def client(self):
        from bob.memory_client import BobMemoryClient as TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_searches_facts_pool(self, client):
        from bob.memory_client import MemoryResult

        pools_searched = []

        async def capture_search(query, pool=None, limit=10):
            pools_searched.append(pool)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert "facts" in pools_searched, f"facts pool not searched. Pools: {pools_searched}"

    @pytest.mark.asyncio
    async def test_searches_lessons_pool(self, client):
        from bob.memory_client import MemoryResult

        pools_searched = []

        async def capture_search(query, pool=None, limit=10):
            pools_searched.append(pool)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert "lessons" in pools_searched, f"lessons pool not searched. Pools: {pools_searched}"

    @pytest.mark.asyncio
    async def test_searches_context_pool(self, client):
        from bob.memory_client import MemoryResult

        pools_searched = []

        async def capture_search(query, pool=None, limit=10):
            pools_searched.append(pool)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert "context" in pools_searched, f"context pool not searched. Pools: {pools_searched}"

    @pytest.mark.asyncio
    async def test_searches_all_three_pools(self, client):
        from bob.memory_client import MemoryResult

        pools_searched = []

        async def capture_search(query, pool=None, limit=10):
            pools_searched.append(pool)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        required_pools = {"facts", "lessons", "context"}
        searched_pools = set(pools_searched)
        assert required_pools.issubset(searched_pools), (
            f"Missing pools: {required_pools - searched_pools}. Searched: {pools_searched}"
        )


# ===================================================================
# Step 4: Return ranked results by retrieval_weight
# ===================================================================


class TestRankedResults:
    """Step 4: Results must be returned ranked by retrieval_weight."""

    @pytest.fixture
    def client(self):
        from bob.memory_client import BobMemoryClient as TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_returns_memory_result(self, client):
        from bob.memory_client import MemoryResult

        async def fake_search(query, pool=None, limit=10):
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert isinstance(result, MemoryResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_results_sorted_by_retrieval_weight_descending(self, client):
        from bob.memory_client import MemoryResult

        call_count = 0

        async def fake_search(query, pool=None, limit=10):
            nonlocal call_count
            call_count += 1
            if pool == "facts":
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "f1", "content": "fact1", "retrieval_weight": 0.5, "pool": "facts"},
                    ],
                    raw_text="[]",
                )
            elif pool == "lessons":
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "l1", "content": "lesson1", "retrieval_weight": 0.9, "pool": "lessons"},
                    ],
                    raw_text="[]",
                )
            elif pool == "context":
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "c1", "content": "context1", "retrieval_weight": 0.7, "pool": "context"},
                    ],
                    raw_text="[]",
                )
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 3

        # Verify sorted by retrieval_weight descending
        weights = [r.get("retrieval_weight", 0) for r in result.data]
        assert weights == sorted(weights, reverse=True), (
            f"Results not sorted by retrieval_weight: {weights}"
        )

        # First result should be the lesson (highest weight 0.9)
        assert result.data[0]["id"] == "l1"
        assert result.data[1]["id"] == "c1"
        assert result.data[2]["id"] == "f1"

    @pytest.mark.asyncio
    async def test_merges_results_from_all_pools(self, client):
        from bob.memory_client import MemoryResult

        async def fake_search(query, pool=None, limit=10):
            if pool == "facts":
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "f1", "content": "fact", "retrieval_weight": 0.8, "pool": "facts"},
                        {"id": "f2", "content": "fact2", "retrieval_weight": 0.6, "pool": "facts"},
                    ],
                    raw_text="[]",
                )
            elif pool == "lessons":
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "l1", "content": "lesson", "retrieval_weight": 0.95, "pool": "lessons"},
                    ],
                    raw_text="[]",
                )
            elif pool == "context":
                return MemoryResult(
                    success=True,
                    data=[],
                    raw_text="[]",
                )
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert len(result.data) == 3
        ids = [r["id"] for r in result.data]
        assert "f1" in ids
        assert "f2" in ids
        assert "l1" in ids

    @pytest.mark.asyncio
    async def test_handles_empty_results_from_all_pools(self, client):
        from bob.memory_client import MemoryResult

        async def fake_search(query, pool=None, limit=10):
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_handles_failed_pool_search_gracefully(self, client):
        """If one pool search fails, others should still return results."""
        from bob.memory_client import MemoryResult

        async def fake_search(query, pool=None, limit=10):
            if pool == "lessons":
                return MemoryResult(
                    success=False,
                    error="MCP timeout",
                )
            return MemoryResult(
                success=True,
                data=[
                    {"id": f"{pool}-1", "content": f"{pool} result", "retrieval_weight": 0.5, "pool": pool},
                ],
                raw_text="[]",
            )

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        # Should still succeed with results from the non-failing pools
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) >= 1

    @pytest.mark.asyncio
    async def test_results_without_retrieval_weight_sorted_last(self, client):
        """Results missing retrieval_weight should sort to the end."""
        from bob.memory_client import MemoryResult

        async def fake_search(query, pool=None, limit=10):
            if pool == "facts":
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "f1", "content": "fact", "pool": "facts"},  # no retrieval_weight
                    ],
                    raw_text="[]",
                )
            elif pool == "lessons":
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "l1", "content": "lesson", "retrieval_weight": 0.8, "pool": "lessons"},
                    ],
                    raw_text="[]",
                )
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        assert result.data[0]["id"] == "l1"  # Has weight 0.8
        assert result.data[1]["id"] == "f1"  # No weight, sorted last


# ===================================================================
# Step 5: Test: Add knowledge, search for it, verify found
# ===================================================================


class TestFullKnowledgeSearchCycle:
    """Step 5: Full cycle - add knowledge, search, verify found."""

    @pytest.mark.asyncio
    async def test_add_knowledge_then_search_relevant(self):
        """Add facts/lessons, then search_relevant_knowledge finds them."""
        from bob.memory_client import MemoryResult, BobMemoryClient as TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        call_sequence = []

        # Simulate stored knowledge
        stored_memories = {
            "facts": [
                {
                    "id": "mem-fact-1",
                    "content": "SQLite WAL mode improves concurrent read performance",
                    "retrieval_weight": 0.85,
                    "pool": "facts",
                },
            ],
            "lessons": [
                {
                    "id": "mem-lesson-1",
                    "content": "TRIGGER: DB lock\nLESSON: Use WAL\nSOLUTION: Enable WAL",
                    "retrieval_weight": 0.92,
                    "pool": "lessons",
                },
            ],
            "context": [
                {
                    "id": "mem-ctx-1",
                    "content": "Working on database connection features",
                    "retrieval_weight": 0.60,
                    "pool": "context",
                },
            ],
        }

        async def fake_search(query, pool=None, limit=10):
            call_sequence.append({"action": "search", "pool": pool, "query": query})
            memories = stored_memories.get(pool, [])
            return MemoryResult(success=True, data=memories, raw_text="[]")

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Database Connection Pool",
                description="Implement connection pooling for SQLite with WAL mode",
                feature_id="F038",
            )

        # Should have searched all three pools
        pools_searched = {c["pool"] for c in call_sequence}
        assert "facts" in pools_searched
        assert "lessons" in pools_searched
        assert "context" in pools_searched

        # Should have found all three memories, sorted by weight
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 3

        # Highest weight first (lesson at 0.92)
        assert result.data[0]["id"] == "mem-lesson-1"
        assert result.data[0]["retrieval_weight"] == 0.92

        # Then fact at 0.85
        assert result.data[1]["id"] == "mem-fact-1"
        assert result.data[1]["retrieval_weight"] == 0.85

        # Then context at 0.60
        assert result.data[2]["id"] == "mem-ctx-1"
        assert result.data[2]["retrieval_weight"] == 0.60

    @pytest.mark.asyncio
    async def test_search_with_feature_id_included(self):
        """feature_id should be usable for more targeted search."""
        from bob.memory_client import MemoryResult, BobMemoryClient as TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        search_calls = []

        async def capture_search(query, pool=None, limit=10):
            search_calls.append({"query": query, "pool": pool})
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Test Feature",
                description="Test description",
                feature_id="F038",
            )

        # Feature ID should be included in at least one query
        all_queries = " ".join(c["query"] for c in search_calls)
        assert "F038" in all_queries

    @pytest.mark.asyncio
    async def test_all_pools_fail_returns_empty_success(self):
        """If all pool searches fail, return success with empty list."""
        from bob.memory_client import MemoryResult, BobMemoryClient as TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fail_search(query, pool=None, limit=10):
            return MemoryResult(success=False, error="MCP down")

        with patch.object(client, "search_memory", side_effect=fail_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        # Should still return success (no results, but no crash)
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self):
        """A limit parameter should control max results per pool."""
        import inspect

        from bob.memory_client import MemoryResult, BobMemoryClient as TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        # Check that limit parameter exists
        sig = inspect.signature(client.search_relevant_knowledge)
        assert "limit_per_pool" in sig.parameters

        search_calls = []

        async def capture_search(query, pool=None, limit=10):
            search_calls.append({"pool": pool, "limit": limit})
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "search_memory", side_effect=capture_search):
            await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
                limit_per_pool=3,
            )

        # Each pool search should use the specified limit
        for call in search_calls:
            assert call["limit"] == 3

    @pytest.mark.asyncio
    async def test_deduplicates_results_across_pools(self):
        """If the same memory appears in multiple pools, deduplicate."""
        from bob.memory_client import MemoryResult, BobMemoryClient as TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_search(query, pool=None, limit=10):
            # Same memory appears in both facts and context
            return MemoryResult(
                success=True,
                data=[
                    {"id": "mem-dup", "content": "duplicate memory", "retrieval_weight": 0.8, "pool": pool},
                ],
                raw_text="[]",
            )

        with patch.object(client, "search_memory", side_effect=fake_search):
            result = await client.search_relevant_knowledge(
                feature_name="Test",
                description="Test description",
            )

        # Should deduplicate by id
        ids = [r["id"] for r in result.data]
        assert ids.count("mem-dup") == 1
