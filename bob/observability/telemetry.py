"""Run-level telemetry for BOB framework.

Tracks per-task and per-run metrics including wall clock time, attempts,
debug attempts, verification results, and error messages. Persists to
JSON files for post-run analysis via `bob metrics`.
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class TaskAttempt:
    """Record of a single task execution attempt."""
    attempt_number: int
    started_at: str
    ended_at: Optional[str] = None
    wall_clock_seconds: float = 0.0
    model_used: str = ""
    success: bool = False
    is_debug: bool = False
    debug_attempt_number: Optional[int] = None
    verification_passed: bool = False
    verification_message: Optional[str] = None
    error_message: Optional[str] = None
    stall_detected: bool = False


@dataclass
class TaskTelemetry:
    """Telemetry data for a single task."""
    task_id: str
    spec_id: str
    title: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    wall_clock_seconds: float = 0.0
    total_attempts: int = 0
    debug_attempts: int = 0
    model_used: str = ""
    final_status: str = ""
    verification_results: list[dict[str, Any]] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    escalations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunSummary:
    """Summary of a complete run."""
    run_id: str
    started_at: str
    ended_at: Optional[str] = None
    wall_clock_seconds: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_tasks: int = 0
    total_attempts: int = 0
    total_debug_attempts: int = 0
    total_iterations: int = 0
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)


class RunTelemetry:
    """Tracks telemetry for a single BOB run.

    Collects per-task and per-run metrics and persists them to
    ``<workspace>/.bob/telemetry/<run_id>.json``.
    """

    def __init__(self, workspace: Path, run_id: Optional[str] = None) -> None:
        self.workspace = Path(workspace)
        self.run_id = run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.tasks: dict[str, TaskTelemetry] = {}
        self._current_attempts: dict[str, TaskAttempt] = {}  # task_id -> current attempt
        self.total_iterations: int = 0

        # Ensure telemetry dir exists
        self._telemetry_dir = self.workspace / ".bob" / "telemetry"
        self._telemetry_dir.mkdir(parents=True, exist_ok=True)

    def start_run(self) -> None:
        """Mark the start of a run."""
        self.start_time = time.time()

    def end_run(self) -> None:
        """Mark the end of a run and persist telemetry."""
        self.end_time = time.time()
        self._persist()

    def _ensure_task(self, task_id: str, spec_id: str = "", title: str = "") -> TaskTelemetry:
        """Get or create a TaskTelemetry entry."""
        if task_id not in self.tasks:
            self.tasks[task_id] = TaskTelemetry(
                task_id=task_id,
                spec_id=spec_id,
                title=title,
            )
        task = self.tasks[task_id]
        if spec_id and not task.spec_id:
            task.spec_id = spec_id
        if title and not task.title:
            task.title = title
        return task

    def start_task_attempt(
        self,
        task_id: str,
        spec_id: str = "",
        title: str = "",
        model: str = "",
        is_debug: bool = False,
        debug_attempt_number: Optional[int] = None,
    ) -> None:
        """Record the start of a task attempt."""
        task_tel = self._ensure_task(task_id, spec_id, title)
        if not task_tel.started_at:
            task_tel.started_at = datetime.now(timezone.utc).isoformat()
        task_tel.model_used = model
        task_tel.total_attempts += 1
        self.total_iterations += 1

        if is_debug:
            task_tel.debug_attempts += 1

        attempt = TaskAttempt(
            attempt_number=task_tel.total_attempts,
            started_at=datetime.now(timezone.utc).isoformat(),
            model_used=model,
            is_debug=is_debug,
            debug_attempt_number=debug_attempt_number,
        )
        self._current_attempts[task_id] = attempt

    def end_task_attempt(
        self,
        task_id: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Record the end of a task attempt."""
        task_tel = self._ensure_task(task_id)
        attempt = self._current_attempts.pop(task_id, None)
        if attempt:
            attempt.ended_at = datetime.now(timezone.utc).isoformat()
            attempt.success = success
            attempt.error_message = error_message
            # Calculate wall clock from ISO timestamps
            try:
                start_dt = datetime.fromisoformat(attempt.started_at)
                end_dt = datetime.fromisoformat(attempt.ended_at)
                attempt.wall_clock_seconds = (end_dt - start_dt).total_seconds()
            except Exception:
                pass
            task_tel.attempts.append(asdict(attempt))

        if error_message:
            task_tel.error_messages.append(error_message)

        if success:
            task_tel.final_status = "completed"
        task_tel.ended_at = datetime.now(timezone.utc).isoformat()

        # Update wall clock
        if task_tel.started_at:
            try:
                start_dt = datetime.fromisoformat(task_tel.started_at)
                end_dt = datetime.fromisoformat(task_tel.ended_at)
                task_tel.wall_clock_seconds = (end_dt - start_dt).total_seconds()
            except Exception:
                pass

        self._persist()

    def record_verification(
        self,
        task_id: str,
        passed: bool,
        message: str,
    ) -> None:
        """Record a verification result."""
        task_tel = self._ensure_task(task_id)
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "message": message,
        }
        task_tel.verification_results.append(result)

        # Also update current attempt if one is active
        attempt = self._current_attempts.get(task_id)
        if attempt:
            attempt.verification_passed = passed
            attempt.verification_message = message

        self._persist()

    def record_debug(
        self,
        task_id: str,
        debug_attempt: int,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a debug attempt result."""
        task_tel = self._ensure_task(task_id)
        debug_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "debug_attempt": debug_attempt,
            "success": success,
            "error_message": error_message,
        }
        task_tel.attempts.append({
            "type": "debug",
            **debug_record,
        })
        if error_message:
            task_tel.error_messages.append(error_message)
        self._persist()

    def record_escalation(
        self,
        task_id: str,
        from_model: str,
        to_model: str,
        reason: str,
    ) -> None:
        """Record a model escalation event."""
        task_tel = self._ensure_task(task_id)
        escalation = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from_model": from_model,
            "to_model": to_model,
            "reason": reason,
        }
        task_tel.escalations.append(escalation)
        self._persist()

    def record_stall(
        self,
        task_id: str,
        stall_duration_seconds: float,
    ) -> None:
        """Record a stall detection event."""
        task_tel = self._ensure_task(task_id)
        attempt = self._current_attempts.get(task_id)
        if attempt:
            attempt.stall_detected = True
        task_tel.error_messages.append(
            f"Stall detected: no file modifications for {stall_duration_seconds:.0f}s"
        )
        self._persist()

    def set_task_final_status(self, task_id: str, status: str) -> None:
        """Set the final status for a task."""
        task_tel = self._ensure_task(task_id)
        task_tel.final_status = status
        task_tel.ended_at = datetime.now(timezone.utc).isoformat()
        self._persist()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the run."""
        tasks_completed = sum(1 for t in self.tasks.values() if t.final_status == "completed")
        tasks_failed = sum(1 for t in self.tasks.values() if t.final_status and t.final_status != "completed")
        total_attempts = sum(t.total_attempts for t in self.tasks.values())
        total_debug = sum(t.debug_attempts for t in self.tasks.values())
        wall_clock = (self.end_time - self.start_time) if self.start_time and self.end_time else 0.0

        return {
            "run_id": self.run_id,
            "started_at": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat() if self.start_time else None,
            "ended_at": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "wall_clock_seconds": wall_clock,
            "tasks_completed": tasks_completed,
            "tasks_failed": tasks_failed,
            "total_tasks": len(self.tasks),
            "total_attempts": total_attempts,
            "total_debug_attempts": total_debug,
            "total_iterations": self.total_iterations,
            "tasks": {
                tid: asdict(ttel) for tid, ttel in self.tasks.items()
            },
        }

    def _persist(self) -> None:
        """Persist telemetry to disk."""
        try:
            self._telemetry_dir.mkdir(parents=True, exist_ok=True)
            data = self.get_summary()
            output_path = self._telemetry_dir / f"{self.run_id}.json"
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception:
            # Telemetry persistence should never crash the main workflow
            pass

    @staticmethod
    def load(telemetry_path: Path) -> dict[str, Any]:
        """Load telemetry data from a JSON file."""
        with open(telemetry_path, "r") as f:
            return json.load(f)

    @staticmethod
    def list_runs(workspace: Path) -> list[Path]:
        """List all telemetry run files in a workspace, newest first."""
        telemetry_dir = Path(workspace) / ".bob" / "telemetry"
        if not telemetry_dir.exists():
            return []
        runs = sorted(telemetry_dir.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return runs
