"""Tests for F091: End-to-end test - TITANS Memory lesson lifecycle.

Exercises the complete lesson lifecycle via the TitansMemoryClient:

Step 1: Create lesson via titans_add (pool='lessons')
Step 2: Record feedback via titans_record_feedback (mix success/fail)
Step 3: Verify usefulness_score via titans_get_stats
Step 4: Get candidates via titans_get_candidates
Step 5: Demote lesson via titans_demote, verify status
Step 6: Archive lesson via titans_archive, verify not in search results
"""

from unittest.mock import patch

import pytest

from bob3.titans_memory_client import (
    MemoryResult,
    TOOL_TITANS_ADD,
    TOOL_TITANS_ARCHIVE,
    TOOL_TITANS_DEMOTE,
    TOOL_TITANS_GET_CANDIDATES,
    TOOL_TITANS_GET_STATS,
    TOOL_TITANS_RECORD_FEEDBACK,
    TOOL_TITANS_SEARCH_POOL,
    TitansMemoryClient,
)


# ============================================================
# Shared fixture: client with tracked prompts
# ============================================================


@pytest.fixture
def client():
    """Create a TitansMemoryClient for testing."""
    return TitansMemoryClient(workspace="/tmp/e2e-lesson-lifecycle")


# ============================================================
# Shared state for the simulated MCP backend
# ============================================================


class SimulatedTitansBackend:
    """In-memory simulation of TITANS Memory MCP behaviour.

    Tracks a single lesson memory and responds to tool calls appropriately,
    maintaining state across the full lifecycle so the E2E test flows
    naturally through all six steps.
    """

    def __init__(self):
        self.memory = None
        self.feedback_log = []  # list of bools
        self.archived = False
        self.demoted = False
        self.prompts = []

    @property
    def usefulness_score(self):
        """Compute usefulness from recorded feedback (fraction of successes)."""
        if not self.feedback_log:
            return 0.5  # default neutral
        return sum(1 for f in self.feedback_log if f) / len(self.feedback_log)

    async def handle(self, prompt: str) -> MemoryResult:
        """Route a prompt to the appropriate simulated tool handler."""
        self.prompts.append(prompt)

        if TOOL_TITANS_ADD in prompt:
            return self._handle_add(prompt)
        if TOOL_TITANS_RECORD_FEEDBACK in prompt:
            return self._handle_record_feedback(prompt)
        if TOOL_TITANS_GET_STATS in prompt:
            return self._handle_get_stats()
        if TOOL_TITANS_GET_CANDIDATES in prompt:
            return self._handle_get_candidates()
        if TOOL_TITANS_DEMOTE in prompt:
            return self._handle_demote(prompt)
        if TOOL_TITANS_ARCHIVE in prompt:
            return self._handle_archive(prompt)
        if TOOL_TITANS_SEARCH_POOL in prompt or "titans_search" in prompt:
            return self._handle_search(prompt)

        return MemoryResult(success=False, error=f"Unrecognised tool in prompt: {prompt[:80]}")

    def _handle_add(self, prompt: str) -> MemoryResult:
        self.memory = {
            "id": "mem-lesson-e2e-001",
            "content": "TRIGGER: SQLite lock during concurrent writes\n"
                       "LESSON: Use WAL mode for concurrent access\n"
                       "SOLUTION: Set journal_mode=WAL at connection time",
            "metadata": {
                "pool": "lessons",
                "feature_id": "F091",
                "error_type": "OperationalError",
                "usefulness_score": 0.5,
                "status": "active",
            },
        }
        return MemoryResult(success=True, data=dict(self.memory), raw_text="{}")

    def _handle_record_feedback(self, prompt: str) -> MemoryResult:
        success = "true" in prompt.lower().split("success")[1][:20] if "success" in prompt.lower() else True
        self.feedback_log.append(success)
        score = self.usefulness_score
        data = dict(self.memory)
        data["metadata"] = dict(data["metadata"])
        data["metadata"]["usefulness_score"] = score
        return MemoryResult(success=True, data=data, raw_text="{}")

    def _handle_get_stats(self) -> MemoryResult:
        stats = {
            "total_memories": 1 if self.memory else 0,
            "pools": {
                "lessons": {
                    "count": 1 if self.memory and not self.archived else 0,
                    "avg_usefulness": self.usefulness_score,
                },
            },
            "global_usefulness_score": self.usefulness_score,
        }
        return MemoryResult(success=True, data=stats, raw_text="{}")

    def _handle_get_candidates(self) -> MemoryResult:
        if self.memory and not self.archived and self.usefulness_score < 0.6:
            candidate = dict(self.memory)
            candidate["metadata"] = dict(candidate["metadata"])
            candidate["metadata"]["usefulness_score"] = self.usefulness_score
            return MemoryResult(success=True, data=[candidate], raw_text="[]")
        return MemoryResult(success=True, data=[], raw_text="[]")

    def _handle_demote(self, prompt: str) -> MemoryResult:
        self.demoted = True
        data = dict(self.memory)
        data["metadata"] = dict(data["metadata"])
        data["metadata"]["status"] = "demoted"
        return MemoryResult(success=True, data=data, raw_text="{}")

    def _handle_archive(self, prompt: str) -> MemoryResult:
        self.archived = True
        data = dict(self.memory)
        data["metadata"] = dict(data["metadata"])
        data["metadata"]["status"] = "archived"
        return MemoryResult(success=True, data=data, raw_text="{}")

    def _handle_search(self, prompt: str) -> MemoryResult:
        if self.archived:
            return MemoryResult(success=True, data=[], raw_text="[]")
        if self.memory:
            result = dict(self.memory)
            result["metadata"] = dict(result["metadata"])
            result["retrieval_weight"] = 0.3 if self.demoted else 0.8
            return MemoryResult(success=True, data=[result], raw_text="[]")
        return MemoryResult(success=True, data=[], raw_text="[]")


@pytest.fixture
def backend():
    return SimulatedTitansBackend()


# ============================================================
# Step 1: Create lesson via titans_add (pool='lessons')
# ============================================================


class TestStep1CreateLessonViaTitansAdd:
    """Step 1: Create lesson via titans_add (pool='lessons')."""

    @pytest.mark.asyncio
    async def test_store_lesson_calls_titans_add(self, client, backend):
        """store_lesson() should call titans_add and return a memory with an ID."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            result = await client.store_lesson(
                trigger_context="SQLite lock during concurrent writes",
                lesson="Use WAL mode for concurrent access",
                solution="Set journal_mode=WAL at connection time",
                feature_id="F091",
                error_type="OperationalError",
            )

        assert result.success is True
        assert result.data["id"] == "mem-lesson-e2e-001"
        assert TOOL_TITANS_ADD in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_lesson_routed_to_lessons_pool(self, client, backend):
        """The lesson must be stored in the 'lessons' pool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            result = await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )

        assert result.success is True
        assert "lessons" in backend.prompts[0]

    @pytest.mark.asyncio
    async def test_lesson_content_is_structured(self, client, backend):
        """Content should contain TRIGGER, LESSON, SOLUTION."""
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

    @pytest.mark.asyncio
    async def test_memory_object_created_in_backend(self, client, backend):
        """After storing, the backend should have a memory object."""
        assert backend.memory is None
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T",
                lesson="L",
                solution="S",
            )
        assert backend.memory is not None
        assert backend.memory["id"] == "mem-lesson-e2e-001"


# ============================================================
# Step 2: Record feedback via titans_record_feedback (mix success/fail)
# ============================================================


class TestStep2RecordFeedbackMixSuccessFail:
    """Step 2: Record feedback via titans_record_feedback (mix success/fail)."""

    @pytest.mark.asyncio
    async def test_record_mixed_feedback(self, client, backend):
        """Record a mix of success and failure feedback on the lesson."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            # Create lesson first
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            # Record 3 successes, 2 failures
            feedback_results = []
            for success in [True, True, False, True, False]:
                result = await client.record_feedback(
                    memory_id=memory_id, success=success,
                )
                feedback_results.append(result)

        assert all(r.success for r in feedback_results)
        assert len(backend.feedback_log) == 5
        assert backend.feedback_log == [True, True, False, True, False]

    @pytest.mark.asyncio
    async def test_feedback_calls_use_correct_tool(self, client, backend):
        """Each feedback call should use the titans_record_feedback tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            await client.record_feedback(memory_id=memory_id, success=True)
            await client.record_feedback(memory_id=memory_id, success=False)

        # prompts[0] is store_lesson (titans_add)
        # prompts[1] and prompts[2] are record_feedback
        assert TOOL_TITANS_RECORD_FEEDBACK in backend.prompts[1]
        assert TOOL_TITANS_RECORD_FEEDBACK in backend.prompts[2]

    @pytest.mark.asyncio
    async def test_feedback_contains_memory_id(self, client, backend):
        """The feedback prompt must include the memory ID."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            await client.record_feedback(
                memory_id="mem-lesson-e2e-001", success=True,
            )

        assert "mem-lesson-e2e-001" in backend.prompts[1]

    @pytest.mark.asyncio
    async def test_feedback_result_includes_updated_score(self, client, backend):
        """After feedback, the returned data should include updated usefulness."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            # Record only successes -> score should be 1.0
            result = await client.record_feedback(
                memory_id=memory_id, success=True,
            )

        assert result.success is True
        assert result.data["metadata"]["usefulness_score"] == 1.0


# ============================================================
# Step 3: Verify usefulness_score via titans_get_stats
# ============================================================


class TestStep3VerifyUsefulnessScoreViaGetStats:
    """Step 3: Verify usefulness_score via titans_get_stats."""

    @pytest.mark.asyncio
    async def test_get_stats_returns_usefulness_score(self, client, backend):
        """After mixed feedback, get_stats should reflect the calculated score."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            # 3 success, 2 failure -> score = 0.6
            for success in [True, True, False, True, False]:
                await client.record_feedback(memory_id=memory_id, success=success)

            stats_result = await client.get_stats()

        assert stats_result.success is True
        assert "pools" in stats_result.data
        lessons_stats = stats_result.data["pools"]["lessons"]
        assert lessons_stats["count"] == 1
        assert lessons_stats["avg_usefulness"] == pytest.approx(0.6, abs=0.01)

    @pytest.mark.asyncio
    async def test_get_stats_calls_correct_tool(self, client, backend):
        """get_stats() should call the titans_get_stats tool."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            await client.get_stats()

        stats_prompt = backend.prompts[1]
        assert TOOL_TITANS_GET_STATS in stats_prompt

    @pytest.mark.asyncio
    async def test_global_usefulness_score_after_all_success(self, client, backend):
        """All positive feedback should yield usefulness_score of 1.0."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            for _ in range(5):
                await client.record_feedback(memory_id=memory_id, success=True)

            stats = await client.get_stats()

        assert stats.data["global_usefulness_score"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_global_usefulness_score_after_all_failure(self, client, backend):
        """All negative feedback should yield usefulness_score of 0.0."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            for _ in range(5):
                await client.record_feedback(memory_id=memory_id, success=False)

            stats = await client.get_stats()

        assert stats.data["global_usefulness_score"] == pytest.approx(0.0)


# ============================================================
# Step 4: Get candidates via titans_get_candidates
# ============================================================


class TestStep4GetCandidatesViaTitansGetCandidates:
    """Step 4: Get candidates via titans_get_candidates."""

    @pytest.mark.asyncio
    async def test_low_usefulness_appears_as_candidate(self, client, backend):
        """A lesson with low usefulness should appear in demotion candidates."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            # Record mostly failures: 1 success, 4 failures -> score = 0.2
            for success in [True, False, False, False, False]:
                await client.record_feedback(memory_id=memory_id, success=success)

            candidates_result = await client.get_demotion_candidates(limit=10)

        assert candidates_result.success is True
        assert isinstance(candidates_result.data, list)
        assert len(candidates_result.data) == 1
        assert candidates_result.data[0]["id"] == "mem-lesson-e2e-001"

    @pytest.mark.asyncio
    async def test_high_usefulness_not_a_candidate(self, client, backend):
        """A lesson with high usefulness should NOT appear in demotion candidates."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            # All successes -> score = 1.0
            for _ in range(5):
                await client.record_feedback(memory_id=memory_id, success=True)

            candidates_result = await client.get_demotion_candidates(limit=10)

        assert candidates_result.success is True
        assert isinstance(candidates_result.data, list)
        assert len(candidates_result.data) == 0

    @pytest.mark.asyncio
    async def test_get_candidates_calls_correct_tool(self, client, backend):
        """get_demotion_candidates() should call titans_get_candidates."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            await client.get_demotion_candidates()

        candidates_prompt = backend.prompts[1]
        assert TOOL_TITANS_GET_CANDIDATES in candidates_prompt

    @pytest.mark.asyncio
    async def test_candidate_usefulness_score_is_low(self, client, backend):
        """Returned candidate should have a low usefulness score."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            memory_id = backend.memory["id"]

            # 1/5 success -> 0.2
            for success in [True, False, False, False, False]:
                await client.record_feedback(memory_id=memory_id, success=success)

            candidates_result = await client.get_demotion_candidates()

        candidate = candidates_result.data[0]
        assert candidate["metadata"]["usefulness_score"] == pytest.approx(0.2)


# ============================================================
# Step 5: Demote lesson via titans_demote, verify status
# ============================================================


class TestStep5DemoteLessonViaTitansDemote:
    """Step 5: Demote lesson via titans_demote, verify status."""

    @pytest.mark.asyncio
    async def test_demote_lesson_returns_demoted_status(self, client, backend):
        """Demoting a lesson should return status='demoted'."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            demote_result = await client.demote_memory(
                memory_id="mem-lesson-e2e-001",
            )

        assert demote_result.success is True
        assert demote_result.data["metadata"]["status"] == "demoted"

    @pytest.mark.asyncio
    async def test_demote_sets_backend_flag(self, client, backend):
        """After demoting, the backend should track the demoted state."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            assert backend.demoted is False

            await client.demote_memory(memory_id="mem-lesson-e2e-001")

        assert backend.demoted is True

    @pytest.mark.asyncio
    async def test_demote_calls_correct_tool(self, client, backend):
        """demote_memory() should call titans_demote."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            await client.demote_memory(memory_id="mem-lesson-e2e-001")

        demote_prompt = backend.prompts[1]
        assert TOOL_TITANS_DEMOTE in demote_prompt

    @pytest.mark.asyncio
    async def test_demoted_lesson_has_lower_retrieval_weight(self, client, backend):
        """A demoted lesson should have a lower retrieval weight in search results."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            # Search before demoting
            search_before = await client.search_memory(
                query="WAL mode", pool="lessons",
            )
            weight_before = search_before.data[0]["retrieval_weight"]

            # Demote
            await client.demote_memory(memory_id="mem-lesson-e2e-001")

            # Search after demoting
            search_after = await client.search_memory(
                query="WAL mode", pool="lessons",
            )
            weight_after = search_after.data[0]["retrieval_weight"]

        assert weight_after < weight_before


# ============================================================
# Step 6: Archive lesson via titans_archive, verify not in search results
# ============================================================


class TestStep6ArchiveLessonViaTitansArchive:
    """Step 6: Archive lesson via titans_archive, verify not in search results."""

    @pytest.mark.asyncio
    async def test_archive_lesson_returns_archived_status(self, client, backend):
        """Archiving a lesson should return status='archived'."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            archive_result = await client.archive_memory(
                memory_id="mem-lesson-e2e-001",
            )

        assert archive_result.success is True
        assert archive_result.data["metadata"]["status"] == "archived"

    @pytest.mark.asyncio
    async def test_archived_lesson_not_in_search_results(self, client, backend):
        """After archiving, the lesson should NOT appear in search results."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            # Verify it appears before archiving
            search_before = await client.search_memory(
                query="WAL mode", pool="lessons",
            )
            assert len(search_before.data) == 1

            # Archive it
            await client.archive_memory(memory_id="mem-lesson-e2e-001")

            # Verify it no longer appears in search
            search_after = await client.search_memory(
                query="WAL mode", pool="lessons",
            )
            assert len(search_after.data) == 0

    @pytest.mark.asyncio
    async def test_archive_sets_backend_flag(self, client, backend):
        """After archiving, the backend should track the archived state."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            assert backend.archived is False

            await client.archive_memory(memory_id="mem-lesson-e2e-001")

        assert backend.archived is True

    @pytest.mark.asyncio
    async def test_archive_calls_correct_tool(self, client, backend):
        """archive_memory() should call titans_archive."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )
            await client.archive_memory(memory_id="mem-lesson-e2e-001")

        archive_prompt = backend.prompts[1]
        assert TOOL_TITANS_ARCHIVE in archive_prompt

    @pytest.mark.asyncio
    async def test_archived_lesson_not_in_stats_count(self, client, backend):
        """After archiving, the lesson should not count in pool stats."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            await client.store_lesson(
                trigger_context="T", lesson="L", solution="S",
            )

            await client.archive_memory(memory_id="mem-lesson-e2e-001")

            stats = await client.get_stats()

        assert stats.data["pools"]["lessons"]["count"] == 0


# ============================================================
# Full E2E: All 6 steps in one test
# ============================================================


class TestFullE2ELessonLifecycle:
    """Full end-to-end test: all 6 acceptance criteria in a single workflow."""

    @pytest.mark.asyncio
    async def test_complete_lesson_lifecycle(self, client, backend):
        """Complete E2E: create -> feedback -> stats -> candidates -> demote -> archive.

        Exercises the full acceptance criteria in sequence:
          Step 1: Create lesson via titans_add (pool='lessons')
          Step 2: Record feedback via titans_record_feedback (mix success/fail)
          Step 3: Verify usefulness_score via titans_get_stats
          Step 4: Get candidates via titans_get_candidates
          Step 5: Demote lesson via titans_demote, verify status
          Step 6: Archive lesson via titans_archive, verify not in search results
        """
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            # ---- Step 1: Create lesson via titans_add (pool='lessons') ----
            create_result = await client.store_lesson(
                trigger_context="SQLite lock during concurrent writes",
                lesson="Use WAL mode for concurrent access",
                solution="Set journal_mode=WAL at connection time",
                feature_id="F091",
                error_type="OperationalError",
                fix_action="Set journal_mode=WAL",
            )
            assert create_result.success is True
            assert create_result.data["id"] == "mem-lesson-e2e-001"
            assert TOOL_TITANS_ADD in backend.prompts[0]
            assert "lessons" in backend.prompts[0]
            memory_id = create_result.data["id"]

            # ---- Step 2: Record feedback (mix success/fail) ----
            # 2 successes, 3 failures -> usefulness = 0.4
            feedback_pattern = [True, True, False, False, False]
            for success in feedback_pattern:
                fb_result = await client.record_feedback(
                    memory_id=memory_id, success=success,
                )
                assert fb_result.success is True

            assert len(backend.feedback_log) == 5
            assert backend.feedback_log == feedback_pattern

            # ---- Step 3: Verify usefulness_score via get_stats ----
            stats_result = await client.get_stats()
            assert stats_result.success is True

            lessons_stats = stats_result.data["pools"]["lessons"]
            expected_score = 2 / 5  # 0.4
            assert lessons_stats["avg_usefulness"] == pytest.approx(
                expected_score, abs=0.01,
            )
            assert stats_result.data["global_usefulness_score"] == pytest.approx(
                expected_score, abs=0.01,
            )

            # ---- Step 4: Get candidates (lesson has low score) ----
            candidates_result = await client.get_demotion_candidates(limit=10)
            assert candidates_result.success is True
            assert isinstance(candidates_result.data, list)
            assert len(candidates_result.data) == 1
            assert candidates_result.data[0]["id"] == memory_id
            assert candidates_result.data[0]["metadata"]["usefulness_score"] == pytest.approx(
                expected_score, abs=0.01,
            )

            # ---- Step 5: Demote lesson, verify status ----
            demote_result = await client.demote_memory(memory_id=memory_id)
            assert demote_result.success is True
            assert demote_result.data["metadata"]["status"] == "demoted"
            assert backend.demoted is True

            # Verify demoted lesson still appears in search but with lower weight
            search_demoted = await client.search_memory(
                query="WAL mode", pool="lessons",
            )
            assert len(search_demoted.data) == 1
            assert search_demoted.data[0]["retrieval_weight"] == 0.3  # reduced

            # ---- Step 6: Archive lesson, verify not in search results ----
            archive_result = await client.archive_memory(memory_id=memory_id)
            assert archive_result.success is True
            assert archive_result.data["metadata"]["status"] == "archived"
            assert backend.archived is True

            # Search should now return empty results
            search_archived = await client.search_memory(
                query="WAL mode", pool="lessons",
            )
            assert len(search_archived.data) == 0

            # Stats should show 0 lessons
            final_stats = await client.get_stats()
            assert final_stats.data["pools"]["lessons"]["count"] == 0

    @pytest.mark.asyncio
    async def test_lifecycle_with_positive_lesson(self, client, backend):
        """A lesson with high usefulness should NOT appear in candidates."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            # Create lesson
            await client.store_lesson(
                trigger_context="Missing import",
                lesson="Always check imports",
                solution="Add import at top of file",
            )
            memory_id = backend.memory["id"]

            # All positive feedback -> score = 1.0
            for _ in range(5):
                await client.record_feedback(memory_id=memory_id, success=True)

            # Should NOT be a demotion candidate
            candidates = await client.get_demotion_candidates(limit=10)
            assert len(candidates.data) == 0

            # Verify stats show high usefulness
            stats = await client.get_stats()
            assert stats.data["global_usefulness_score"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_lifecycle_search_then_feedback_then_archive(self, client, backend):
        """Create, search, give feedback, then archive."""
        with patch.object(client, "_execute_tool_prompt", side_effect=backend.handle):
            # Step 1: Create
            await client.store_lesson(
                trigger_context="Race condition",
                lesson="Use locks",
                solution="Add threading.Lock",
            )
            memory_id = backend.memory["id"]

            # Search to verify it's findable
            search = await client.search_memory(
                query="race condition", pool="lessons",
            )
            assert len(search.data) == 1
            assert search.data[0]["id"] == memory_id

            # Give negative feedback
            await client.record_feedback(memory_id=memory_id, success=False)

            # Verify low score
            stats = await client.get_stats()
            assert stats.data["global_usefulness_score"] == pytest.approx(0.0)

            # Archive directly (skip demotion)
            await client.archive_memory(memory_id=memory_id)

            # Verify not searchable
            post_archive = await client.search_memory(
                query="race condition", pool="lessons",
            )
            assert len(post_archive.data) == 0
