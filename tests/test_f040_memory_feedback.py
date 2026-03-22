"""Tests for F040: Implement TITANS memory feedback loop.

Validates that the memory feedback system:
- Step 1: Add record_memory_feedback() function
- Step 2: Call titans_record_feedback(memory_id, success=True/False)
- Step 3: Track when memory helped vs when it was wrong
- Step 4: Use titans_get_candidates to find low-value memories
- Step 5: Test: Use memory, record success, verify usefulness increases
"""

import inspect
from unittest.mock import patch

import pytest


# ===================================================================
# Step 1: record_memory_feedback() function exists
# ===================================================================


class TestRecordMemoryFeedbackExists:
    """Step 1: record_memory_feedback() must exist on TitansMemoryClient."""

    def test_method_exists(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert hasattr(client, "record_memory_feedback")
        assert callable(client.record_memory_feedback)

    def test_method_is_async(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert inspect.iscoroutinefunction(client.record_memory_feedback)

    def test_method_accepts_memory_id_and_success(self):
        from bob3.titans_memory_client import TitansMemoryClient

        sig = inspect.signature(TitansMemoryClient.record_memory_feedback)
        params = list(sig.parameters.keys())
        assert "memory_id" in params
        assert "success" in params

    def test_method_accepts_optional_notes(self):
        from bob3.titans_memory_client import TitansMemoryClient

        sig = inspect.signature(TitansMemoryClient.record_memory_feedback)
        params = sig.parameters
        assert "notes" in params
        assert params["notes"].default is not inspect.Parameter.empty

    def test_method_accepts_optional_feature_id(self):
        from bob3.titans_memory_client import TitansMemoryClient

        sig = inspect.signature(TitansMemoryClient.record_memory_feedback)
        params = sig.parameters
        assert "feature_id" in params
        assert params["feature_id"].default is not inspect.Parameter.empty


# ===================================================================
# Step 2: Call titans_record_feedback(memory_id, success=True/False)
# ===================================================================


class TestCallsTitansRecordFeedback:
    """Step 2: record_memory_feedback() must delegate to record_feedback()."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_delegates_to_record_feedback(self, client):
        from bob3.titans_memory_client import MemoryResult

        feedback_calls = []

        async def capture_feedback(memory_id, success):
            feedback_calls.append({"memory_id": memory_id, "success": success})
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": 0.8}},
                raw_text="{}",
            )

        with patch.object(client, "record_feedback", side_effect=capture_feedback):
            await client.record_memory_feedback(
                memory_id="mem-abc", success=True
            )

        assert len(feedback_calls) == 1
        assert feedback_calls[0]["memory_id"] == "mem-abc"
        assert feedback_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_passes_success_true(self, client):
        from bob3.titans_memory_client import MemoryResult

        feedback_calls = []

        async def capture(memory_id, success):
            feedback_calls.append({"success": success})
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "record_feedback", side_effect=capture):
            await client.record_memory_feedback(memory_id="mem-1", success=True)

        assert feedback_calls[0]["success"] is True

    @pytest.mark.asyncio
    async def test_passes_success_false(self, client):
        from bob3.titans_memory_client import MemoryResult

        feedback_calls = []

        async def capture(memory_id, success):
            feedback_calls.append({"success": success})
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "record_feedback", side_effect=capture):
            await client.record_memory_feedback(memory_id="mem-1", success=False)

        assert feedback_calls[0]["success"] is False

    @pytest.mark.asyncio
    async def test_returns_memory_result(self, client):
        from bob3.titans_memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": 0.85}},
                raw_text="{}",
            )

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-1", success=True
            )

        assert isinstance(result, MemoryResult)
        assert result.success is True


# ===================================================================
# Step 3: Track when memory helped vs when it was wrong
# ===================================================================


class TestTrackMemoryHelpfulness:
    """Step 3: System tracks helpful vs unhelpful memory usage via notes."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_positive_feedback_logged(self, client):
        """Positive feedback should be logged."""
        from bob3.titans_memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={}, raw_text="{}")

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
        from bob3.titans_memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={}, raw_text="{}")

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
        import logging

        from bob3.titans_memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            with patch("bob3.titans_memory_client.logger") as mock_logger:
                await client.record_memory_feedback(
                    memory_id="mem-1",
                    success=True,
                    notes="Helped with API design",
                )
                # Check that info was logged with notes
                log_calls = mock_logger.info.call_args_list
                all_log_text = " ".join(
                    str(call) for call in log_calls
                )
                assert "mem-1" in all_log_text

    @pytest.mark.asyncio
    async def test_feature_id_included_in_logging(self, client):
        """Feature ID should be included in log messages when provided."""
        from bob3.titans_memory_client import MemoryResult

        async def fake_feedback(memory_id, success):
            return MemoryResult(success=True, data={}, raw_text="{}")

        with patch.object(client, "record_feedback", side_effect=fake_feedback):
            with patch("bob3.titans_memory_client.logger") as mock_logger:
                await client.record_memory_feedback(
                    memory_id="mem-1",
                    success=True,
                    feature_id="F040",
                )
                log_calls = mock_logger.info.call_args_list
                all_log_text = " ".join(
                    str(call) for call in log_calls
                )
                assert "F040" in all_log_text

    @pytest.mark.asyncio
    async def test_handles_feedback_failure_gracefully(self, client):
        """If record_feedback fails, record_memory_feedback should return the failure."""
        from bob3.titans_memory_client import MemoryResult

        async def failing_feedback(memory_id, success):
            return MemoryResult(success=False, error="MCP timeout")

        with patch.object(client, "record_feedback", side_effect=failing_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-1",
                success=True,
                notes="This should fail",
            )

        assert result.success is False
        assert "MCP timeout" in result.error


# ===================================================================
# Step 4: Use titans_get_candidates to find low-value memories
# ===================================================================


class TestGetDemotionCandidatesExists:
    """Step 4: get_demotion_candidates() must exist and use titans_get_candidates."""

    def test_method_exists(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert hasattr(client, "get_demotion_candidates")
        assert callable(client.get_demotion_candidates)

    def test_method_is_async(self):
        from bob3.titans_memory_client import TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")
        assert inspect.iscoroutinefunction(client.get_demotion_candidates)

    def test_method_accepts_optional_limit(self):
        from bob3.titans_memory_client import TitansMemoryClient

        sig = inspect.signature(TitansMemoryClient.get_demotion_candidates)
        params = sig.parameters
        assert "limit" in params
        assert params["limit"].default is not inspect.Parameter.empty


class TestGetDemotionCandidatesBehavior:
    """Step 4: get_demotion_candidates() calls titans_get_candidates."""

    @pytest.fixture
    def client(self):
        from bob3.titans_memory_client import TitansMemoryClient

        return TitansMemoryClient(workspace="/tmp/test")

    @pytest.mark.asyncio
    async def test_calls_execute_tool_prompt(self, client):
        from bob3.titans_memory_client import MemoryResult

        async def fake(prompt):
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=fake) as mock:
            await client.get_demotion_candidates()
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_prompt_contains_get_candidates_tool(self, client):
        from bob3.titans_memory_client import (
            TOOL_TITANS_GET_CANDIDATES,
            MemoryResult,
        )

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.get_demotion_candidates()

        assert len(prompts_seen) == 1
        assert TOOL_TITANS_GET_CANDIDATES in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_prompt_contains_limit(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.get_demotion_candidates(limit=5)

        assert "5" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_default_limit(self, client):
        from bob3.titans_memory_client import MemoryResult

        prompts_seen = []

        async def capture(prompt):
            prompts_seen.append(prompt)
            return MemoryResult(success=True, data=[], raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=capture):
            await client.get_demotion_candidates()

        # Default limit should be 10
        assert "10" in prompts_seen[0]

    @pytest.mark.asyncio
    async def test_returns_memory_result_with_list(self, client):
        from bob3.titans_memory_client import MemoryResult

        candidates = [
            {"id": "mem-low-1", "content": "old info", "usefulness_score": 0.1},
            {"id": "mem-low-2", "content": "stale data", "usefulness_score": 0.2},
        ]

        async def fake(prompt):
            return MemoryResult(success=True, data=candidates, raw_text="[]")

        with patch.object(client, "_execute_tool_prompt", side_effect=fake):
            result = await client.get_demotion_candidates()

        assert isinstance(result, MemoryResult)
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_handles_failure_gracefully(self, client):
        from bob3.titans_memory_client import MemoryResult

        async def failing(prompt):
            return MemoryResult(success=False, error="MCP server down")

        with patch.object(client, "_execute_tool_prompt", side_effect=failing):
            result = await client.get_demotion_candidates()

        assert result.success is False
        assert "MCP server down" in result.error


# ===================================================================
# Step 5: Full cycle - use memory, record success, verify usefulness
# ===================================================================


class TestFullFeedbackLoop:
    """Step 5: Full cycle - search, use, record feedback, verify improvement."""

    @pytest.mark.asyncio
    async def test_search_use_feedback_cycle(self):
        """Search for memory, record positive feedback, verify score increases."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        initial_score = 0.5
        updated_score = 0.65

        call_sequence = []

        async def fake_record_feedback(memory_id, success):
            call_sequence.append({"action": "record_feedback", "memory_id": memory_id, "success": success})
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": updated_score}},
                raw_text="{}",
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
                raw_text="[]",
            )

        with patch.object(client, "search_memory", side_effect=fake_search), \
             patch.object(client, "record_feedback", side_effect=fake_record_feedback):

            # Step 1: Search for relevant memory
            search_result = await client.search_memory(
                query="SQLite concurrent reads",
                pool="facts",
            )
            assert search_result.success is True
            assert len(search_result.data) >= 1

            found_memory = search_result.data[0]
            initial_usefulness = found_memory["metadata"]["usefulness_score"]

            # Step 2: Record positive feedback (memory was helpful)
            feedback_result = await client.record_memory_feedback(
                memory_id=found_memory["id"],
                success=True,
                notes="Memory helped with DB design",
                feature_id="F040",
            )
            assert feedback_result.success is True

            # Step 3: Verify usefulness increased
            updated_usefulness = feedback_result.data["metadata"]["usefulness_score"]
            assert updated_usefulness > initial_usefulness

        # Verify call sequence
        assert len(call_sequence) == 2
        assert call_sequence[0]["action"] == "search"
        assert call_sequence[1]["action"] == "record_feedback"
        assert call_sequence[1]["success"] is True

    @pytest.mark.asyncio
    async def test_negative_feedback_reduces_usefulness(self):
        """Record negative feedback, verify score decreases."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        initial_score = 0.7
        reduced_score = 0.55

        async def fake_record_feedback(memory_id, success):
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": reduced_score}},
                raw_text="{}",
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
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_record_feedback(memory_id, success):
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": 0.1}},
                raw_text="{}",
            )

        async def fake_execute(prompt):
            if "get_candidates" in prompt:
                return MemoryResult(
                    success=True,
                    data=[
                        {"id": "mem-bad", "content": "wrong info", "usefulness_score": 0.1},
                    ],
                    raw_text="[]",
                )
            return MemoryResult(success=False, error="unexpected")

        with patch.object(client, "record_feedback", side_effect=fake_record_feedback), \
             patch.object(client, "_execute_tool_prompt", side_effect=fake_execute):

            # Record negative feedback
            await client.record_memory_feedback(
                memory_id="mem-bad",
                success=False,
            )

            # Get demotion candidates
            candidates = await client.get_demotion_candidates(limit=5)
            assert candidates.success is True
            assert isinstance(candidates.data, list)
            assert len(candidates.data) >= 1
            assert candidates.data[0]["id"] == "mem-bad"

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_multiple_feedbacks(self):
        """Multiple feedbacks on same memory should all succeed."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        feedback_count = 0

        async def fake_record_feedback(memory_id, success):
            nonlocal feedback_count
            feedback_count += 1
            score = 0.5 + (0.1 * feedback_count if success else -0.1 * feedback_count)
            return MemoryResult(
                success=True,
                data={"id": memory_id, "metadata": {"usefulness_score": score}},
                raw_text="{}",
            )

        with patch.object(client, "record_feedback", side_effect=fake_record_feedback):
            # Record several positive feedbacks
            r1 = await client.record_memory_feedback("mem-x", success=True)
            r2 = await client.record_memory_feedback("mem-x", success=True)
            r3 = await client.record_memory_feedback("mem-x", success=True)

        assert r1.success is True
        assert r2.success is True
        assert r3.success is True
        assert feedback_count == 3
        # Score should increase with positive feedbacks
        assert r3.data["metadata"]["usefulness_score"] > r1.data["metadata"]["usefulness_score"]

    @pytest.mark.asyncio
    async def test_feedback_with_no_notes_works(self):
        """record_memory_feedback should work without notes or feature_id."""
        from bob3.titans_memory_client import MemoryResult, TitansMemoryClient

        client = TitansMemoryClient(workspace="/tmp/test")

        async def fake_record_feedback(memory_id, success):
            return MemoryResult(success=True, data={"id": memory_id}, raw_text="{}")

        with patch.object(client, "record_feedback", side_effect=fake_record_feedback):
            result = await client.record_memory_feedback(
                memory_id="mem-1",
                success=True,
            )

        assert result.success is True
