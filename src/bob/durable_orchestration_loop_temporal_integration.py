"""Durable orchestration loop — Temporal integration.

Wraps the OrchestrationLoop in a Temporal-compatible workflow structure for
multi-hour HPC verification cycles. Provides at-least-once execution,
automatic retries on transient failures, and a history replay for debugging.

Architecture
------------
Even without a live Temporal server or the ``temporalio`` SDK installed, this
module exposes the full Temporal programming model:

* ``DurableOrchestrationConfig``  — typed configuration dataclass
* ``RetryPolicy``                  — exponential-backoff retry configuration
* ``ActivityResult``               — structured result from an activity call
* ``WorkflowHistory`` / ``WorkflowHistoryEntry`` — append-only event log
* ``WorkflowState``                — mutable workflow state with termination
* Activity functions:
    - ``activity_spawn_sub_agent``   — execute a sub-agent for a feature
    - ``activity_run_verification``  — run the verification checklist
    - ``activity_emit_telemetry``    — emit a run.jsonl telemetry record
* ``DurableOrchestrationLoop``     — orchestrator with retry logic + history
* ``run_durable_orchestration_workflow`` — top-level entry point
* ``get_temporal_activities``      — returns list of activity functions for
                                     Temporal worker registration
* ``get_temporal_workflow_class``  — returns the workflow class for Temporal
                                     worker registration

When ``temporalio`` is installed the module transparently applies
``@workflow.defn`` and ``@activity.defn`` decorators so that the functions
can be executed directly by a Temporal worker (``Worker``) without any
further changes.  When ``temporalio`` is absent the decorators are
no-op identity functions and the same code runs in process — useful for
local development and unit tests.

Transient vs. permanent errors
-------------------------------
``ActivityResult.is_retryable()`` classifies errors using a keyword
allow-list.  Transient errors (timeout, connection refused, temporarily
unavailable, 5xx) are retried up to ``RetryPolicy.max_attempts`` with
exponential backoff capped at ``max_interval_seconds``.  Permanent errors
(authentication failed, not found, permission denied) are NOT retried.

History replay
--------------
Every activity invocation appends a ``WorkflowHistoryEntry`` to the loop's
``WorkflowHistory``.  ``DurableOrchestrationLoop.get_history_snapshot()``
serialises the history to a dict that is safe to persist or log, enabling
post-mortem debugging without replaying from Temporal's internal history.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Temporal SDK integration
# ---------------------------------------------------------------------------

try:
    import temporalio.activity as _ta
    import temporalio.workflow as _tw

    def _workflow_defn(cls: type) -> type:  # type: ignore[return]
        return _tw.defn(cls)

    def _workflow_run(fn: Callable) -> Callable:
        return _tw.run(fn)

    def _activity_defn(fn: Callable) -> Callable:
        return _ta.defn(fn)

    _TEMPORAL_AVAILABLE = True
except ImportError:
    def _workflow_defn(cls: type) -> type:
        return cls

    def _workflow_run(fn: Callable) -> Callable:
        return fn

    def _activity_defn(fn: Callable) -> Callable:
        return fn

    _TEMPORAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class DurableOrchestrationConfig:
    """Configuration for the durable orchestration workflow.

    Attributes:
        project_id: Bob project UUID (required).
        max_cost: Optional budget cap in USD; None means unlimited.
        workspace: Filesystem path passed to sub-agents. None → CWD.
        max_retries: Max retries per activity on transient errors.
        retry_backoff_seconds: Initial retry delay (grows exponentially).
        target_feature_id: If set, only execute this one feature.
    """

    project_id: str
    max_cost: float | None = None
    workspace: str | None = None
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    target_feature_id: str | None = None


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Exponential-backoff retry policy mirroring Temporal's RetryPolicy.

    Attributes:
        max_attempts: Total attempts including the first (not retries).
        initial_interval_seconds: Delay before the first retry.
        backoff_coefficient: Multiplier applied to the interval each retry.
        max_interval_seconds: Hard cap on the computed delay.
    """

    max_attempts: int = 3
    initial_interval_seconds: float = 1.0
    backoff_coefficient: float = 2.0
    max_interval_seconds: float = 60.0

    def compute_delay(self, attempt: int) -> float:
        """Return the sleep duration in seconds before retry ``attempt``."""
        raw = self.initial_interval_seconds * (self.backoff_coefficient ** attempt)
        return min(raw, self.max_interval_seconds)


# ---------------------------------------------------------------------------
# ActivityResult
# ---------------------------------------------------------------------------

_TRANSIENT_KEYWORDS = frozenset({
    "timeout",
    "timed out",
    "connection refused",
    "temporarily unavailable",
    "503",
    "502",
    "429",
    "rate limit",
    "service unavailable",
    "network",
    "reset by peer",
    "broken pipe",
})

_PERMANENT_KEYWORDS = frozenset({
    "authentication failed",
    "invalid credentials",
    "not found",
    "permission denied",
    "unauthorized",
    "forbidden",
    "400",
    "401",
    "403",
    "404",
})


@dataclass
class ActivityResult:
    """Structured result returned by every activity function.

    Attributes:
        success: True iff the activity completed without error.
        output: Arbitrary JSON-serialisable data from the activity.
        error: Human-readable error message when success is False.
    """

    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None

    def is_retryable(self) -> bool:
        """Return True if this failure should be retried.

        Successful results and permanent failures are not retried.
        """
        if self.success:
            return False
        if not self.error:
            return False
        lower = self.error.lower()
        for kw in _PERMANENT_KEYWORDS:
            if kw in lower:
                return False
        for kw in _TRANSIENT_KEYWORDS:
            if kw in lower:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"success": self.success, "output": self.output, "error": self.error}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivityResult":
        return cls(success=data["success"], output=data.get("output"), error=data.get("error"))


# ---------------------------------------------------------------------------
# WorkflowHistory
# ---------------------------------------------------------------------------


@dataclass
class WorkflowHistoryEntry:
    """A single recorded event in the workflow history.

    Attributes:
        activity: Name of the activity function.
        feature_id: Feature this entry is associated with.
        attempt: Zero-based attempt number (0 = first try).
        result: The ActivityResult from this invocation.
        timestamp: Unix timestamp when the entry was appended.
    """

    activity: str
    feature_id: str
    attempt: int
    result: ActivityResult
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity": self.activity,
            "feature_id": self.feature_id,
            "attempt": self.attempt,
            "result": self.result.to_dict(),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowHistoryEntry":
        return cls(
            activity=data["activity"],
            feature_id=data["feature_id"],
            attempt=data["attempt"],
            result=ActivityResult.from_dict(data["result"]),
            timestamp=data.get("timestamp", 0.0),
        )


class WorkflowHistory:
    """Append-only event log for the durable orchestration workflow.

    Every activity invocation appends an entry here regardless of outcome.
    The history can be serialised for post-mortem debugging or replay.
    """

    def __init__(self) -> None:
        self.entries: list[WorkflowHistoryEntry] = []

    def __len__(self) -> int:
        return len(self.entries)

    def append(self, entry: WorkflowHistoryEntry) -> None:
        self.entries.append(entry)

    def get_by_activity(self, activity: str) -> list[WorkflowHistoryEntry]:
        return [e for e in self.entries if e.activity == activity]

    def was_successful(self, activity: str, *, feature_id: str) -> bool:
        """Return True if any entry for this activity+feature succeeded."""
        return any(
            e.result.success
            for e in self.entries
            if e.activity == activity and e.feature_id == feature_id
        )

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowHistory":
        obj = cls()
        obj.entries = [WorkflowHistoryEntry.from_dict(d) for d in data.get("entries", [])]
        return obj


# ---------------------------------------------------------------------------
# WorkflowState
# ---------------------------------------------------------------------------


@dataclass
class WorkflowState:
    """Mutable state snapshot of the durable orchestration workflow.

    Serialisable to a dict for checkpointing / replay.
    """

    project_id: str
    features_completed: int = 0
    features_failed: int = 0
    total_cost_usd: float = 0.0
    is_terminal: bool = False
    termination_reason: str | None = None

    def mark_completed(self, reason: str) -> None:
        self.is_terminal = True
        self.termination_reason = reason

    def increment_cost(self, amount: float) -> None:
        self.total_cost_usd += amount

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Internal helpers (thin wrappers; replaced by mocks in tests)
# ---------------------------------------------------------------------------


async def _call_spawn_sub_agent(inp: "SpawnSubAgentInput") -> ActivityResult:
    """Invoke the Bob sub-agent for a feature.

    Delegates to the OrchestrationLoop / claude_executor path.  In
    production this runs the real Claude Code SDK; in tests it is mocked.
    """
    try:
        from bob.orchestrator.claude_executor import spawn_sub_agent, build_sub_agent_options

        options = build_sub_agent_options(
            cwd=inp.workspace or ".",
            model=None,
        )
        result = await spawn_sub_agent(
            prompt=inp.prompt,
            options=options,
        )
        return ActivityResult(
            success=result.success,
            output={
                "cost_usd": result.cost_usd,
                "num_turns": result.num_turns,
                "response": result.response[:500] if result.response else None,
            },
            error=result.error if not result.success else None,
        )
    except Exception as exc:
        return ActivityResult(success=False, error=str(exc))


async def _call_run_verification(inp: "RunVerificationInput") -> ActivityResult:
    """Run the Bob verification checklist for a feature."""
    try:
        from bob.superpowers import run_verification_checklist

        passed = await run_verification_checklist(
            feature_id=inp.feature_id,
            workspace=inp.workspace or ".",
        )
        return ActivityResult(success=passed, output={"passed": passed})
    except Exception as exc:
        return ActivityResult(success=False, error=str(exc))


def _call_emit_telemetry(inp: "EmitTelemetryInput") -> None:
    """Emit one telemetry record to run.jsonl."""
    from bob.telemetry import emit_telemetry_line

    emit_telemetry_line(
        run_id=inp.run_id,
        feature_id=inp.feature_id,
        completion_status=inp.completion_status,
        cost_usd=inp.cost_usd,
        duration_ms=inp.duration_ms,
    )


def _get_ready_features(config: DurableOrchestrationConfig) -> list[dict[str, Any]]:
    """Return a list of ready features for the given project.

    Each dict has keys: id, name, prompt, run_id.
    """
    try:
        from bob import db

        features = db.get_ready_features(project_id=config.project_id)
        if config.target_feature_id:
            features = [f for f in features if f.id == config.target_feature_id]
        return [
            {
                "id": f.id,
                "name": f.name or "",
                "prompt": f.description or "",
                "run_id": str(uuid.uuid4()),
            }
            for f in features
        ]
    except Exception as exc:
        logger.warning("Could not query ready features: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Activity input dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SpawnSubAgentInput:
    """Input for the spawn_sub_agent activity."""

    feature_id: str
    feature_name: str
    prompt: str
    workspace: str | None = None


@dataclass
class RunVerificationInput:
    """Input for the run_verification activity."""

    feature_id: str
    workspace: str | None = None


@dataclass
class EmitTelemetryInput:
    """Input for the emit_telemetry activity."""

    run_id: str
    feature_id: str
    completion_status: str
    cost_usd: float
    duration_ms: int


# ---------------------------------------------------------------------------
# Activity functions
# ---------------------------------------------------------------------------


@_activity_defn
async def activity_spawn_sub_agent(inp: SpawnSubAgentInput) -> ActivityResult:
    """Temporal activity: spawn a Bob sub-agent to implement a feature.

    Wraps ``_call_spawn_sub_agent`` so the function signature matches the
    Temporal activity protocol.  Provides at-least-once execution: the
    caller (``DurableOrchestrationLoop._execute_activity_with_retry``)
    handles retries on transient failures.
    """
    return await _call_spawn_sub_agent(inp)


@_activity_defn
async def activity_run_verification(inp: RunVerificationInput) -> ActivityResult:
    """Temporal activity: run the Bob verification checklist."""
    return await _call_run_verification(inp)


@_activity_defn
async def activity_emit_telemetry(inp: EmitTelemetryInput) -> ActivityResult:
    """Temporal activity: emit a telemetry record to run.jsonl."""
    try:
        _call_emit_telemetry(inp)
        return ActivityResult(success=True)
    except Exception as exc:
        return ActivityResult(success=False, error=str(exc))


# ---------------------------------------------------------------------------
# DurableOrchestrationLoop
# ---------------------------------------------------------------------------


class DurableOrchestrationLoop:
    """Durable orchestration loop with Temporal-compatible activity model.

    Orchestrates features by executing three activities in sequence per
    feature:

    1. ``activity_spawn_sub_agent``  — run the Claude sub-agent
    2. ``activity_run_verification`` — verify the implementation
    3. ``activity_emit_telemetry``   — emit a telemetry record

    Each activity is retried on transient failures according to
    ``config.max_retries`` and ``config.retry_backoff_seconds``.  All
    invocations are recorded in ``self.history`` for replay debugging.
    """

    def __init__(self, config: DurableOrchestrationConfig) -> None:
        self.config = config
        self.history = WorkflowHistory()
        self.state = WorkflowState(project_id=config.project_id)
        self._retry_policy = RetryPolicy(
            max_attempts=config.max_retries + 1,
            initial_interval_seconds=config.retry_backoff_seconds,
            backoff_coefficient=2.0,
            max_interval_seconds=max(config.retry_backoff_seconds * 64, 60.0),
        )

    async def _execute_activity_with_retry(
        self,
        *,
        activity_fn: Callable[..., Coroutine[Any, Any, ActivityResult]],
        activity_input: Any,
        activity_name: str,
        feature_id: str,
    ) -> ActivityResult:
        """Execute ``activity_fn`` with retry and history recording.

        Retries up to ``config.max_retries`` times on transient failures.
        Permanent failures and successes are returned immediately.
        Every invocation (including retries) is appended to ``self.history``.
        """
        max_attempts = self._retry_policy.max_attempts
        last_result: ActivityResult = ActivityResult(success=False, error="no attempts made")

        for attempt in range(max_attempts):
            result = await activity_fn(activity_input)
            self.history.append(
                WorkflowHistoryEntry(
                    activity=activity_name,
                    feature_id=feature_id,
                    attempt=attempt,
                    result=result,
                )
            )
            last_result = result

            if result.success:
                return result

            if not result.is_retryable():
                logger.info(
                    "Activity %s for feature %s: permanent failure (no retry): %s",
                    activity_name,
                    feature_id,
                    result.error,
                )
                return result

            if attempt < max_attempts - 1:
                delay = self._retry_policy.compute_delay(attempt)
                logger.warning(
                    "Activity %s for feature %s: transient failure (attempt %d/%d), "
                    "retrying in %.1fs: %s",
                    activity_name,
                    feature_id,
                    attempt + 1,
                    max_attempts,
                    delay,
                    result.error,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Activity %s for feature %s: exhausted %d retries: %s",
                    activity_name,
                    feature_id,
                    max_attempts,
                    result.error,
                )

        return last_result

    async def run_feature(
        self,
        *,
        feature_id: str,
        feature_name: str,
        prompt: str,
        run_id: str,
    ) -> dict[str, Any]:
        """Execute the three-activity pipeline for one feature.

        Returns a dict with keys:
            status: "completed" | "failed"
            feature_id: the feature ID
            cost_usd: float (0.0 if unavailable)
        """
        start_ms = int(time.time() * 1000)

        # --- Activity 1: spawn sub-agent ---
        spawn_result = await self._execute_activity_with_retry(
            activity_fn=activity_spawn_sub_agent,
            activity_input=SpawnSubAgentInput(
                feature_id=feature_id,
                feature_name=feature_name,
                prompt=prompt,
                workspace=self.config.workspace,
            ),
            activity_name="spawn_sub_agent",
            feature_id=feature_id,
        )

        cost_usd = 0.0
        if spawn_result.output:
            cost_usd = float(spawn_result.output.get("cost_usd") or 0.0)

        if not spawn_result.success:
            duration_ms = int(time.time() * 1000) - start_ms
            await self._execute_activity_with_retry(
                activity_fn=activity_emit_telemetry,
                activity_input=EmitTelemetryInput(
                    run_id=run_id,
                    feature_id=feature_id,
                    completion_status="failed",
                    cost_usd=cost_usd,
                    duration_ms=duration_ms,
                ),
                activity_name="emit_telemetry",
                feature_id=feature_id,
            )
            return {"status": "failed", "feature_id": feature_id, "cost_usd": cost_usd}

        # --- Activity 2: run verification ---
        verify_result = await self._execute_activity_with_retry(
            activity_fn=activity_run_verification,
            activity_input=RunVerificationInput(
                feature_id=feature_id,
                workspace=self.config.workspace,
            ),
            activity_name="run_verification",
            feature_id=feature_id,
        )

        status = "completed" if verify_result.success else "failed"
        duration_ms = int(time.time() * 1000) - start_ms

        # --- Activity 3: emit telemetry ---
        await self._execute_activity_with_retry(
            activity_fn=activity_emit_telemetry,
            activity_input=EmitTelemetryInput(
                run_id=run_id,
                feature_id=feature_id,
                completion_status=status,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
            ),
            activity_name="emit_telemetry",
            feature_id=feature_id,
        )

        return {"status": status, "feature_id": feature_id, "cost_usd": cost_usd}

    def get_history_snapshot(self) -> dict[str, Any]:
        """Return a serialisable snapshot of the full activity history."""
        return self.history.to_dict()


# ---------------------------------------------------------------------------
# Temporal workflow class
# ---------------------------------------------------------------------------


@_workflow_defn
class DurableOrchestrationWorkflow:
    """Temporal workflow definition for the durable orchestration loop.

    When ``temporalio`` is installed this class is registered as a Temporal
    workflow.  When ``temporalio`` is absent the ``@_workflow_defn`` decorator
    is a no-op and ``run`` can be called directly as a regular async method.
    """

    @_workflow_run
    async def run(self, config: DurableOrchestrationConfig) -> dict[str, Any]:
        """Execute the durable orchestration workflow.

        Calls ``run_durable_orchestration_workflow`` so the core logic is
        shared between the Temporal-hosted path and the direct async path.
        """
        state = await run_durable_orchestration_workflow(config)
        return state.to_dict()


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


async def run_durable_orchestration_workflow(
    config: DurableOrchestrationConfig,
) -> WorkflowState:
    """Run the durable orchestration workflow and return the final state.

    Iterates over all ready features, executing the three-activity pipeline
    for each.  Terminates when:

    * No more ready features are available → ``all_completed``
    * Budget cap is exceeded → ``budget_exceeded``

    Returns a ``WorkflowState`` capturing the final counts and reason.
    """
    loop = DurableOrchestrationLoop(config=config)
    features = _get_ready_features(config)

    if not features:
        loop.state.mark_completed("all_completed")
        return loop.state

    for feat in features:
        if config.max_cost is not None and loop.state.total_cost_usd >= config.max_cost:
            logger.warning(
                "Budget cap %.2f USD reached after %.2f USD; stopping.",
                config.max_cost,
                loop.state.total_cost_usd,
            )
            loop.state.mark_completed("budget_exceeded")
            return loop.state

        result = await loop.run_feature(
            feature_id=feat["id"],
            feature_name=feat["name"],
            prompt=feat["prompt"],
            run_id=feat["run_id"],
        )

        cost = float(result.get("cost_usd") or 0.0)
        loop.state.increment_cost(cost)

        if result["status"] == "completed":
            loop.state.features_completed += 1
        else:
            loop.state.features_failed += 1

    loop.state.mark_completed("all_completed")
    return loop.state


# ---------------------------------------------------------------------------
# Temporal registration helpers
# ---------------------------------------------------------------------------


def get_temporal_activities() -> list[Callable]:
    """Return the list of activity functions for Temporal worker registration.

    Usage::

        from temporalio.worker import Worker
        from bob.durable_orchestration_loop_temporal_integration import (
            get_temporal_activities,
            get_temporal_workflow_class,
        )

        worker = Worker(
            client,
            task_queue="bob-hpc",
            workflows=[get_temporal_workflow_class()],
            activities=get_temporal_activities(),
        )
    """
    return [
        activity_spawn_sub_agent,
        activity_run_verification,
        activity_emit_telemetry,
    ]


def get_temporal_workflow_class() -> type:
    """Return the Temporal workflow class for worker registration."""
    return DurableOrchestrationWorkflow
