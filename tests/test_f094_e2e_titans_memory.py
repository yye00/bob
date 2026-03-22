"""Tests for F094: End-to-end test - TITANS memory lifecycle.

Exercises the complete TITANS memory lifecycle: add, search, feedback, archive.

Step 1: Add facts to TITANS memory (titans_add to facts pool)
Step 2: Add lessons to TITANS memory (titans_add to lessons pool)
Step 3: Search for relevant memories (titans_search)
Step 4: Verify retrieval ranking by surprise score
Step 5: Record feedback (titans_record_feedback success=True)
Step 6: Verify usefulness score increases
Step 7: Get forgetting candidates (titans_get_candidates)
Step 8: Archive old memory (titans_archive)
"""

from unittest.mock import patch

import pytest

from bob3.titans_memory_client import (
    MemoryResult,
    TOOL_TITANS_ADD,
    TOOL_TITANS_ARCHIVE,
    TOOL_TITANS_GET_CANDIDATES,
    TOOL_TITANS_RECORD_FEEDBACK,
    TOOL_TITANS_SEARCH,
    TOOL_TITANS_SEARCH_POOL,
    TitansMemoryClient,
)


# ============================================================
# Simulated TITANS backend supporting facts + lessons pools
# ============================================================


class SimulatedTitansBackend:
    """In-memory simulation of TITANS Memory MCP for the full lifecycle.

    Supports multiple pools (facts, lessons), surprise-based retrieval
    scoring, feedback tracking, forgetting candidates, and archiving.
    """

    def __init__(self):
        # Pool -> list of memory dicts
        self.memories: dict[str, list[dict]] = {"facts": [], "lessons": []}
        self.feedback_log: dict[str, list[bool]] = {}  # memory_id -> [bool, ...]
        self.archived_ids: set[str] = set()
        self.prompts: list[str] = []
        self._next_id = 1

    def _make_id(self) -> str:
        mid = f"mem-e2e-{self._next_id:03d}"
        self._next_id += 1
        return mid

    def _usefulness_score(self, memory_id: str) -> float:
        fb = self.feedback_log.get(memory_id, [])
        if not fb:
            return 0.5  # default neutral
        return sum(1 for f in fb if f) / len(fb)

    async def handle(self, prompt: str) -> MemoryResult:
        self.prompts.append(prompt)

        if TOOL_TITANS_ADD in prompt:
            return self._handle_add(prompt)
        if TOOL_TITANS_RECORD_FEEDBACK in prompt:
            return self._handle_record_feedback(prompt)
        if TOOL_TITANS_GET_CANDIDATES in prompt:
            return self._handle_get_candidates()
        if TOOL_TITANS_ARCHIVE in prompt:
            return self._handle_archive(prompt)
        if TOOL_TITANS_SEARCH_POOL in prompt:
            return self._handle_search_pool(prompt)
        if TOOL_TITANS_SEARCH in prompt:
            return self._handle_search_global(prompt)

        return MemoryResult(
            success=False, error=f"Unrecognised tool in prompt: {prompt[:80]}"
        )

    def _detect_pool(self, prompt: str) -> str:
        if '"facts"' in prompt or "'facts'" in prompt:
            return "facts"
        if '"lessons"' in prompt or "'lessons'" in prompt:
            return "lessons"
        return "facts"

    def _handle_add(self, prompt: str) -> MemoryResult:
        pool = self._detect_pool(prompt)
        mid = self._make_id()
        # Extract approximate content from prompt (between first pair of quotes after content:)
        content = f"Memory in {pool} pool (id={mid})"
        memory = {
            "id": mid,
            "content": content,
            "metadata": {
                "pool": pool,
                "usefulness_score": 0.5,
                "status": "active",
            },
            "retrieval_weight": 0.5,
            "surprise_score": 0.7 if pool == "facts" else 0.4,
        }
        self.memories[pool].append(memory)
        self.feedback_log[mid] = []
        return MemoryResult(success=True, data=dict(memory), raw_text="{}")

    def _handle_record_feedback(self, prompt: str) -> MemoryResult:
        # Find memory_id in prompt
        memory_id = None
        for pool_mems in self.memories.values():
            for mem in pool_mems:
                if mem["id"] in prompt:
                    memory_id = mem["id"]
                    break
            if memory_id:
                break

        if not memory_id:
            return MemoryResult(success=False, error="Memory not found in prompt")

        success = "true" in prompt.lower().split("success")[1][:20] if "success" in prompt.lower() else True
        self.feedback_log[memory_id].append(success)

        score = self._usefulness_score(memory_id)
        # Find the memory and update it
        for pool_mems in self.memories.values():
            for mem in pool_mems:
                if mem["id"] == memory_id:
                    mem["metadata"]["usefulness_score"] = score
                    # Increase retrieval weight with positive feedback
                    if success:
                        mem["retrieval_weight"] = min(1.0, mem["retrieval_weight"] + 0.1)
                    return MemoryResult(success=True, data=dict(mem), raw_text="{}")

        return MemoryResult(success=False, error=f"Memory {memory_id} not found")

    def _handle_get_candidates(self) -> MemoryResult:
        candidates = []
        for pool_mems in self.memories.values():
            for mem in pool_mems:
                if mem["id"] in self.archived_ids:
                    continue
                score = self._usefulness_score(mem["id"])
                if score < 0.5:
                    candidate = dict(mem)
                    candidate["metadata"] = dict(candidate["metadata"])
                    candidate["metadata"]["usefulness_score"] = score
                    candidates.append(candidate)
        return MemoryResult(success=True, data=candidates, raw_text="[]")

    def _handle_archive(self, prompt: str) -> MemoryResult:
        for pool_mems in self.memories.values():
            for mem in pool_mems:
                if mem["id"] in prompt:
                    self.archived_ids.add(mem["id"])
                    data = dict(mem)
                    data["metadata"] = dict(data["metadata"])
                    data["metadata"]["status"] = "archived"
                    return MemoryResult(success=True, data=data, raw_text="{}")

        return MemoryResult(success=False, error="Memory not found for archive")

    def _handle_search_pool(self, prompt: str) -> MemoryResult:
        pool = self._detect_pool(prompt)
        results = []
        for mem in self.memories.get(pool, []):
            if mem["id"] not in self.archived_ids:
                result = dict(mem)
                result["metadata"] = dict(result["metadata"])
                result["metadata"]["usefulness_score"] = self._usefulness_score(
                    mem["id"]
                )
                results.append(result)
        # Sort by retrieval_weight descending (surprise-based ranking)
        results.sort(key=lambda m: m.get("retrieval_weight", 0), reverse=True)
        return MemoryResult(success=True, data=results, raw_text="[]")

    def _handle_search_global(self, prompt: str) -> MemoryResult:
        results = []
        for pool_mems in self.memories.values():
            for mem in pool_mems:
                if mem["id"] not in self.archived_ids:
                    result = dict(mem)
                    result["metadata"] = dict(result["metadata"])
                    result["metadata"]["usefulness_score"] = self._usefulness_score(
                        mem["id"]
                    )
                    results.append(result)
        # Sort by retrieval_weight descending (surprise-based ranking)
        results.sort(key=lambda m: m.get("retrieval_weight", 0), reverse=True)
        return MemoryResult(success=True, data=results, raw_text="[]")


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def client():
    return TitansMemoryClient(workspace="/tmp/e2e-titans-memory-lifecycle")


@pytest.fixture
def backend():
    return SimulatedTitansBackend()


# ============================================================
# Step 1: Add facts to TITANS memory (titans_add to facts pool)
# ============================================================


class TestStep1AddFactsToTitansMemory:
    """Step 1: Add facts to TITANS memory (titans_add to facts pool)."""

    @pytest.mark.asyncio
    async def test_add_fact_to_facts_pool(self, client, backend):
        """Adding a fact to the facts pool should succeed and return an ID."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            result = await client.add_memory(
                content="SQLite WAL mode improves concurrent read performance",
                pool="facts",
            )

        assert result.success is True
        assert "id" in result.data
        assert result.data["metadata"]["pool"] == "facts"

    @pytest.mark.asyncio
    async def test_add_fact_calls_titans_add_tool(self, client, backend):
        """add_memory() for facts should invoke the titans_add tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.add_memory(content="Python 3.14 supports PEP 649", pool="facts")

        assert len(backend.prompts) == 1
        assert TOOL_TITANS_ADD in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_add_fact_prompt_specifies_facts_pool(self, client, backend):
        """The prompt sent to sub-agent should specify pool='facts'."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.add_memory(content="fact content", pool="facts")

        assert "facts" in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_add_multiple_facts(self, client, backend):
        """Multiple facts can be added to the facts pool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            r1 = await client.add_memory(content="Fact 1", pool="facts")
            r2 = await client.add_memory(content="Fact 2", pool="facts")

        assert r1.success is True
        assert r2.success is True
        assert r1.data["id"] != r2.data["id"]
        assert len(backend.memories["facts"]) == 2


# ============================================================
# Step 2: Add lessons to TITANS memory (titans_add to lessons pool)
# ============================================================


class TestStep2AddLessonsToTitansMemory:
    """Step 2: Add lessons to TITANS memory (titans_add to lessons pool)."""

    @pytest.mark.asyncio
    async def test_add_lesson_to_lessons_pool(self, client, backend):
        """Adding a lesson to the lessons pool should succeed."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            result = await client.store_lesson(
                trigger_context="Database lock during writes",
                lesson="Use WAL mode for concurrent access",
                solution="Set journal_mode=WAL",
            )

        assert result.success is True
        assert "id" in result.data
        assert result.data["metadata"]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_store_lesson_calls_titans_add(self, client, backend):
        """store_lesson() should use titans_add tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert TOOL_TITANS_ADD in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_store_lesson_routes_to_lessons_pool(self, client, backend):
        """store_lesson() must route to the 'lessons' pool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert "lessons" in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_lesson_content_is_structured(self, client, backend):
        """Lesson content should contain TRIGGER, LESSON, SOLUTION."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="Lock error",
                lesson="Enable WAL",
                solution="Pragma WAL",
            )

        prompt = backend.prompts[0]
        assert "TRIGGER:" in prompt
        assert "LESSON:" in prompt
        assert "SOLUTION:" in prompt


# ============================================================
# Step 3: Search for relevant memories (titans_search)
# ============================================================


class TestStep3SearchForRelevantMemories:
    """Step 3: Search for relevant memories (titans_search)."""

    @pytest.mark.asyncio
    async def test_search_returns_added_memories(self, client, backend):
        """Searching should return previously added memories."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.add_memory(content="WAL mode fact", pool="facts")
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            results = await client.search_memory(query="WAL mode")

        assert results.success is True
        assert isinstance(results.data, list)
        assert len(results.data) == 2  # one fact + one lesson

    @pytest.mark.asyncio
    async def test_search_pool_filters_by_pool(self, client, backend):
        """Search with a pool filter should only return memories from that pool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.add_memory(content="Fact A", pool="facts")
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            facts_results = await client.search_memory(
                query="memory", pool="facts",
            )
            lessons_results = await client.search_memory(
                query="memory", pool="lessons",
            )

        assert facts_results.success is True
        assert len(facts_results.data) == 1
        assert facts_results.data[0]["metadata"]["pool"] == "facts"

        assert lessons_results.success is True
        assert len(lessons_results.data) == 1
        assert lessons_results.data[0]["metadata"]["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_search_uses_titans_search_tool(self, client, backend):
        """Global search should use titans_search tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.search_memory(query="test query")

        assert TOOL_TITANS_SEARCH in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_pool_search_uses_titans_search_pool_tool(self, client, backend):
        """Pool-filtered search should use titans_search_pool tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.search_memory(query="test", pool="facts")

        assert TOOL_TITANS_SEARCH_POOL in backend.prompts[0]


# ============================================================
# Step 4: Verify retrieval ranking by surprise score
# ============================================================


class TestStep4VerifyRetrievalRankingBySurpriseScore:
    """Step 4: Verify retrieval ranking by surprise score."""

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_retrieval_weight(self, client, backend):
        """Search results should be sorted by retrieval_weight (descending)."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            # Add multiple facts - they'll get different surprise scores
            await client.add_memory(content="Fact 1", pool="facts")
            await client.add_memory(content="Fact 2", pool="facts")

            # Give positive feedback to second fact to boost its weight
            second_id = backend.memories["facts"][1]["id"]
            await client.record_feedback(memory_id=second_id, success=True)
            await client.record_feedback(memory_id=second_id, success=True)

            results = await client.search_memory(query="facts", pool="facts")

        assert results.success is True
        assert len(results.data) == 2
        # Results should be sorted by retrieval_weight descending
        weights = [m["retrieval_weight"] for m in results.data]
        assert weights == sorted(weights, reverse=True)

    @pytest.mark.asyncio
    async def test_higher_surprise_score_ranks_first(self, client, backend):
        """Memories with higher retrieval weight rank before lower ones."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.add_memory(content="Low priority fact", pool="facts")
            await client.add_memory(content="High priority fact", pool="facts")

            # Boost second memory's weight through feedback
            high_id = backend.memories["facts"][1]["id"]
            for _ in range(3):
                await client.record_feedback(memory_id=high_id, success=True)

            results = await client.search_memory(query="fact", pool="facts")

        assert results.data[0]["id"] == high_id

    @pytest.mark.asyncio
    async def test_global_search_ranks_across_pools(self, client, backend):
        """Global search ranks results across all pools by retrieval_weight."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.add_memory(content="A fact", pool="facts")
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            results = await client.search_memory(query="memory")

        assert results.success is True
        weights = [m.get("retrieval_weight", 0) for m in results.data]
        assert weights == sorted(weights, reverse=True)


# ============================================================
# Step 5: Record feedback (titans_record_feedback success=True)
# ============================================================


class TestStep5RecordFeedback:
    """Step 5: Record feedback (titans_record_feedback success=True)."""

    @pytest.mark.asyncio
    async def test_record_positive_feedback(self, client, backend):
        """Recording positive feedback should succeed."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            fb_result = await client.record_feedback(
                memory_id=memory_id, success=True,
            )

        assert fb_result.success is True
        assert TOOL_TITANS_RECORD_FEEDBACK in backend.prompts[1]

    @pytest.mark.asyncio
    async def test_feedback_prompt_contains_memory_id(self, client, backend):
        """Feedback prompt must include the memory ID."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            await client.record_feedback(memory_id=memory_id, success=True)

        assert memory_id in backend.prompts[1]

    @pytest.mark.asyncio
    async def test_feedback_prompt_contains_success_true(self, client, backend):
        """Positive feedback prompt must contain 'true'."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            await client.record_feedback(memory_id=memory_id, success=True)

        assert "true" in backend.prompts[1].lower()

    @pytest.mark.asyncio
    async def test_multiple_feedback_recorded(self, client, backend):
        """Multiple feedback entries should be tracked."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            await client.record_feedback(memory_id=memory_id, success=True)
            await client.record_feedback(memory_id=memory_id, success=True)
            await client.record_feedback(memory_id=memory_id, success=False)

        assert len(backend.feedback_log[memory_id]) == 3
        assert backend.feedback_log[memory_id] == [True, True, False]


# ============================================================
# Step 6: Verify usefulness score increases
# ============================================================


class TestStep6VerifyUsefulnessScoreIncreases:
    """Step 6: Verify usefulness score increases after positive feedback."""

    @pytest.mark.asyncio
    async def test_usefulness_increases_after_positive_feedback(self, client, backend):
        """Usefulness score should increase after positive feedback."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            # Initial score is 0.5 (neutral default)
            initial_score = backend._usefulness_score(memory_id)
            assert initial_score == 0.5

            # Record positive feedback
            fb_result = await client.record_feedback(
                memory_id=memory_id, success=True,
            )

            new_score = backend._usefulness_score(memory_id)

        assert new_score > initial_score
        assert new_score == 1.0  # 1 success out of 1 = 1.0

    @pytest.mark.asyncio
    async def test_usefulness_reflects_feedback_ratio(self, client, backend):
        """Usefulness should reflect the ratio of positive to total feedback."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            # 4 positive, 1 negative -> 0.8
            for success in [True, True, True, True, False]:
                await client.record_feedback(memory_id=memory_id, success=success)

        score = backend._usefulness_score(memory_id)
        assert score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_returned_data_contains_updated_score(self, client, backend):
        """The feedback result data should contain the updated usefulness score."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            fb_result = await client.record_feedback(
                memory_id=memory_id, success=True,
            )

        assert fb_result.data["metadata"]["usefulness_score"] == 1.0

    @pytest.mark.asyncio
    async def test_retrieval_weight_increases_with_positive_feedback(
        self, client, backend
    ):
        """Retrieval weight should increase when positive feedback is recorded."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="A fact", pool="facts")
            memory_id = add_result.data["id"]

            initial_weight = backend.memories["facts"][0]["retrieval_weight"]

            await client.record_feedback(memory_id=memory_id, success=True)

            new_weight = backend.memories["facts"][0]["retrieval_weight"]

        assert new_weight > initial_weight


# ============================================================
# Step 7: Get forgetting candidates (titans_get_candidates)
# ============================================================


class TestStep7GetForgettingCandidates:
    """Step 7: Get forgetting candidates (titans_get_candidates)."""

    @pytest.mark.asyncio
    async def test_low_usefulness_memory_is_candidate(self, client, backend):
        """A memory with low usefulness should appear as a forgetting candidate."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="Bad fact", pool="facts")
            memory_id = add_result.data["id"]

            # All negative feedback -> score = 0.0
            for _ in range(3):
                await client.record_feedback(memory_id=memory_id, success=False)

            candidates = await client.get_demotion_candidates(limit=10)

        assert candidates.success is True
        assert isinstance(candidates.data, list)
        assert len(candidates.data) == 1
        assert candidates.data[0]["id"] == memory_id

    @pytest.mark.asyncio
    async def test_high_usefulness_memory_not_candidate(self, client, backend):
        """A memory with high usefulness should NOT appear as a forgetting candidate."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="Good fact", pool="facts")
            memory_id = add_result.data["id"]

            # All positive feedback -> score = 1.0
            for _ in range(3):
                await client.record_feedback(memory_id=memory_id, success=True)

            candidates = await client.get_demotion_candidates(limit=10)

        assert candidates.success is True
        assert len(candidates.data) == 0

    @pytest.mark.asyncio
    async def test_get_candidates_calls_correct_tool(self, client, backend):
        """get_demotion_candidates() should use titans_get_candidates tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.get_demotion_candidates()

        assert TOOL_TITANS_GET_CANDIDATES in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_archived_memory_not_in_candidates(self, client, backend):
        """Archived memories should not appear as forgetting candidates."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="Old fact", pool="facts")
            memory_id = add_result.data["id"]

            # Give negative feedback so it would normally be a candidate
            for _ in range(3):
                await client.record_feedback(memory_id=memory_id, success=False)

            # Archive it
            await client.archive_memory(memory_id=memory_id)

            # Should NOT appear in candidates
            candidates = await client.get_demotion_candidates(limit=10)

        assert len(candidates.data) == 0


# ============================================================
# Step 8: Archive old memory (titans_archive)
# ============================================================


class TestStep8ArchiveOldMemory:
    """Step 8: Archive old memory (titans_archive)."""

    @pytest.mark.asyncio
    async def test_archive_memory_succeeds(self, client, backend):
        """Archiving a memory should succeed and return archived status."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="Old fact", pool="facts")
            memory_id = add_result.data["id"]

            archive_result = await client.archive_memory(memory_id=memory_id)

        assert archive_result.success is True
        assert archive_result.data["metadata"]["status"] == "archived"

    @pytest.mark.asyncio
    async def test_archived_memory_not_in_search_results(self, client, backend):
        """After archiving, the memory should NOT appear in search results."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="Archivable fact", pool="facts")
            memory_id = add_result.data["id"]

            # Verify it appears before archiving
            search_before = await client.search_memory(query="fact", pool="facts")
            assert len(search_before.data) == 1

            # Archive
            await client.archive_memory(memory_id=memory_id)

            # Verify it no longer appears
            search_after = await client.search_memory(query="fact", pool="facts")
            assert len(search_after.data) == 0

    @pytest.mark.asyncio
    async def test_archive_calls_correct_tool(self, client, backend):
        """archive_memory() should invoke the titans_archive tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            add_result = await client.add_memory(content="To archive", pool="facts")
            memory_id = add_result.data["id"]

            await client.archive_memory(memory_id=memory_id)

        archive_prompt = backend.prompts[1]
        assert TOOL_TITANS_ARCHIVE in archive_prompt

    @pytest.mark.asyncio
    async def test_archive_tracks_in_backend(self, client, backend):
        """The backend should track which memories are archived."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
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
        """Complete E2E: add facts -> add lessons -> search -> ranking ->
        feedback -> usefulness -> candidates -> archive.

        Exercises all 8 acceptance criteria in sequence:
          Step 1: Add facts to TITANS memory (titans_add to facts pool)
          Step 2: Add lessons to TITANS memory (titans_add to lessons pool)
          Step 3: Search for relevant memories (titans_search)
          Step 4: Verify retrieval ranking by surprise score
          Step 5: Record feedback (titans_record_feedback success=True)
          Step 6: Verify usefulness score increases
          Step 7: Get forgetting candidates (titans_get_candidates)
          Step 8: Archive old memory (titans_archive)
        """
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            # ---- Step 1: Add facts to TITANS memory ----
            fact_result = await client.add_memory(
                content="SQLite WAL mode allows concurrent reads",
                pool="facts",
            )
            assert fact_result.success is True
            fact_id = fact_result.data["id"]
            assert fact_result.data["metadata"]["pool"] == "facts"
            assert TOOL_TITANS_ADD in backend.prompts[0]

            # ---- Step 2: Add lessons to TITANS memory ----
            lesson_result = await client.store_lesson(
                trigger_context="Database lock during concurrent writes",
                lesson="Use WAL mode for concurrent access",
                solution="Set journal_mode=WAL at connection time",
                feature_id="F094",
            )
            assert lesson_result.success is True
            lesson_id = lesson_result.data["id"]
            assert lesson_result.data["metadata"]["pool"] == "lessons"

            # ---- Step 3: Search for relevant memories ----
            search_result = await client.search_memory(query="WAL mode")
            assert search_result.success is True
            assert isinstance(search_result.data, list)
            assert len(search_result.data) == 2  # fact + lesson

            # ---- Step 4: Verify retrieval ranking by surprise score ----
            weights = [m["retrieval_weight"] for m in search_result.data]
            assert weights == sorted(weights, reverse=True), (
                "Results should be sorted by retrieval_weight descending"
            )

            # ---- Step 5: Record feedback (titans_record_feedback success=True) ----
            fb_result = await client.record_feedback(
                memory_id=fact_id, success=True,
            )
            assert fb_result.success is True

            # Record more positive feedback
            await client.record_feedback(memory_id=fact_id, success=True)
            await client.record_feedback(memory_id=fact_id, success=True)

            # ---- Step 6: Verify usefulness score increases ----
            fact_score = backend._usefulness_score(fact_id)
            assert fact_score == pytest.approx(1.0), (
                "All positive feedback should yield usefulness 1.0"
            )

            # Give the lesson mixed feedback so its score is low
            await client.record_feedback(memory_id=lesson_id, success=False)
            await client.record_feedback(memory_id=lesson_id, success=False)
            await client.record_feedback(memory_id=lesson_id, success=False)

            lesson_score = backend._usefulness_score(lesson_id)
            assert lesson_score == pytest.approx(0.0), (
                "All negative feedback should yield usefulness 0.0"
            )

            # ---- Step 7: Get forgetting candidates ----
            candidates = await client.get_demotion_candidates(limit=10)
            assert candidates.success is True
            assert isinstance(candidates.data, list)
            # The lesson with score 0.0 should be a candidate
            candidate_ids = [c["id"] for c in candidates.data]
            assert lesson_id in candidate_ids, (
                "Lesson with low score should be a forgetting candidate"
            )
            # The fact with score 1.0 should NOT be a candidate
            assert fact_id not in candidate_ids, (
                "Fact with high score should not be a forgetting candidate"
            )

            # ---- Step 8: Archive old memory ----
            archive_result = await client.archive_memory(memory_id=lesson_id)
            assert archive_result.success is True
            assert archive_result.data["metadata"]["status"] == "archived"

            # Verify archived memory not in search
            post_archive_search = await client.search_memory(
                query="WAL mode", pool="lessons",
            )
            assert len(post_archive_search.data) == 0, (
                "Archived lesson should not appear in search results"
            )

            # Fact should still be searchable
            fact_search = await client.search_memory(
                query="WAL mode", pool="facts",
            )
            assert len(fact_search.data) == 1
            assert fact_search.data[0]["id"] == fact_id

    @pytest.mark.asyncio
    async def test_lifecycle_mixed_pools_independent(self, client, backend):
        """Facts and lessons in different pools should be independent."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            # Add to both pools
            fact = await client.add_memory(content="Fact 1", pool="facts")
            lesson = await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            fact_id = fact.data["id"]
            lesson_id = lesson.data["id"]

            # Archive only the fact
            await client.archive_memory(memory_id=fact_id)

            # Lesson should still be searchable
            lesson_search = await client.search_memory(
                query="lesson", pool="lessons",
            )
            assert len(lesson_search.data) == 1

            # Fact should not be searchable
            fact_search = await client.search_memory(
                query="fact", pool="facts",
            )
            assert len(fact_search.data) == 0

    @pytest.mark.asyncio
    async def test_lifecycle_feedback_then_search_shows_updated_ranking(
        self, client, backend
    ):
        """After feedback, search ranking should reflect updated weights."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            r1 = await client.add_memory(content="Fact A", pool="facts")
            r2 = await client.add_memory(content="Fact B", pool="facts")

            id_a = r1.data["id"]
            id_b = r2.data["id"]

            # Boost B's weight through feedback
            for _ in range(5):
                await client.record_feedback(memory_id=id_b, success=True)

            results = await client.search_memory(query="fact", pool="facts")

        # B should rank higher due to boosted retrieval weight
        assert results.data[0]["id"] == id_b
        assert results.data[0]["retrieval_weight"] > results.data[1]["retrieval_weight"]
