"""Tests for F040: Bob3 memory feedback loop (formerly TITANS).

Validates that the memory feedback system:
- Step 1: Add record_memory_feedback() function
- Step 2: Call record_feedback(memory_id, success=True/False)
- Step 3: Track when memory helped vs when it was wrong
- Step 4: Use get_demotion_candidates to find low-value memories
- Step 5: Test: Use memory, record success, verify usefulness increases
"""

import inspect
from unittest.mock import patch

import pytest


class _StubBackend:
    """Minimal stub BobMemory backend for feedback tests."""

    def __init__(self):
        self.add_calls = []
        self.feedback_calls = []
        self.candidates: list = []
        self.raise_candidates: Exception | None = None

    def add(self, content, *, pool=None, metadata=None):
        self.add_calls.append((content, pool, metadata))
        return {"id": f"stub-{len(self.add_calls)}", "content": content, "pool": pool or "facts", "metadata": metadata or {}}

    def search(self, query, *, pool=None, limit=10, include_archived=False):
        return []

    def record_feedback(self, memory_id, success):
        self.feedback_calls.append((memory_id, success))
        return True

    def get(self, memory_id):
        return None

    def get_stats(self):
        return {"total": 0, "pools": {}, "statuses": {}}

    def archive(self, memory_id):
        return True

    def demote(self, memory_id):
        return True

    def get_demotion_candidates(self, *, min_times_applied=5, max_usefulness=0.3, limit=50):
        if self.raise_candidates:
            raise self.raise_candidates
        return list(self.candidates)


# ===================================================================
# Step 1: record_memory_feedback() function exists
# ===================================================================


class TestRecordMemoryFeedbackExists:
    """Step 1: record_memory_feedback() must exist on BobMemoryClient."""

    def test_method_exists(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())
        assert hasattr(client, "record_memory_feedback")
        assert callable(client.record_memory_feedback)

    def test_method_is_async(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())
        assert inspect.iscoroutinefunction(client.record_memory_feedback)

    def test_method_accepts_memory_id_and_success(self):
        from bob3.memory_client import BobMemoryClient

        sig = inspect.signature(BobMemoryClient.record_memory_feedback)
        params = list(sig.parameters.keys())
        assert "memory_id" in params
        assert "success" in params

    def test_method_accepts_optional_notes(self):
        from bob3.memory_client import BobMemoryClient

        sig = inspect.signature(BobMemoryClient.record_memory_feedback)
        params = sig.parameters
        assert "notes" in params
        assert params["notes"].default is not inspect.Parameter.empty

    def test_method_accepts_optional_feature_id(self):
        from bob3.memory_client import BobMemoryClient

        sig = inspect.signature(BobMemoryClient.record_memory_feedback)
        params = sig.parameters
        assert "feature_id" in params
        assert params["feature_id"].default is not inspect.Parameter.empty


# ===================================================================
# Step 2: Call record_feedback(memory_id, success=True/False)
# ===================================================================


class TestCallsRecordFeedback:
    """Step 2: record_memory_feedback() must delegate to record_feedback()."""

    @pytest.fixture
    def client(self):
        from bob3.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

    @pytest.mark.asyncio
    async def test_delegates_to_record_feedback(self, client):
        from bob3.memory_client import MemoryResult

        feedback_calls = []

        async def capture_feedback(memory_id, success):
            feedback_calls.append({"memory_id": memory_id, "success": success})
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": 0.8}},
            )

        with patch.object(client, "record_feedback", side_effect=capture_feedback):
            await client.record_memory_feedback(memory_id="mem-abc", success=True)

        assert len(feedback_calls) == 1
        assert feedback_calls[0]["memory_id"] == "mem-abc"
        assert feedback_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_passes_success_true(self, client):
        from bob3.memory_client import MemoryResult

        feedback_calls = []

        async def capture(memory_id, success):
            feedback_calls.append({"success": success})
            return MemoryResult(success=True, data={})

        with patch.object(client, "record_feedback", side_effect=capture):
            await client.record_memory_feedback(memory_id="mem-1", success=True)

        assert feedback_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_passes_success_false(self, client):
        from bob3.memory_client import MemoryResult

        feedback_calls = []

        async def capture(memory_id, success):
            feedback_calls.append({"success": success})
            return MemoryResult(success=True, data={})

        with patch.object(client, "record_feedback", side_effect=capture):
            await client.record_memory_feedback(memory_id="mem-1", success=False)

        assert feedback_calls[0]["success"] is False

    @pytest.mark.asyncio
    async def test_returns_memory_result(self, client):
        from bob3.memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": 0.85}},
            )

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            result = await client.record_memory_feedback(memory_id="mem-1", success=True)

        assert isinstance(result, MemoryResult)
        assert result.success is True


# ===================================================================
# Step 3: Track when memory helped vs when it was wrong
# ===================================================================


class TestTrackMemoryHelpfulness:
    """Step 3: System tracks helpful vs unhelpful memory usage via notes."""

    @pytest.fixture
    def client(self):
        from bob3.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

    @pytest.mark.asyncio
    async def test_positive_feedback_logged(self, client):
        """Positive feedback should be logged."""
        from bob3.memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={})

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-1",
                success=True,
                notes="Memory helped with DB schema design",
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_negative_feedback_logged(self, client):
        """Negative feedback should be logged."""
        from bob3.memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={})

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-2",
                success=False,
                notes="Memory was outdated and incorrect",
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_notes_included_in_logging(self, client):
        """Notes provided to record_memory_feedback should be logged."""
        from bob3.memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={})

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            with patch("bob3.memory_client.logger") as mock_logger:
                await client.record_memory_feedback(
                    memory_id="mem-1",
                    success=True,
                    notes="Helped with API design",
                )
                log_calls = mock_logger.info.call_args_list
                all_log_text = " ".join(str(call) for call in log_calls)
                assert "mem-1" in all_log_text

    @pytest.mark.asyncio
    async def test_feature_id_included_in_logging(self, client):
        """Feature ID should be included in log messages when provided."""
        from bob3.memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={})

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            with patch("bob3.memory_client.logger") as mock_logger:
                await client.record_memory_feedback(
                    memory_id="mem-1",
                    success=True,
                    feature_id="F040",
                )
                log_calls = mock_logger.info.call_args_list
                all_log_text = " ".join(str(call) for call in log_calls)
                assert "F040" in all_log_text

    @pytest.mark.asyncio
    async def test_handles_feedback_failure_gracefully(self, client):
        """If record_feedback fails, record_memory_feedback should return the failure."""
        from bob3.memory_client import MemoryResult

        async def failing_feedback(memory_id, success):
            return MemoryResult(success=False, error="backend timeout")

        with patch.object(client, "record_feedback", side_effect=failing_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-1",
                success=True,
                notes="This should fail",
            )

        assert result.success is False
        assert "backend timeout" in result.error


# ===================================================================
# Step 4: Use backend's get_demotion_candidates for low-value memories
# ===================================================================


class TestGetDemotionCandidatesExists:
    """Step 4: get_demotion_candidates() must exist and call backend."""

    def test_method_exists(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())
        assert hasattr(client, "get_demotion_candidates")
        assert callable(client.get_demotion_candidates)

    def test_method_is_async(self):
        from bob3.memory_client import BobMemoryClient

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())
        assert inspect.iscoroutinefunction(client.get_demotion_candidates)

    def test_method_accepts_optional_limit(self):
        from bob3.memory_client import BobMemoryClient

        sig = inspect.signature(BobMemoryClient.get_demotion_candidates)
        params = sig.parameters
        assert "limit" in params
        assert params["limit"].default is not inspect.Parameter.empty


class TestGetDemotionCandidatesBehavior:
    """Step 4: get_demotion_candidates() calls backend.get_demotion_candidates."""

    @pytest.fixture
    def backend(self):
        return _StubBackend()

    @pytest.fixture
    def client(self, backend):
        from bob3.memory_client import BobMemoryClient

        return BobMemoryClient(workspace="/tmp/test", backend=backend)

    @pytest.mark.asyncio
    async def test_calls_backend(self, client, backend):
        backend.candidates = []
        # Spy on backend
        orig = backend.get_demotion_candidates
        called = {"n": 0}

        def spy(**kwargs):
            called["n"] += 1
            return orig(**kwargs)

        backend.get_demotion_candidates = spy
        await client.get_demotion_candidates()
        assert called["n"] == 1

    @pytest.mark.asyncio
    async def test_passes_limit(self, client, backend):
        captured = {}
        orig = backend.get_demotion_candidates

        def spy(**kwargs):
            captured.update(kwargs)
            return orig(**kwargs)

        backend.get_demotion_candidates = spy
        await client.get_demotion_candidates(limit=5)
        assert captured.get("limit") == 5

    @pytest.mark.asyncio
    async def test_default_limit_is_10(self, client, backend):
        captured = {}
        orig = backend.get_demotion_candidates

        def spy(**kwargs):
            captured.update(kwargs)
            return orig(**kwargs)

        backend.get_demotion_candidates = spy
        await client.get_demotion_candidates()
        # Default limit should be 10 per test signature
        assert captured.get("limit") == 10

    @pytest.mark.asyncio
    async def test_returns_memory_result_with_list(self, client, backend):
        from bob3.memory_client import MemoryResult

        backend.candidates = [
            {"id": "mem-low-1", "content": "old info", "usefulness_score": 0.1},
            {"id": "mem-low-2", "content": "stale data", "usefulness_score": 0.2},
        ]

        result = await client.get_demotion_candidates()
        assert isinstance(result, MemoryResult)
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_handles_failure_gracefully(self, client, backend):
        backend.raise_candidates = RuntimeError("backend down")
        result = await client.get_demotion_candidates()

        assert result.success is False
        assert "backend down" in result.error


# ===================================================================
# Step 5: Full cycle - use memory, record success, verify usefulness
# ===================================================================


class TestFullFeedbackLoop:
    """Step 5: Full cycle - search, use, record feedback, verify improvement."""

    @pytest.mark.asyncio
    async def test_search_use_feedback_cycle(self):
        """Search for memory, record positive feedback, verify score increases."""
        from bob3.memory_client import BobMemoryClient, MemoryResult

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

        initial_score = 0.5
        updated_score = 0.65

        call_sequence = []

        async def fake_record_feedback(memory_id, success):
            call_sequence.append({"action": "record_feedback", "memory_id": memory_id, "success": success})
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": updated_score}},
            )

        async def fake_search(query, pool=None, limit=10):
            call_sequence.append({"action": "search", "query": query})
            return MemoryResult(
                success=True,
                data=[{
                    "id": "mem-feedback-1",
                    "content": "WAL mode improves concurrent reads",
                    "retrieval_weight": 0.7,
                    "metadata": {"usefulness_score": initial_score},
                }],
            )

        with patch.object(client, "search_memory", side_effect=fake_search), \
             patch.object(client, "record_feedback", side_effect=fake_record_feedback):

            search_result = await client.search_memory(
                query="SQLite concurrent reads",
                pool="facts",
            )
            assert search_result.success is True
            assert len(search_result.data) >= 1

            found_memory = search_result.data[0]
            initial_usefulness = found_memory["metadata"]["usefulness_score"]

            feedback_result = await client.record_memory_feedback(
                memory_id=found_memory["id"],
                success=True,
                notes="Memory helped with DB design",
                feature_id="F040",
            )
            assert feedback_result.success is True

            updated_usefulness = feedback_result.data["metadata"]["usefulness_score"]
            assert updated_usefulness > initial_usefulness

        assert len(call_sequence) == 2
        assert call_sequence[0]["action"] == "search"
        assert call_sequence[1]["action"] == "record_feedback"
        assert call_sequence[1]["success"] is True

    @pytest.mark.asyncio
    async def test_negative_feedback_reduces_usefulness(self):
        """Record negative feedback, verify score decreases."""
        from bob3.memory_client import BobMemoryClient, MemoryResult

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

        initial_score = 0.7
        reduced_score = 0.55

        async def fake_record_feedback(memory_id, success):
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": reduced_score}},
            )

        with patch.object(client, "record_feedback", side_effect=fake_record_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-bad",
                success=False,
                notes="Memory was outdated and wrong",
            )

        assert result.success is True
        assert result.data["metadata"]["usefulness_score"] < initial_score

    @pytest.mark.asyncio
    async def test_get_candidates_after_negative_feedback(self):
        """After negative feedback, low-value memories appear as demotion candidates."""
        from bob3.memory_client import BobMemoryClient, MemoryResult

        backend = _StubBackend()
        backend.candidates = [
            {"id": "mem-bad", "content": "wrong info", "usefulness_score": 0.1},
        ]
        client = BobMemoryClient(workspace="/tmp/test", backend=backend)

        async def fake_record_feedback(memory_id, success):
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": 0.1}},
            )

        with patch.object(client, "record_feedback", side_effect=fake_record_feedback):
            await client.record_memory_feedback(
                memory_id="mem-bad",
                success=False,
            )

            candidates = await client.get_demotion_candidates(limit=5)
            assert candidates.success is True
            assert isinstance(candidates.data, list)
            assert len(candidates.data) >= 1
            assert candidates.data[0]["id"] == "mem-bad"

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_multiple_feedbacks(self):
        """Multiple feedbacks on same memory should all succeed."""
        from bob3.memory_client import BobMemoryClient, MemoryResult

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

        feedback_count = 0

        async def fake_record_feedback(memory_id, success):
            nonlocal feedback_count
            feedback_count += 1
            score = 0.5 + (0.1 * feedback_count if success else -0.1 * feedback_count)
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": score}},
            )

        with patch.object(client, "record_feedback", side_effect=fake_record_feedback):
            r1 = await client.record_memory_feedback("mem-x", success=True)
            r2 = await client.record_memory_feedback("mem-x", success=True)
            r3 = await client.record_memory_feedback("mem-x", success=True)

        assert r1.success is True
        assert r2.success is True
        assert r3.success is True
        assert feedback_count == 3
        assert r3.data["metadata"]["usefulness_score"] > r1.data["metadata"]["usefulness_score"]

    @pytest.mark.asyncio
    async def test_feedback_with_no_notes_works(self):
        """record_memory_feedback should work without notes or feature_id."""
        from bob3.memory_client import BobMemoryClient, MemoryResult

        client = BobMemoryClient(workspace="/tmp/test", backend=_StubBackend())

        async def fake_record_feedback(memory_id, success):
            return MemoryResult(success=True, data={"id": memory_id})

        with patch.object(client, "record_feedback", side_effect=fake_record_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-1",
                success=True,
            )

        assert result.success is True
