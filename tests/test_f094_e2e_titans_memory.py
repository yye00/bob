"""Tests for F094: End-to-end test - Bob3 Memory lifecycle (formerly TITANS).

Exercises the complete memory lifecycle: add, search, feedback, archive.

Step 1: Add facts to memory (pool='facts')
Step 2: Add lessons to memory (pool='lessons')
Step 3: Search for relevant memories
Step 4: Verify retrieval ranking by retrieval_weight
Step 5: Record feedback (success=True)
Step 6: Verify usefulness score increases
Step 7: Get forgetting candidates
Step 8: Archive old memory

Previously this exercised the TITANS Memory MCP client (which spawned a
sub-agent to call MCP tools). It now exercises the in-process
BobMemoryClient backed by a simulated BobMemory.
"""

import pytest

from bob3.memory_client import BobMemoryClient


# ============================================================
# Simulated BobMemory backend supporting facts + lessons pools
# ============================================================


class SimulatedBackend:
    """In-memory simulation of BobMemory across multiple pools."""

    def __init__(self):
        self.memories: dict[str, list[dict]] = {"facts": [], "lessons": []}
        self.feedback_log: dict[str, list[bool]] = {}
        self.archived_ids: set[str] = set()
        self._next_id = 1

    def _make_id(self) -> str:
        mid = f"mem-e2e-{self._next_id:03d}"
        self._next_id += 1
        return mid

    def _usefulness_score(self, memory_id: str) -> float:
        fb = self.feedback_log.get(memory_id, [])
        if not fb:
            return 0.5
        return sum(1 for f in fb if f) / len(fb)

    def _find(self, memory_id: str) -> dict | None:
        for pool_mems in self.memories.values():
            for mem in pool_mems:
                if mem["id"] == memory_id:
                    return mem
        return None

    def add(self, content, *, pool=None, metadata=None):
        actual_pool = pool or "facts"
        mid = self._make_id()
        meta = {
            "pool": actual_pool,
            "usefulness_score": 0.5,
            "status": "active",
        }
        if metadata:
            meta.update(metadata)
            meta["pool"] = actual_pool
        memory = {
            "id": mid,
            "content": content,
            "pool": actual_pool,
            "metadata": meta,
            "retrieval_weight": 0.5,
        }
        self.memories.setdefault(actual_pool, []).append(memory)
        self.feedback_log[mid] = []
        return dict(memory)

    def search(self, query, *, pool=None, limit=10, include_archived=False):
        results = []
        if pool:
            pool_list = self.memories.get(pool, [])
        else:
            pool_list = [m for mems in self.memories.values() for m in mems]
        for mem in pool_list:
            if not include_archived and mem["id"] in self.archived_ids:
                continue
            result = dict(mem)
            # Refresh metadata with current usefulness score
            result["metadata"] = dict(result["metadata"])
            result["metadata"]["usefulness_score"] = self._usefulness_score(mem["id"])
            result["score"] = result["retrieval_weight"]
            results.append(result)
        results.sort(key=lambda m: m.get("retrieval_weight", 0), reverse=True)
        return results[:limit]

    def record_feedback(self, memory_id, success):
        mem = self._find(memory_id)
        if mem is None:
            return False
        self.feedback_log[memory_id].append(bool(success))
        mem["metadata"]["usefulness_score"] = self._usefulness_score(memory_id)
        if success:
            mem["retrieval_weight"] = min(1.0, mem["retrieval_weight"] + 0.1)
        return True

    def get(self, memory_id):
        mem = self._find(memory_id)
        if mem is None:
            return None
        return dict(mem)

    def get_stats(self):
        totals = {}
        for pool_name, mems in self.memories.items():
            live = [m for m in mems if m["id"] not in self.archived_ids]
            totals[pool_name] = {"count": len(live)}
        return {"total": sum(t["count"] for t in totals.values()), "pools": totals, "statuses": {}}

    def archive(self, memory_id):
        mem = self._find(memory_id)
        if mem is None:
            return False
        self.archived_ids.add(memory_id)
        mem["metadata"]["status"] = "archived"
        return True

    def demote(self, memory_id):
        mem = self._find(memory_id)
        if mem is None:
            return False
        mem["metadata"]["status"] = "demoted"
        return True

    def get_demotion_candidates(self, *, min_times_applied=5, max_usefulness=0.3, limit=50):
        out = []
        for mems in self.memories.values():
            for mem in mems:
                if mem["id"] in self.archived_ids:
                    continue
                score = self._usefulness_score(mem["id"])
                if score < 0.5:
                    candidate = dict(mem)
                    candidate["metadata"] = dict(candidate["metadata"])
                    candidate["metadata"]["usefulness_score"] = score
                    out.append(candidate)
        return out[:limit]


@pytest.fixture
def backend():
    return SimulatedBackend()


@pytest.fixture
def client(backend):
    return BobMemoryClient(workspace="/tmp/e2e-memory-lifecycle", backend=backend)


# ============================================================
# Step 1: Add facts to memory (pool='facts')
# ============================================================


class TestStep1AddFactsToMemory:
    """Step 1: Add facts to memory (pool='facts')."""

    @pytest.mark.asyncio
    async def test_add_fact_to_facts_pool(self, client, backend):
        """Adding a fact to the facts pool should succeed and return an ID."""
        result = await client.add_memory(
            content="SQLite WAL mode improves concurrent read performance",
            pool="facts",
        )
        assert result.success is True
        assert "id" in result.data
        assert result.data["metadata"]["pool"] == "facts"

    @pytest.mark.asyncio
    async def test_add_fact_calls_backend_add(self, client, backend):
        await client.add_memory(content="Python 3.14 supports PEP 649", pool="facts")
        assert len(backend.memories["facts"]) == 1

    @pytest.mark.asyncio
    async def test_add_multiple_facts(self, client, backend):
        """Multiple facts can be added to the facts pool."""
        r1 = await client.add_memory(content="Fact 1", pool="facts")
        r2 = await client.add_memory(content="Fact 2", pool="facts")
        assert r1.success is True
        assert r2.success is True
        assert r1.data["id"] != r2.data["id"]
        assert len(backend.memories["facts"]) == 2


# ============================================================
# Step 2: Add lessons to memory (pool='lessons')
# ============================================================


class TestStep2AddLessonsToMemory:
    """Step 2: Add lessons to memory (pool='lessons')."""

    @pytest.mark.asyncio
    async def test_add_lesson_to_lessons_pool(self, client, backend):
        """Adding a lesson to the lessons pool should succeed."""
        result = await client.store_lesson(
            trigger_context="Database lock during writes",
            lesson="Use WAL mode for concurrent access",
            solution="Set journal_mode=WAL",
        )
        assert result.success is True
        assert result.data["metadata"]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_lesson_content_is_structured(self, client, backend):
        """Lesson content should contain TRIGGER, LESSON, SOLUTION."""
        await client.store_lesson(
            trigger_context="Lock error",
            lesson="Enable WAL",
            solution="Pragma WAL",
        )
        content = backend.memories["lessons"][0]["content"]
        assert "TRIGGER:" in content
        assert "LESSON:" in content
        assert "SOLUTION:" in content


# ============================================================
# Step 3: Search for relevant memories
# ============================================================


class TestStep3SearchForRelevantMemories:
    """Step 3: Search for relevant memories."""

    @pytest.mark.asyncio
    async def test_search_returns_added_memories(self, client, backend):
        """Searching should return previously added memories."""
        await client.add_memory(content="WAL mode fact", pool="facts")
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")

        results = await client.search_memory(query="WAL mode")
        assert results.success is True
        assert len(results.data) == 2

    @pytest.mark.asyncio
    async def test_search_pool_filters_by_pool(self, client, backend):
        """Search with a pool filter should only return memories from that pool."""
        await client.add_memory(content="Fact A", pool="facts")
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")

        facts_results = await client.search_memory(query="memory", pool="facts")
        lessons_results = await client.search_memory(query="memory", pool="lessons")

        assert len(facts_results.data) == 1
        assert facts_results.data[0]["metadata"]["pool"] == "facts"
        assert len(lessons_results.data) == 1
        assert lessons_results.data[0]["metadata"]["pool"] == "lessons"


# ============================================================
# Step 4: Verify retrieval ranking by retrieval_weight
# ============================================================


class TestStep4VerifyRetrievalRanking:
    """Step 4: Verify retrieval ranking by retrieval_weight."""

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_retrieval_weight(self, client, backend):
        """Search results should be sorted by retrieval_weight (descending)."""
        await client.add_memory(content="Fact 1", pool="facts")
        await client.add_memory(content="Fact 2", pool="facts")

        second_id = backend.memories["facts"][1]["id"]
        await client.record_feedback(memory_id=second_id, success=True)
        await client.record_feedback(memory_id=second_id, success=True)

        results = await client.search_memory(query="facts", pool="facts")
        assert len(results.data) == 2
        weights = [m["retrieval_weight"] for m in results.data]
        assert weights == sorted(weights, reverse=True)

    @pytest.mark.asyncio
    async def test_higher_weight_ranks_first(self, client, backend):
        """Memories with higher retrieval weight rank before lower ones."""
        await client.add_memory(content="Low priority fact", pool="facts")
        await client.add_memory(content="High priority fact", pool="facts")

        high_id = backend.memories["facts"][1]["id"]
        for _ in range(3):
            await client.record_feedback(memory_id=high_id, success=True)

        results = await client.search_memory(query="fact", pool="facts")
        assert results.data[0]["id"] == high_id

    @pytest.mark.asyncio
    async def test_global_search_ranks_across_pools(self, client, backend):
        """Global search ranks results across all pools by retrieval_weight."""
        await client.add_memory(content="A fact", pool="facts")
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")

        results = await client.search_memory(query="memory")
        weights = [m.get("retrieval_weight", 0) for m in results.data]
        assert weights == sorted(weights, reverse=True)


# ============================================================
# Step 5: Record feedback (success=True)
# ============================================================


class TestStep5RecordFeedback:
    """Step 5: Record feedback (success=True)."""

    @pytest.mark.asyncio
    async def test_record_positive_feedback(self, client, backend):
        """Recording positive feedback should succeed."""
        add_result = await client.add_memory(content="A fact", pool="facts")
        memory_id = add_result.data["id"]

        fb_result = await client.record_feedback(memory_id=memory_id, success=True)
        assert fb_result.success is True
        assert backend.feedback_log[memory_id] == [True]

    @pytest.mark.asyncio
    async def test_multiple_feedback_recorded(self, client, backend):
        """Multiple feedback entries should be tracked."""
        add_result = await client.add_memory(content="A fact", pool="facts")
        memory_id = add_result.data["id"]

        await client.record_feedback(memory_id=memory_id, success=True)
        await client.record_feedback(memory_id=memory_id, success=True)
        await client.record_feedback(memory_id=memory_id, success=False)

        assert backend.feedback_log[memory_id] == [True, True, False]


# ============================================================
# Step 6: Verify usefulness score increases
# ============================================================


class TestStep6VerifyUsefulnessScoreIncreases:
    """Step 6: Verify usefulness score increases after positive feedback."""

    @pytest.mark.asyncio
    async def test_usefulness_increases_after_positive_feedback(self, client, backend):
        """Usefulness score should increase after positive feedback."""
        add_result = await client.add_memory(content="A fact", pool="facts")
        memory_id = add_result.data["id"]

        initial_score = backend._usefulness_score(memory_id)
        assert initial_score == 0.5

        await client.record_feedback(memory_id=memory_id, success=True)

        new_score = backend._usefulness_score(memory_id)
        assert new_score > initial_score
        assert new_score == 1.0

    @pytest.mark.asyncio
    async def test_usefulness_reflects_feedback_ratio(self, client, backend):
        """Usefulness should reflect the ratio of positive to total feedback."""
        add_result = await client.add_memory(content="A fact", pool="facts")
        memory_id = add_result.data["id"]

        for success in [True, True, True, True, False]:
            await client.record_feedback(memory_id=memory_id, success=success)

        score = backend._usefulness_score(memory_id)
        assert score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_retrieval_weight_increases_with_positive_feedback(
        self, client, backend
    ):
        """Retrieval weight should increase when positive feedback is recorded."""
        add_result = await client.add_memory(content="A fact", pool="facts")
        memory_id = add_result.data["id"]

        initial_weight = backend.memories["facts"][0]["retrieval_weight"]
        await client.record_feedback(memory_id=memory_id, success=True)
        new_weight = backend.memories["facts"][0]["retrieval_weight"]

        assert new_weight > initial_weight


# ============================================================
# Step 7: Get forgetting candidates
# ============================================================


class TestStep7GetForgettingCandidates:
    """Step 7: Get forgetting candidates."""

    @pytest.mark.asyncio
    async def test_low_usefulness_memory_is_candidate(self, client, backend):
        """A memory with low usefulness should appear as a forgetting candidate."""
        add_result = await client.add_memory(content="Bad fact", pool="facts")
        memory_id = add_result.data["id"]

        for _ in range(3):
            await client.record_feedback(memory_id=memory_id, success=False)

        candidates = await client.get_demotion_candidates(limit=10)
        assert candidates.success is True
        assert len(candidates.data) == 1
        assert candidates.data[0]["id"] == memory_id

    @pytest.mark.asyncio
    async def test_high_usefulness_memory_not_candidate(self, client, backend):
        """A memory with high usefulness should NOT appear as a forgetting candidate."""
        add_result = await client.add_memory(content="Good fact", pool="facts")
        memory_id = add_result.data["id"]

        for _ in range(3):
            await client.record_feedback(memory_id=memory_id, success=True)

        candidates = await client.get_demotion_candidates(limit=10)
        assert len(candidates.data) == 0

    @pytest.mark.asyncio
    async def test_archived_memory_not_in_candidates(self, client, backend):
        """Archived memories should not appear as forgetting candidates."""
        add_result = await client.add_memory(content="Old fact", pool="facts")
        memory_id = add_result.data["id"]

        for _ in range(3):
            await client.record_feedback(memory_id=memory_id, success=False)

        await client.archive_memory(memory_id=memory_id)

        candidates = await client.get_demotion_candidates(limit=10)
        assert len(candidates.data) == 0


# ============================================================
# Step 8: Archive old memory
# ============================================================


class TestStep8ArchiveOldMemory:
    """Step 8: Archive old memory."""

    @pytest.mark.asyncio
    async def test_archive_memory_succeeds(self, client, backend):
        add_result = await client.add_memory(content="Old fact", pool="facts")
        memory_id = add_result.data["id"]
        archive_result = await client.archive_memory(memory_id=memory_id)
        assert archive_result.success is True

    @pytest.mark.asyncio
    async def test_archived_memory_not_in_search_results(self, client, backend):
        add_result = await client.add_memory(content="Archivable fact", pool="facts")
        memory_id = add_result.data["id"]

        search_before = await client.search_memory(query="fact", pool="facts")
        assert len(search_before.data) == 1

        await client.archive_memory(memory_id=memory_id)

        search_after = await client.search_memory(query="fact", pool="facts")
        assert len(search_after.data) == 0

    @pytest.mark.asyncio
    async def test_archive_tracks_in_backend(self, client, backend):
        add_result = await client.add_memory(content="Track me", pool="facts")
        memory_id = add_result.data["id"]

        assert memory_id not in backend.archived_ids
        await client.archive_memory(memory_id=memory_id)
        assert memory_id in backend.archived_ids


# ============================================================
# Full E2E: All 8 steps in a single workflow
# ============================================================


class TestFullE2ETitansMemoryLifecycle:
    """Full end-to-end test: all 8 acceptance criteria in a single workflow."""

    @pytest.mark.asyncio
    async def test_complete_memory_lifecycle(self, client, backend):
        """Full E2E lifecycle covering all eight acceptance criteria."""
        # Step 1: Add facts
        fact_result = await client.add_memory(
            content="SQLite WAL mode allows concurrent reads",
            pool="facts",
        )
        assert fact_result.success is True
        fact_id = fact_result.data["id"]

        # Step 2: Add lessons
        lesson_result = await client.store_lesson(
            trigger_context="Database lock during concurrent writes",
            lesson="Use WAL mode for concurrent access",
            solution="Set journal_mode=WAL at connection time",
            feature_id="F094",
        )
        assert lesson_result.success is True
        lesson_id = lesson_result.data["id"]
        assert lesson_result.data["metadata"]["pool"] == "lessons"

        # Step 3: Search
        search_result = await client.search_memory(query="WAL mode")
        assert search_result.success is True
        assert len(search_result.data) == 2

        # Step 4: Ranking
        weights = [m["retrieval_weight"] for m in search_result.data]
        assert weights == sorted(weights, reverse=True)

        # Step 5: Feedback
        for _ in range(3):
            await client.record_feedback(memory_id=fact_id, success=True)

        # Step 6: Usefulness score increases
        assert backend._usefulness_score(fact_id) == pytest.approx(1.0)

        # Give the lesson mixed feedback so it's a candidate
        for _ in range(3):
            await client.record_feedback(memory_id=lesson_id, success=False)
        assert backend._usefulness_score(lesson_id) == pytest.approx(0.0)

        # Step 7: Candidates
        candidates = await client.get_demotion_candidates(limit=10)
        assert candidates.success is True
        candidate_ids = [c["id"] for c in candidates.data]
        assert lesson_id in candidate_ids
        assert fact_id not in candidate_ids

        # Step 8: Archive
        archive_result = await client.archive_memory(memory_id=lesson_id)
        assert archive_result.success is True

        post_archive = await client.search_memory(query="WAL mode", pool="lessons")
        assert len(post_archive.data) == 0

        fact_search = await client.search_memory(query="WAL mode", pool="facts")
        assert len(fact_search.data) == 1
        assert fact_search.data[0]["id"] == fact_id

    @pytest.mark.asyncio
    async def test_lifecycle_mixed_pools_independent(self, client, backend):
        """Facts and lessons in different pools should be independent."""
        fact = await client.add_memory(content="Fact 1", pool="facts")
        lesson = await client.store_lesson(trigger_context="T", lesson="L", solution="S")

        fact_id = fact.data["id"]

        await client.archive_memory(memory_id=fact_id)

        lesson_search = await client.search_memory(query="lesson", pool="lessons")
        assert len(lesson_search.data) == 1

        fact_search = await client.search_memory(query="fact", pool="facts")
        assert len(fact_search.data) == 0

    @pytest.mark.asyncio
    async def test_lifecycle_feedback_then_search_shows_updated_ranking(
        self, client, backend
    ):
        """After feedback, search ranking should reflect updated weights."""
        r1 = await client.add_memory(content="Fact A", pool="facts")
        r2 = await client.add_memory(content="Fact B", pool="facts")

        id_b = r2.data["id"]

        for _ in range(5):
            await client.record_feedback(memory_id=id_b, success=True)

        results = await client.search_memory(query="fact", pool="facts")
        assert results.data[0]["id"] == id_b
        assert (
            results.data[0]["retrieval_weight"]
            > results.data[1]["retrieval_weight"]
        )
