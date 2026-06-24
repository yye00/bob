"""Tests for F091: End-to-end test - Bob Memory lesson lifecycle.

Exercises the complete lesson lifecycle via the BobMemoryClient:

Step 1: Create lesson via add() (pool='lessons')
Step 2: Record feedback via record_feedback (mix success/fail)
Step 3: Verify usefulness_score via get_stats
Step 4: Get candidates via get_demotion_candidates
Step 5: Demote lesson via demote, verify status
Step 6: Archive lesson via archive, verify not in search results

Previously this exercised the TITANS Memory MCP client (which spawned a
sub-agent to call MCP tools). It now exercises the in-process
BobMemoryClient backed by a simulated BobMemory.
"""

import pytest

from bob.memory_client import BobMemoryClient, MemoryResult


# ============================================================
# Simulated BobMemory backend for the lesson lifecycle
# ============================================================


class SimulatedBackend:
    """In-memory simulation of BobMemory with feedback tracking."""

    def __init__(self):
        self.memory: dict | None = None
        self.feedback_log: list[bool] = []
        self.archived = False
        self.demoted = False
        self.add_calls = 0

    @property
    def usefulness_score(self) -> float:
        if not self.feedback_log:
            return 0.5
        return sum(1 for f in self.feedback_log if f) / len(self.feedback_log)

    def _current_metadata(self) -> dict:
        status = "active"
        if self.archived:
            status = "archived"
        elif self.demoted:
            status = "demoted"
        return {
            "pool": "lessons",
            "feature_id": "F091",
            "error_type": "OperationalError",
            "usefulness_score": self.usefulness_score,
            "status": status,
        }

    def add(self, content, *, pool=None, metadata=None):
        self.add_calls += 1
        meta = self._current_metadata()
        if metadata:
            meta.update(metadata)
            meta["pool"] = "lessons"
        self.memory = {
            "id": "mem-lesson-e2e-001",
            "content": content,
            "pool": "lessons",
            "metadata": meta,
        }
        return dict(self.memory)

    def search(self, query, *, pool=None, limit=10, include_archived=False):
        if self.archived and not include_archived:
            return []
        if not self.memory:
            return []
        weight = 0.3 if self.demoted else 0.8
        result = dict(self.memory)
        result["metadata"] = self._current_metadata()
        result["retrieval_weight"] = weight
        result["score"] = weight
        return [result]

    def record_feedback(self, memory_id, success):
        if self.memory is None or memory_id != self.memory["id"]:
            return False
        self.feedback_log.append(bool(success))
        return True

    def get(self, memory_id):
        if self.memory and memory_id == self.memory["id"]:
            data = dict(self.memory)
            data["metadata"] = self._current_metadata()
            return data
        return None

    def get_stats(self):
        lessons_count = 1 if self.memory and not self.archived else 0
        return {
            "total": lessons_count,
            "pools": {
                "lessons": {
                    "count": lessons_count,
                    "avg_usefulness": self.usefulness_score,
                },
            },
            "statuses": {},
            "global_usefulness_score": self.usefulness_score,
        }

    def archive(self, memory_id):
        if self.memory and memory_id == self.memory["id"]:
            self.archived = True
            return True
        return False

    def demote(self, memory_id):
        if self.memory and memory_id == self.memory["id"]:
            self.demoted = True
            return True
        return False

    def get_demotion_candidates(self, *, min_times_applied=5, max_usefulness=0.3, limit=50):
        if self.memory and not self.archived and self.usefulness_score < 0.6:
            data = dict(self.memory)
            data["metadata"] = self._current_metadata()
            return [data]
        return []


@pytest.fixture
def backend():
    return SimulatedBackend()


@pytest.fixture
def client(backend):
    return BobMemoryClient(workspace="/tmp/e2e-lesson-lifecycle", backend=backend)


# ============================================================
# Step 1: Create lesson via add() (pool='lessons')
# ============================================================


class TestStep1CreateLesson:
    """Step 1: Create lesson via the memory backend (pool='lessons')."""

    @pytest.mark.asyncio
    async def test_store_lesson_calls_backend_add(self, client, backend):
        """store_lesson() should call backend.add() and return a memory with an ID."""
        result = await client.store_lesson(
            trigger_context="SQLite lock during concurrent writes",
            lesson="Use WAL mode for concurrent access",
            solution="Set journal_mode=WAL at connection time",
            feature_id="F091",
            error_type="OperationalError",
        )

        assert result.success is True
        assert result.data["id"] == "mem-lesson-e2e-001"
        assert backend.add_calls == 1

    @pytest.mark.asyncio
    async def test_lesson_routed_to_lessons_pool(self, client, backend):
        """The lesson must be stored in the 'lessons' pool."""
        result = await client.store_lesson(
            trigger_context="T",
            lesson="L",
            solution="S",
        )

        assert result.success is True
        assert backend.memory["pool"] == "lessons"

    @pytest.mark.asyncio
    async def test_lesson_content_is_structured(self, client, backend):
        """Content should contain TRIGGER, LESSON, SOLUTION."""
        await client.store_lesson(
            trigger_context="Lock error",
            lesson="Enable WAL",
            solution="Pragma WAL",
        )

        content = backend.memory["content"]
        assert "TRIGGER:" in content
        assert "LESSON:" in content
        assert "SOLUTION:" in content

    @pytest.mark.asyncio
    async def test_memory_object_created_in_backend(self, client, backend):
        """After storing, the backend should have a memory object."""
        assert backend.memory is None
        await client.store_lesson(
            trigger_context="T",
            lesson="L",
            solution="S",
        )
        assert backend.memory is not None
        assert backend.memory["id"] == "mem-lesson-e2e-001"


# ============================================================
# Step 2: Record feedback (mix success/fail)
# ============================================================


class TestStep2RecordFeedbackMixSuccessFail:
    """Step 2: Record feedback (mix success/fail)."""

    @pytest.mark.asyncio
    async def test_record_mixed_feedback(self, client, backend):
        """Record a mix of success and failure feedback on the lesson."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        memory_id = backend.memory["id"]

        feedback_results = []
        for success in [True, True, False, True, False]:
            result = await client.record_feedback(memory_id=memory_id, success=success)
            feedback_results.append(result)

        assert all(r.success for r in feedback_results)
        assert backend.feedback_log == [True, True, False, True, False]

    @pytest.mark.asyncio
    async def test_feedback_result_includes_updated_score(self, client, backend):
        """After feedback, the returned data should reflect the update."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        memory_id = backend.memory["id"]

        # Record only successes -> score should be 1.0
        result = await client.record_feedback(memory_id=memory_id, success=True)
        assert result.success is True
        # The underlying backend score is now 1.0
        assert backend.usefulness_score == pytest.approx(1.0)


# ============================================================
# Step 3: Verify usefulness_score via get_stats
# ============================================================


class TestStep3VerifyUsefulnessScoreViaGetStats:
    """Step 3: Verify usefulness_score via get_stats."""

    @pytest.mark.asyncio
    async def test_get_stats_returns_usefulness_score(self, client, backend):
        """After mixed feedback, get_stats should reflect the calculated score."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
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
    async def test_global_usefulness_score_after_all_success(self, client, backend):
        """All positive feedback should yield usefulness_score of 1.0."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        memory_id = backend.memory["id"]

        for _ in range(5):
            await client.record_feedback(memory_id=memory_id, success=True)

        stats = await client.get_stats()
        assert stats.data["global_usefulness_score"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_global_usefulness_score_after_all_failure(self, client, backend):
        """All negative feedback should yield usefulness_score of 0.0."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        memory_id = backend.memory["id"]

        for _ in range(5):
            await client.record_feedback(memory_id=memory_id, success=False)

        stats = await client.get_stats()
        assert stats.data["global_usefulness_score"] == pytest.approx(0.0)


# ============================================================
# Step 4: Get candidates via get_demotion_candidates
# ============================================================


class TestStep4GetCandidates:
    """Step 4: Get candidates via get_demotion_candidates."""

    @pytest.mark.asyncio
    async def test_low_usefulness_appears_as_candidate(self, client, backend):
        """A lesson with low usefulness should appear in demotion candidates."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        memory_id = backend.memory["id"]

        for success in [True, False, False, False, False]:
            await client.record_feedback(memory_id=memory_id, success=success)

        candidates_result = await client.get_demotion_candidates(limit=10)

        assert candidates_result.success is True
        assert len(candidates_result.data) == 1
        assert candidates_result.data[0]["id"] == "mem-lesson-e2e-001"

    @pytest.mark.asyncio
    async def test_high_usefulness_not_a_candidate(self, client, backend):
        """A lesson with high usefulness should NOT appear in demotion candidates."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        memory_id = backend.memory["id"]

        for _ in range(5):
            await client.record_feedback(memory_id=memory_id, success=True)

        candidates_result = await client.get_demotion_candidates(limit=10)

        assert candidates_result.success is True
        assert len(candidates_result.data) == 0

    @pytest.mark.asyncio
    async def test_candidate_usefulness_score_is_low(self, client, backend):
        """Returned candidate should have a low usefulness score."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        memory_id = backend.memory["id"]

        for success in [True, False, False, False, False]:
            await client.record_feedback(memory_id=memory_id, success=success)

        candidates_result = await client.get_demotion_candidates()
        candidate = candidates_result.data[0]
        assert candidate["metadata"]["usefulness_score"] == pytest.approx(0.2)


# ============================================================
# Step 5: Demote lesson, verify status
# ============================================================


class TestStep5DemoteLesson:
    """Step 5: Demote lesson, verify status."""

    @pytest.mark.asyncio
    async def test_demote_sets_backend_flag(self, client, backend):
        """After demoting, the backend should track the demoted state."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        assert backend.demoted is False

        await client.demote_memory(memory_id="mem-lesson-e2e-001")
        assert backend.demoted is True

    @pytest.mark.asyncio
    async def test_demote_returns_success(self, client, backend):
        """demote_memory() should return success."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        result = await client.demote_memory(memory_id="mem-lesson-e2e-001")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_demoted_lesson_has_lower_retrieval_weight(self, client, backend):
        """A demoted lesson should have a lower retrieval weight in search results."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")

        search_before = await client.search_memory(query="WAL mode", pool="lessons")
        weight_before = search_before.data[0]["retrieval_weight"]

        await client.demote_memory(memory_id="mem-lesson-e2e-001")

        search_after = await client.search_memory(query="WAL mode", pool="lessons")
        weight_after = search_after.data[0]["retrieval_weight"]

        assert weight_after < weight_before


# ============================================================
# Step 6: Archive lesson, verify not in search results
# ============================================================


class TestStep6ArchiveLesson:
    """Step 6: Archive lesson, verify not in search results."""

    @pytest.mark.asyncio
    async def test_archive_returns_success(self, client, backend):
        """Archiving a lesson should succeed."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        result = await client.archive_memory(memory_id="mem-lesson-e2e-001")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_archived_lesson_not_in_search_results(self, client, backend):
        """After archiving, the lesson should NOT appear in search results."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")

        search_before = await client.search_memory(query="WAL mode", pool="lessons")
        assert len(search_before.data) == 1

        await client.archive_memory(memory_id="mem-lesson-e2e-001")

        search_after = await client.search_memory(query="WAL mode", pool="lessons")
        assert len(search_after.data) == 0

    @pytest.mark.asyncio
    async def test_archive_sets_backend_flag(self, client, backend):
        """After archiving, the backend should track the archived state."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
        assert backend.archived is False

        await client.archive_memory(memory_id="mem-lesson-e2e-001")
        assert backend.archived is True

    @pytest.mark.asyncio
    async def test_archived_lesson_not_in_stats_count(self, client, backend):
        """After archiving, the lesson should not count in pool stats."""
        await client.store_lesson(trigger_context="T", lesson="L", solution="S")
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
        """Complete E2E: create -> feedback -> stats -> candidates -> demote -> archive."""
        # ---- Step 1: Create lesson (pool='lessons') ----
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
        assert backend.memory["pool"] == "lessons"
        memory_id = create_result.data["id"]

        # ---- Step 2: Record feedback (mix success/fail) ----
        feedback_pattern = [True, True, False, False, False]
        for success in feedback_pattern:
            fb_result = await client.record_feedback(memory_id=memory_id, success=success)
            assert fb_result.success is True
        assert backend.feedback_log == feedback_pattern

        # ---- Step 3: Verify usefulness_score via get_stats ----
        stats_result = await client.get_stats()
        assert stats_result.success is True
        lessons_stats = stats_result.data["pools"]["lessons"]
        expected_score = 2 / 5
        assert lessons_stats["avg_usefulness"] == pytest.approx(expected_score, abs=0.01)
        assert stats_result.data["global_usefulness_score"] == pytest.approx(
            expected_score, abs=0.01
        )

        # ---- Step 4: Get candidates (lesson has low score) ----
        candidates_result = await client.get_demotion_candidates(limit=10)
        assert candidates_result.success is True
        assert len(candidates_result.data) == 1
        assert candidates_result.data[0]["id"] == memory_id

        # ---- Step 5: Demote lesson ----
        demote_result = await client.demote_memory(memory_id=memory_id)
        assert demote_result.success is True
        assert backend.demoted is True

        search_demoted = await client.search_memory(query="WAL mode", pool="lessons")
        assert len(search_demoted.data) == 1
        assert search_demoted.data[0]["retrieval_weight"] == pytest.approx(0.3)

        # ---- Step 6: Archive lesson ----
        archive_result = await client.archive_memory(memory_id=memory_id)
        assert archive_result.success is True
        assert backend.archived is True

        search_archived = await client.search_memory(query="WAL mode", pool="lessons")
        assert len(search_archived.data) == 0

        final_stats = await client.get_stats()
        assert final_stats.data["pools"]["lessons"]["count"] == 0

    @pytest.mark.asyncio
    async def test_lifecycle_with_positive_lesson(self, client, backend):
        """A lesson with high usefulness should NOT appear in candidates."""
        await client.store_lesson(
            trigger_context="Missing import",
            lesson="Always check imports",
            solution="Add import at top of file",
        )
        memory_id = backend.memory["id"]

        for _ in range(5):
            await client.record_feedback(memory_id=memory_id, success=True)

        candidates = await client.get_demotion_candidates(limit=10)
        assert len(candidates.data) == 0

        stats = await client.get_stats()
        assert stats.data["global_usefulness_score"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_lifecycle_search_then_feedback_then_archive(self, client, backend):
        """Create, search, give feedback, then archive."""
        await client.store_lesson(
            trigger_context="Race condition",
            lesson="Use locks",
            solution="Add threading.Lock",
        )
        memory_id = backend.memory["id"]

        search = await client.search_memory(query="race condition", pool="lessons")
        assert len(search.data) == 1
        assert search.data[0]["id"] == memory_id

        await client.record_feedback(memory_id=memory_id, success=False)

        stats = await client.get_stats()
        assert stats.data["global_usefulness_score"] == pytest.approx(0.0)

        await client.archive_memory(memory_id=memory_id)

        post_archive = await client.search_memory(query="race condition", pool="lessons")
        assert len(post_archive.data) == 0
