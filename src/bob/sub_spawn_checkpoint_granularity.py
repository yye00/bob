"""Sub-spawn checkpoint granularity for compile-and-verify cycles.

Provides finer-than-feature checkpoints by saving a checkpoint after each
compiler invocation and after each test class, not just at feature completion.
This enables resuming from mid-compile without re-spending the full sub-agent
budget.

Checkpoint types used:
    compiler_invocation  — saved after each call to a compiler / syntax check.
    test_class           — saved after each pytest test class runs.
    verify_cycle         — saved after a full compile+verify round-trip.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CompilerResult:
    """Result from a single compiler invocation."""

    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    files_checked: list[str] = field(default_factory=list)


@dataclass
class TestClassResult:
    """Result from running a single pytest test class."""

    class_name: str
    passed: int
    failed: int
    errors: int
    duration_ms: int = 0
    failure_messages: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0


@dataclass
class VerifyCycleState:
    """Accumulated state across a compile-and-verify cycle.

    Tracks which compiler invocations and test classes have completed so
    that a resumed agent can skip already-done work.
    """

    feature_id: str
    project_id: str
    compiler_steps_done: list[str] = field(default_factory=list)
    test_classes_done: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    last_checkpoint_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "project_id": self.project_id,
            "compiler_steps_done": list(self.compiler_steps_done),
            "test_classes_done": list(self.test_classes_done),
            "total_cost_usd": self.total_cost_usd,
            "total_duration_ms": self.total_duration_ms,
            "last_checkpoint_id": self.last_checkpoint_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerifyCycleState":
        return cls(
            feature_id=data["feature_id"],
            project_id=data["project_id"],
            compiler_steps_done=list(data.get("compiler_steps_done", [])),
            test_classes_done=list(data.get("test_classes_done", [])),
            total_cost_usd=float(data.get("total_cost_usd", 0.0)),
            total_duration_ms=int(data.get("total_duration_ms", 0)),
            last_checkpoint_id=data.get("last_checkpoint_id"),
        )


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def checkpoint_after_compiler(
    *,
    state: VerifyCycleState,
    result: CompilerResult,
    step_name: str,
    task_id: str | None = None,
) -> str:
    """Save a checkpoint immediately after a compiler invocation.

    Args:
        state: Current verify-cycle accumulator; mutated in place (step_name
               is appended to compiler_steps_done).
        result: The result returned by the compiler.
        step_name: Human-readable label for this step (e.g. "mypy", "pytest-collect").
        task_id: Optional task ID to attach to the checkpoint.

    Returns:
        ID of the created checkpoint.
    """
    from bob.db import create_checkpoint

    state.compiler_steps_done.append(step_name)

    snapshot = {
        **state.to_dict(),
        "last_compiler_step": step_name,
        "last_compiler_success": result.success,
        "last_compiler_returncode": result.returncode,
        "last_compiler_files_checked": result.files_checked,
    }

    cp = create_checkpoint(
        project_id=state.project_id,
        feature_id=state.feature_id,
        task_id=task_id,
        checkpoint_type="compiler_invocation",
        state_snapshot=json.dumps(snapshot),
        cost_at_checkpoint=state.total_cost_usd if state.total_cost_usd else None,
        duration_at_checkpoint_ms=state.total_duration_ms if state.total_duration_ms else None,
    )

    state.last_checkpoint_id = cp.id
    logger.debug(
        "Compiler checkpoint saved (step=%s, success=%s, id=%s)",
        step_name,
        result.success,
        cp.id,
    )
    return cp.id


def checkpoint_after_test_class(
    *,
    state: VerifyCycleState,
    result: TestClassResult,
    task_id: str | None = None,
) -> str:
    """Save a checkpoint immediately after a pytest test class completes.

    Args:
        state: Current verify-cycle accumulator; mutated in place (class name
               is appended to test_classes_done).
        result: The result returned by the test class run.
        task_id: Optional task ID to attach to the checkpoint.

    Returns:
        ID of the created checkpoint.
    """
    from bob.db import create_checkpoint

    state.test_classes_done.append(result.class_name)

    snapshot = {
        **state.to_dict(),
        "last_test_class": result.class_name,
        "last_test_class_passed": result.passed,
        "last_test_class_failed": result.failed,
        "last_test_class_errors": result.errors,
        "last_test_class_success": result.success,
    }

    cp = create_checkpoint(
        project_id=state.project_id,
        feature_id=state.feature_id,
        task_id=task_id,
        checkpoint_type="test_class",
        state_snapshot=json.dumps(snapshot),
        cost_at_checkpoint=state.total_cost_usd if state.total_cost_usd else None,
        duration_at_checkpoint_ms=state.total_duration_ms if state.total_duration_ms else None,
    )

    state.last_checkpoint_id = cp.id
    logger.debug(
        "Test-class checkpoint saved (class=%s, passed=%d, failed=%d, id=%s)",
        result.class_name,
        result.passed,
        result.failed,
        cp.id,
    )
    return cp.id


def checkpoint_after_verify_cycle(
    *,
    state: VerifyCycleState,
    all_passed: bool,
    task_id: str | None = None,
) -> str:
    """Save a checkpoint at the end of a complete compile-and-verify round.

    Args:
        state: Final state for the completed round.
        all_passed: Whether the full cycle succeeded.
        task_id: Optional task ID to attach to the checkpoint.

    Returns:
        ID of the created checkpoint.
    """
    from bob.db import create_checkpoint

    snapshot = {
        **state.to_dict(),
        "cycle_complete": True,
        "all_passed": all_passed,
    }

    cp = create_checkpoint(
        project_id=state.project_id,
        feature_id=state.feature_id,
        task_id=task_id,
        checkpoint_type="verify_cycle",
        state_snapshot=json.dumps(snapshot),
        cost_at_checkpoint=state.total_cost_usd if state.total_cost_usd else None,
        duration_at_checkpoint_ms=state.total_duration_ms if state.total_duration_ms else None,
    )

    state.last_checkpoint_id = cp.id
    logger.debug(
        "Verify-cycle checkpoint saved (all_passed=%s, id=%s)",
        all_passed,
        cp.id,
    )
    return cp.id


# ---------------------------------------------------------------------------
# Resume helpers
# ---------------------------------------------------------------------------


def load_cycle_state_from_checkpoint(checkpoint_id: str) -> VerifyCycleState:
    """Reconstruct a VerifyCycleState from a previously saved checkpoint.

    Args:
        checkpoint_id: ID of the checkpoint to load.

    Returns:
        Restored VerifyCycleState.

    Raises:
        ValueError: If the checkpoint does not exist or cannot be parsed.
    """
    from bob.db import get_checkpoint

    cp = get_checkpoint(checkpoint_id)
    if cp is None:
        raise ValueError(f"Checkpoint '{checkpoint_id}' not found")

    try:
        data = json.loads(cp.state_snapshot)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Checkpoint '{checkpoint_id}' has invalid JSON snapshot: {exc}") from exc

    if "feature_id" not in data or "project_id" not in data:
        raise ValueError(
            f"Checkpoint '{checkpoint_id}' snapshot is missing required fields "
            f"(feature_id, project_id)"
        )

    state = VerifyCycleState.from_dict(data)
    state.last_checkpoint_id = checkpoint_id
    return state


def find_latest_cycle_checkpoint(
    *,
    feature_id: str,
    project_id: str,
    checkpoint_type: str | None = None,
) -> "str | None":
    """Find the most recent resumable compile/verify checkpoint for a feature.

    Args:
        feature_id: Feature to search.
        project_id: Project to search within.
        checkpoint_type: Optionally restrict to a specific type
                         (compiler_invocation|test_class|verify_cycle).

    Returns:
        Checkpoint ID of the latest resumable checkpoint, or None if none exists.
    """
    from bob.db import list_checkpoints

    checkpoints = list_checkpoints(feature_id=feature_id)
    cycle_types = {"compiler_invocation", "test_class", "verify_cycle"}

    candidates = [
        cp for cp in checkpoints
        if cp.can_resume
        and cp.project_id == project_id
        and (checkpoint_type is None and cp.checkpoint_type in cycle_types
             or cp.checkpoint_type == checkpoint_type)
    ]

    if not candidates:
        return None

    # list_checkpoints returns in creation order; take the last (most recent).
    return candidates[-1].id


# ---------------------------------------------------------------------------
# High-level runner
# ---------------------------------------------------------------------------


class GranularVerifyRunner:
    """Runs a compile-and-verify cycle with per-step checkpointing.

    This class wraps user-supplied callables for the compiler and test
    execution steps, injecting a checkpoint after each one.  It is
    intentionally thin — business logic stays in the callables.

    Usage::

        runner = GranularVerifyRunner(
            state=VerifyCycleState(feature_id="f1", project_id="p1"),
        )
        for step_name, compiler_fn in compiler_steps:
            result = runner.run_compiler_step(step_name, compiler_fn)
            if not result.success:
                break
        for class_name, test_fn in test_steps:
            result = runner.run_test_class(class_name, test_fn)
        runner.finalize()
    """

    def __init__(
        self,
        state: VerifyCycleState,
        *,
        task_id: str | None = None,
    ) -> None:
        self.state = state
        self.task_id = task_id
        self._compiler_results: list[CompilerResult] = []
        self._test_results: list[TestClassResult] = []

    def run_compiler_step(
        self,
        step_name: str,
        compiler_fn: Any,
    ) -> CompilerResult:
        """Execute one compiler step and checkpoint the outcome.

        If this step was already done in a prior run (its name is in
        ``state.compiler_steps_done``), the call is skipped and a synthetic
        success result is returned so the caller can continue.

        Args:
            step_name: Unique label for this step.
            compiler_fn: Zero-argument callable that returns a CompilerResult.

        Returns:
            CompilerResult from this invocation (or the cached success).
        """
        if step_name in self.state.compiler_steps_done:
            logger.debug("Skipping already-completed compiler step: %s", step_name)
            return CompilerResult(success=True, returncode=0)

        t0 = time.monotonic()
        result = compiler_fn()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result.duration_ms = elapsed_ms
        self.state.total_duration_ms += elapsed_ms

        self._compiler_results.append(result)
        checkpoint_after_compiler(
            state=self.state,
            result=result,
            step_name=step_name,
            task_id=self.task_id,
        )
        return result

    def run_test_class(
        self,
        class_name: str,
        test_fn: Any,
    ) -> TestClassResult:
        """Execute one test class and checkpoint the outcome.

        If this class was already tested in a prior run (its name is in
        ``state.test_classes_done``), the call is skipped and a synthetic
        success result is returned.

        Args:
            class_name: Fully-qualified test class name.
            test_fn: Zero-argument callable that returns a TestClassResult.

        Returns:
            TestClassResult from this invocation (or the cached success).
        """
        if class_name in self.state.test_classes_done:
            logger.debug("Skipping already-completed test class: %s", class_name)
            return TestClassResult(class_name=class_name, passed=1, failed=0, errors=0)

        t0 = time.monotonic()
        result = test_fn()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        result.duration_ms = elapsed_ms
        self.state.total_duration_ms += elapsed_ms

        self._test_results.append(result)
        checkpoint_after_test_class(
            state=self.state,
            result=result,
            task_id=self.task_id,
        )
        return result

    def finalize(self) -> str:
        """Save a verify_cycle checkpoint summarising the completed round.

        Returns:
            Checkpoint ID of the final verify_cycle checkpoint.
        """
        all_passed = (
            all(r.success for r in self._compiler_results)
            and all(r.success for r in self._test_results)
        )
        return checkpoint_after_verify_cycle(
            state=self.state,
            all_passed=all_passed,
            task_id=self.task_id,
        )

    @property
    def all_passed(self) -> bool:
        return (
            all(r.success for r in self._compiler_results)
            and all(r.success for r in self._test_results)
        )
