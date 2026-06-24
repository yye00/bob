"""Tests for Durable orchestration loop (Temporal integration).

Feature: Wrap the OrchestrationLoop in a Temporal workflow for multi-hour
HPC verification cycles. Activities: spawn_sub_agent, run_verification,
emit_telemetry. Provides at-least-once execution, automatic retries
on transient failures, and a history replay for debugging.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.durable_orchestration_loop_temporal_integration import (
    ActivityResult,
    DurableOrchestrationConfig,
    DurableOrchestrationLoop,
    EmitTelemetryInput,
    RetryPolicy,
    RunVerificationInput,
    SpawnSubAgentInput,
    WorkflowHistory,
    WorkflowHistoryEntry,
    WorkflowState,
    activity_emit_telemetry,
    activity_run_verification,
    activity_spawn_sub_agent,
    run_durable_orchestration_workflow,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def feature_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def project_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def basic_config(project_id: str) -> DurableOrchestrationConfig:
    return DurableOrchestrationConfig(
        project_id=project_id,
        max_cost=10.0,
        workspace="/tmp/test-workspace",
        max_retries=3,
        retry_backoff_seconds=0.01,
    )


# ---------------------------------------------------------------------------
# DurableOrchestrationConfig
# ---------------------------------------------------------------------------


class TestDurableOrchestrationConfig:
    def test_required_fields(self, project_id: str) -> None:
        cfg = DurableOrchestrationConfig(project_id=project_id)
        assert cfg.project_id == project_id

    def test_defaults(self, project_id: str) -> None:
        cfg = DurableOrchestrationConfig(project_id=project_id)
        assert cfg.max_cost is None
        assert cfg.workspace is None
        assert cfg.max_retries == 3
        assert cfg.retry_backoff_seconds == 1.0

    def test_custom_values(self, project_id: str) -> None:
        cfg = DurableOrchestrationConfig(
            project_id=project_id,
            max_cost=50.0,
            workspace="/my/workspace",
            max_retries=5,
            retry_backoff_seconds=2.0,
        )
        assert cfg.max_cost == 50.0
        assert cfg.workspace == "/my/workspace"
        assert cfg.max_retries == 5
        assert cfg.retry_backoff_seconds == 2.0


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_default_policy(self) -> None:
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.backoff_coefficient > 0
        assert policy.initial_interval_seconds > 0

    def test_custom_policy(self) -> None:
        policy = RetryPolicy(
            max_attempts=5,
            initial_interval_seconds=2.0,
            backoff_coefficient=1.5,
            max_interval_seconds=30.0,
        )
        assert policy.max_attempts == 5
        assert policy.initial_interval_seconds == 2.0
        assert policy.backoff_coefficient == 1.5
        assert policy.max_interval_seconds == 30.0

    def test_compute_delay_grows_with_attempts(self) -> None:
        policy = RetryPolicy(
            initial_interval_seconds=1.0,
            backoff_coefficient=2.0,
            max_interval_seconds=100.0,
        )
        delay0 = policy.compute_delay(attempt=0)
        delay1 = policy.compute_delay(attempt=1)
        delay2 = policy.compute_delay(attempt=2)
        assert delay0 < delay1 < delay2

    def test_compute_delay_capped_at_max(self) -> None:
        policy = RetryPolicy(
            initial_interval_seconds=10.0,
            backoff_coefficient=100.0,
            max_interval_seconds=20.0,
        )
        delay = policy.compute_delay(attempt=5)
        assert delay <= 20.0


# ---------------------------------------------------------------------------
# ActivityResult
# ---------------------------------------------------------------------------


class TestActivityResult:
    def test_success_result(self) -> None:
        result = ActivityResult(success=True, output={"key": "value"})
        assert result.success is True
        assert result.output == {"key": "value"}
        assert result.error is None

    def test_failure_result(self) -> None:
        result = ActivityResult(success=False, error="Connection refused")
        assert result.success is False
        assert result.error == "Connection refused"

    def test_is_retryable_transient_errors(self) -> None:
        for msg in ["timeout", "connection refused", "temporarily unavailable", "503"]:
            result = ActivityResult(success=False, error=msg)
            assert result.is_retryable() is True, f"Expected {msg!r} to be retryable"

    def test_is_retryable_permanent_errors(self) -> None:
        for msg in ["authentication failed", "invalid credentials", "not found", "permission denied"]:
            result = ActivityResult(success=False, error=msg)
            assert result.is_retryable() is False, f"Expected {msg!r} to not be retryable"

    def test_success_not_retryable(self) -> None:
        result = ActivityResult(success=True)
        assert result.is_retryable() is False


# ---------------------------------------------------------------------------
# WorkflowHistory and WorkflowHistoryEntry
# ---------------------------------------------------------------------------


class TestWorkflowHistory:
    def test_empty_history(self) -> None:
        history = WorkflowHistory()
        assert len(history) == 0
        assert history.entries == []

    def test_append_entry(self) -> None:
        history = WorkflowHistory()
        entry = WorkflowHistoryEntry(
            activity="spawn_sub_agent",
            feature_id="feat-1",
            attempt=0,
            result=ActivityResult(success=True),
        )
        history.append(entry)
        assert len(history) == 1
        assert history.entries[0].activity == "spawn_sub_agent"

    def test_get_entries_by_activity(self) -> None:
        history = WorkflowHistory()
        history.append(WorkflowHistoryEntry(activity="spawn_sub_agent", feature_id="f1", attempt=0, result=ActivityResult(success=True)))
        history.append(WorkflowHistoryEntry(activity="run_verification", feature_id="f1", attempt=0, result=ActivityResult(success=False, error="timeout")))
        history.append(WorkflowHistoryEntry(activity="run_verification", feature_id="f1", attempt=1, result=ActivityResult(success=True)))

        spawn_entries = history.get_by_activity("spawn_sub_agent")
        verify_entries = history.get_by_activity("run_verification")
        assert len(spawn_entries) == 1
        assert len(verify_entries) == 2

    def test_was_activity_successful(self) -> None:
        history = WorkflowHistory()
        history.append(WorkflowHistoryEntry(activity="emit_telemetry", feature_id="f1", attempt=0, result=ActivityResult(success=True)))
        assert history.was_successful("emit_telemetry", feature_id="f1") is True

    def test_was_activity_not_successful(self) -> None:
        history = WorkflowHistory()
        history.append(WorkflowHistoryEntry(activity="run_verification", feature_id="f1", attempt=0, result=ActivityResult(success=False, error="failed")))
        assert history.was_successful("run_verification", feature_id="f1") is False

    def test_to_dict_roundtrip(self) -> None:
        history = WorkflowHistory()
        history.append(WorkflowHistoryEntry(activity="spawn_sub_agent", feature_id="f1", attempt=0, result=ActivityResult(success=True, output={"cost": 0.5})))
        data = history.to_dict()
        restored = WorkflowHistory.from_dict(data)
        assert len(restored) == 1
        assert restored.entries[0].activity == "spawn_sub_agent"
        assert restored.entries[0].result.output == {"cost": 0.5}


# ---------------------------------------------------------------------------
# WorkflowState
# ---------------------------------------------------------------------------


class TestWorkflowState:
    def test_initial_state(self, project_id: str) -> None:
        state = WorkflowState(project_id=project_id)
        assert state.project_id == project_id
        assert state.features_completed == 0
        assert state.features_failed == 0
        assert state.total_cost_usd == 0.0
        assert state.is_terminal is False

    def test_mark_completed(self, project_id: str) -> None:
        state = WorkflowState(project_id=project_id)
        state.mark_completed("all_completed")
        assert state.is_terminal is True
        assert state.termination_reason == "all_completed"

    def test_increment_cost(self, project_id: str) -> None:
        state = WorkflowState(project_id=project_id)
        state.increment_cost(1.5)
        state.increment_cost(2.0)
        assert abs(state.total_cost_usd - 3.5) < 1e-9

    def test_to_dict_roundtrip(self, project_id: str) -> None:
        state = WorkflowState(project_id=project_id)
        state.features_completed = 3
        state.increment_cost(5.0)
        state.mark_completed("budget_exceeded")
        data = state.to_dict()
        restored = WorkflowState.from_dict(data)
        assert restored.project_id == project_id
        assert restored.features_completed == 3
        assert restored.total_cost_usd == 5.0
        assert restored.is_terminal is True
        assert restored.termination_reason == "budget_exceeded"


# ---------------------------------------------------------------------------
# Activity functions
# ---------------------------------------------------------------------------


class TestActivitySpawnSubAgent:
    @pytest.mark.asyncio
    async def test_spawn_sub_agent_success(self, feature_id: str) -> None:
        inp = SpawnSubAgentInput(
            feature_id=feature_id,
            feature_name="Test Feature",
            prompt="Implement test feature",
            workspace="/tmp/ws",
        )
        with patch(
            "bob.durable_orchestration_loop_temporal_integration._call_spawn_sub_agent",
            new_callable=AsyncMock,
        ) as mock_spawn:
            mock_spawn.return_value = ActivityResult(success=True, output={"cost_usd": 0.25, "num_turns": 5})
            result = await activity_spawn_sub_agent(inp)
        assert result.success is True
        assert result.output["cost_usd"] == 0.25

    @pytest.mark.asyncio
    async def test_spawn_sub_agent_propagates_error(self, feature_id: str) -> None:
        inp = SpawnSubAgentInput(
            feature_id=feature_id,
            feature_name="Test Feature",
            prompt="Implement test feature",
            workspace="/tmp/ws",
        )
        with patch(
            "bob.durable_orchestration_loop_temporal_integration._call_spawn_sub_agent",
            new_callable=AsyncMock,
        ) as mock_spawn:
            mock_spawn.return_value = ActivityResult(success=False, error="timeout connecting to Claude")
            result = await activity_spawn_sub_agent(inp)
        assert result.success is False
        assert "timeout" in result.error


class TestActivityRunVerification:
    @pytest.mark.asyncio
    async def test_run_verification_success(self, feature_id: str) -> None:
        inp = RunVerificationInput(feature_id=feature_id, workspace="/tmp/ws")
        with patch(
            "bob.durable_orchestration_loop_temporal_integration._call_run_verification",
            new_callable=AsyncMock,
        ) as mock_verify:
            mock_verify.return_value = ActivityResult(success=True, output={"passed": True})
            result = await activity_run_verification(inp)
        assert result.success is True
        assert result.output["passed"] is True

    @pytest.mark.asyncio
    async def test_run_verification_failure(self, feature_id: str) -> None:
        inp = RunVerificationInput(feature_id=feature_id, workspace="/tmp/ws")
        with patch(
            "bob.durable_orchestration_loop_temporal_integration._call_run_verification",
            new_callable=AsyncMock,
        ) as mock_verify:
            mock_verify.return_value = ActivityResult(success=False, error="tests failed")
            result = await activity_run_verification(inp)
        assert result.success is False


class TestActivityEmitTelemetry:
    @pytest.mark.asyncio
    async def test_emit_telemetry_success(self, feature_id: str) -> None:
        inp = EmitTelemetryInput(
            run_id="run-1",
            feature_id=feature_id,
            completion_status="completed",
            cost_usd=0.5,
            duration_ms=30000,
        )
        with patch(
            "bob.durable_orchestration_loop_temporal_integration._call_emit_telemetry"
        ) as mock_emit:
            mock_emit.return_value = None
            result = await activity_emit_telemetry(inp)
        assert result.success is True
        mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_telemetry_handles_exception(self, feature_id: str) -> None:
        inp = EmitTelemetryInput(
            run_id="run-1",
            feature_id=feature_id,
            completion_status="failed",
            cost_usd=0.0,
            duration_ms=100,
        )
        with patch(
            "bob.durable_orchestration_loop_temporal_integration._call_emit_telemetry",
            side_effect=OSError("disk full"),
        ):
            result = await activity_emit_telemetry(inp)
        assert result.success is False
        assert "disk full" in result.error


# ---------------------------------------------------------------------------
# DurableOrchestrationLoop
# ---------------------------------------------------------------------------


class TestDurableOrchestrationLoop:
    def test_construction(self, basic_config: DurableOrchestrationConfig) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        assert loop.config is basic_config
        assert isinstance(loop.history, WorkflowHistory)
        assert isinstance(loop.state, WorkflowState)

    def test_initial_state_matches_config(self, basic_config: DurableOrchestrationConfig) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        assert loop.state.project_id == basic_config.project_id

    @pytest.mark.asyncio
    async def test_execute_activity_with_retry_success_first_try(
        self, basic_config: DurableOrchestrationConfig
    ) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        mock_activity = AsyncMock(return_value=ActivityResult(success=True, output={"done": True}))
        result = await loop._execute_activity_with_retry(
            activity_fn=mock_activity,
            activity_input=object(),
            activity_name="test_activity",
            feature_id="feat-1",
        )
        assert result.success is True
        mock_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_activity_retries_on_transient_failure(
        self, basic_config: DurableOrchestrationConfig
    ) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        transient = ActivityResult(success=False, error="timeout connecting")
        success = ActivityResult(success=True, output={"done": True})
        call_count = 0

        async def flaky(_inp: Any) -> ActivityResult:
            nonlocal call_count
            call_count += 1
            return transient if call_count < 2 else success

        result = await loop._execute_activity_with_retry(
            activity_fn=flaky,
            activity_input=object(),
            activity_name="test_activity",
            feature_id="feat-1",
        )
        assert result.success is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_activity_stops_after_max_retries(
        self, basic_config: DurableOrchestrationConfig
    ) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        always_fails = AsyncMock(
            return_value=ActivityResult(success=False, error="timeout connecting")
        )
        result = await loop._execute_activity_with_retry(
            activity_fn=always_fails,
            activity_input=object(),
            activity_name="test_activity",
            feature_id="feat-1",
        )
        assert result.success is False
        assert always_fails.call_count == basic_config.max_retries + 1

    @pytest.mark.asyncio
    async def test_execute_activity_does_not_retry_permanent_error(
        self, basic_config: DurableOrchestrationConfig
    ) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        permanent_fail = AsyncMock(
            return_value=ActivityResult(success=False, error="authentication failed")
        )
        result = await loop._execute_activity_with_retry(
            activity_fn=permanent_fail,
            activity_input=object(),
            activity_name="test_activity",
            feature_id="feat-1",
        )
        assert result.success is False
        permanent_fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_activity_records_history(
        self, basic_config: DurableOrchestrationConfig
    ) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        success = AsyncMock(return_value=ActivityResult(success=True))
        await loop._execute_activity_with_retry(
            activity_fn=success,
            activity_input=object(),
            activity_name="spawn_sub_agent",
            feature_id="feat-1",
        )
        entries = loop.history.get_by_activity("spawn_sub_agent")
        assert len(entries) == 1
        assert entries[0].feature_id == "feat-1"
        assert entries[0].result.success is True

    @pytest.mark.asyncio
    async def test_run_feature_orchestrates_all_three_activities(
        self, basic_config: DurableOrchestrationConfig, feature_id: str
    ) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)

        async def mock_spawn(inp: SpawnSubAgentInput) -> ActivityResult:
            return ActivityResult(success=True, output={"cost_usd": 0.3, "num_turns": 4})

        async def mock_verify(inp: RunVerificationInput) -> ActivityResult:
            return ActivityResult(success=True, output={"passed": True})

        async def mock_telemetry(inp: EmitTelemetryInput) -> ActivityResult:
            return ActivityResult(success=True)

        with (
            patch("bob.durable_orchestration_loop_temporal_integration.activity_spawn_sub_agent", mock_spawn),
            patch("bob.durable_orchestration_loop_temporal_integration.activity_run_verification", mock_verify),
            patch("bob.durable_orchestration_loop_temporal_integration.activity_emit_telemetry", mock_telemetry),
        ):
            result = await loop.run_feature(
                feature_id=feature_id,
                feature_name="My Feature",
                prompt="Implement my feature",
                run_id="run-001",
            )

        assert result["status"] == "completed"
        assert result["feature_id"] == feature_id

    @pytest.mark.asyncio
    async def test_run_feature_emits_telemetry_on_spawn_failure(
        self, basic_config: DurableOrchestrationConfig, feature_id: str
    ) -> None:
        loop = DurableOrchestrationLoop(config=basic_config)
        telemetry_calls: list[EmitTelemetryInput] = []

        async def mock_spawn(inp: SpawnSubAgentInput) -> ActivityResult:
            return ActivityResult(success=False, error="authentication failed")

        async def mock_telemetry(inp: EmitTelemetryInput) -> ActivityResult:
            telemetry_calls.append(inp)
            return ActivityResult(success=True)

        with (
            patch("bob.durable_orchestration_loop_temporal_integration.activity_spawn_sub_agent", mock_spawn),
            patch("bob.durable_orchestration_loop_temporal_integration.activity_emit_telemetry", mock_telemetry),
        ):
            result = await loop.run_feature(
                feature_id=feature_id,
                feature_name="Failing Feature",
                prompt="...",
                run_id="run-fail",
            )

        assert result["status"] == "failed"
        assert len(telemetry_calls) >= 1
        assert telemetry_calls[-1].completion_status in ("failed", "error")


# ---------------------------------------------------------------------------
# run_durable_orchestration_workflow (top-level entry point)
# ---------------------------------------------------------------------------


class TestRunDurableOrchestrationWorkflow:
    @pytest.mark.asyncio
    async def test_returns_workflow_state(self, project_id: str) -> None:
        config = DurableOrchestrationConfig(project_id=project_id, max_retries=1, retry_backoff_seconds=0.01)

        async def mock_run_feature(**kwargs: Any) -> dict[str, Any]:
            return {"status": "completed", "feature_id": kwargs["feature_id"]}

        with patch(
            "bob.durable_orchestration_loop_temporal_integration.DurableOrchestrationLoop.run_feature",
            mock_run_feature,
        ):
            with patch(
                "bob.durable_orchestration_loop_temporal_integration._get_ready_features",
                return_value=[],
            ):
                state = await run_durable_orchestration_workflow(config)

        assert isinstance(state, WorkflowState)
        assert state.project_id == project_id
        assert state.is_terminal is True

    @pytest.mark.asyncio
    async def test_processes_features_to_completion(self, project_id: str) -> None:
        config = DurableOrchestrationConfig(project_id=project_id, max_retries=1, retry_backoff_seconds=0.01)
        feature_ids = [str(uuid.uuid4()), str(uuid.uuid4())]

        call_order: list[str] = []

        async def mock_run_feature(self_: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append(kwargs["feature_id"])
            return {"status": "completed", "feature_id": kwargs["feature_id"], "cost_usd": 0.1}

        features = [
            {"id": fid, "name": f"Feature {i}", "prompt": "...", "run_id": "r1"}
            for i, fid in enumerate(feature_ids)
        ]

        with patch.object(
            DurableOrchestrationLoop,
            "run_feature",
            new=mock_run_feature,
        ):
            with patch(
                "bob.durable_orchestration_loop_temporal_integration._get_ready_features",
                return_value=features,
            ):
                state = await run_durable_orchestration_workflow(config)

        assert state.features_completed == len(feature_ids)
        assert state.is_terminal is True

    @pytest.mark.asyncio
    async def test_temporal_workflow_registration(self) -> None:
        """Verify the module exposes workflow/activity registration helpers."""
        from bob.durable_orchestration_loop_temporal_integration import (
            get_temporal_activities,
            get_temporal_workflow_class,
        )

        activities = get_temporal_activities()
        assert len(activities) >= 3
        activity_names = {fn.__name__ for fn in activities}
        assert "activity_spawn_sub_agent" in activity_names
        assert "activity_run_verification" in activity_names
        assert "activity_emit_telemetry" in activity_names

        workflow_cls = get_temporal_workflow_class()
        assert workflow_cls is not None
        assert hasattr(workflow_cls, "run")

    @pytest.mark.asyncio
    async def test_history_replay_support(self, project_id: str) -> None:
        """Verify that history can be serialized for replay debugging."""
        config = DurableOrchestrationConfig(project_id=project_id, max_retries=1, retry_backoff_seconds=0.01)
        loop = DurableOrchestrationLoop(config=config)

        loop.history.append(
            WorkflowHistoryEntry(
                activity="spawn_sub_agent",
                feature_id="f1",
                attempt=0,
                result=ActivityResult(success=True, output={"cost_usd": 0.2}),
            )
        )

        snapshot = loop.get_history_snapshot()
        assert isinstance(snapshot, dict)
        assert "entries" in snapshot
        assert len(snapshot["entries"]) == 1
        assert snapshot["entries"][0]["activity"] == "spawn_sub_agent"
