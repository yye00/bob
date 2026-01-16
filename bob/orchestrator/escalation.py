"""
Escalation Controller for BOB Framework
========================================

Manages model escalation (sonnet -> opus) and triggers root cause analysis
when tasks fail repeatedly despite dependencies being met.

Adapted from autonomous-coding/escalation.py to use BOB's database instead
of JSON files. The core escalation logic is preserved to maintain proven behavior.

Escalation Flow:
1. Task fails with Sonnet (3 attempts) -> Escalate to Opus
2. Task fails with Opus (3 attempts) -> Trigger Root Cause Analysis
3. Root cause analysis determines action:
   - too_big: Decompose task into sub-tasks
   - missing_info: Research mode (web search, experimentation)
   - wrong_infra: Stop and request user intervention
   - bad_assumptions: Research and restructure task
   - needs_research: Research mode with specific queries
"""

import json
from datetime import datetime
from typing import Optional

from bob.database.manager import DatabaseManager
from bob.models.base import EscalationAction, FailureType, ModelTier, Task


# Thresholds for escalation (matching autonomous-coding)
MAX_ATTEMPTS_PER_MODEL = 3  # Attempts before escalating to next model
MAX_DIAGNOSIS_ATTEMPTS = 2  # Times to retry after diagnosis before giving up

# Model names for each tier
MODEL_NAMES = {
    ModelTier.TIER1: "claude-sonnet-4-5-20250929",
    ModelTier.SONNET: "claude-sonnet-4-5-20250929",
    ModelTier.TIER2: "claude-opus-4-5-20251101",
    ModelTier.OPUS: "claude-opus-4-5-20251101",
}


class EscalationController:
    """
    Controls model escalation and failure handling for tasks.

    Uses BOB's database to persist escalation state instead of JSON files.
    Preserves the proven escalation logic from autonomous-coding.
    """

    def __init__(self, db_manager: DatabaseManager, project_id: str):
        """Initialize the escalation controller.

        Args:
            db_manager: Database manager for persistence
            project_id: ID of the project being managed
        """
        self.db = db_manager
        self.project_id = project_id

    def record_attempt(
        self,
        task_id: str,
        success: bool,
        error_msg: Optional[str] = None,
        error_type: Optional[str] = None,
        deps_met: bool = True,
    ) -> None:
        """
        Record an attempt to implement a task.

        Args:
            task_id: The task being attempted
            success: Whether the attempt succeeded
            error_msg: Error message if failed
            error_type: Classified error type if known
            deps_met: Whether dependencies were met for this attempt
        """
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Get or create error history from research_findings
        error_history = task.research_findings.get("error_history", [])

        if success:
            # Reset escalation state on success
            # Clear error history on success
            research_findings = task.research_findings.copy()
            research_findings["error_history"] = []

            # Use direct SQL to set failure_type to NULL
            import json
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    UPDATE tasks
                    SET attempts = 0,
                        failure_type = NULL,
                        research_findings = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(research_findings), task_id),
                )
        else:
            if not deps_met:
                # Don't count against escalation if deps not met
                self.db.update_task(task_id, failure_type=FailureType.DEPS_NOT_MET)
            else:
                # Increment attempts and record error
                new_attempts = task.attempts + 1
                error_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "model": task.current_model,
                    "error_msg": error_msg,
                    "error_type": error_type,
                    "deps_met": deps_met,
                })

                research_findings = task.research_findings.copy()
                research_findings["error_history"] = error_history

                self.db.update_task(
                    task_id,
                    attempts=new_attempts,
                    research_findings=research_findings,
                )

    def get_next_action(self, task_id: str, deps_met: bool = True) -> tuple[EscalationAction, dict]:
        """
        Determine the next action for a task based on its escalation state.

        Args:
            task_id: The task to check
            deps_met: Whether dependencies are currently met

        Returns:
            (action, context) where context contains relevant data for the action
        """
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        context: dict = {
            "task_id": task_id,
            "spec_id": task.spec_id,
            "current_model": task.current_model,
        }

        # If deps not met, skip
        if not deps_met:
            return EscalationAction.SKIP, {"reason": "dependencies_not_met"}

        # If already decomposed, don't process parent task
        if task.research_findings.get("decomposed", False):
            return EscalationAction.SKIP, {
                "reason": "decomposed",
                "sub_tasks": task.research_findings.get("sub_tasks", []),
            }

        # Determine attempts at current model tier
        # The original code tracks attempts_at_current_model separately
        # We'll use the current_model field to determine this
        attempts_at_current_tier = task.attempts

        # Check if we need to escalate model
        if attempts_at_current_tier >= MAX_ATTEMPTS_PER_MODEL:
            # Get current tier from escalation_tier field
            current_tier = task.escalation_tier

            if current_tier == ModelTier.TIER1 or current_tier == ModelTier.SONNET:
                # Escalate to Opus
                return EscalationAction.ESCALATE_MODEL, {
                    "from_model": MODEL_NAMES[ModelTier.SONNET],
                    "to_model": MODEL_NAMES[ModelTier.OPUS],
                    "attempts": attempts_at_current_tier,
                }
            elif (current_tier == ModelTier.TIER2 or current_tier == ModelTier.OPUS):
                diagnosis_done = task.research_findings.get("diagnosis_done", False)

                if not diagnosis_done:
                    # Opus also failed - need diagnosis
                    error_history = task.research_findings.get("error_history", [])
                    return EscalationAction.DIAGNOSE, {
                        "total_attempts": task.attempts,
                        "error_history": error_history[-5:],  # Last 5 errors
                    }
                else:
                    # Already diagnosed, take action based on failure type
                    return self._get_post_diagnosis_action(task)

        # Continue with current model
        return EscalationAction.CONTINUE, context

    def _get_post_diagnosis_action(self, task: Task) -> tuple[EscalationAction, dict]:
        """Determine action after diagnosis has been performed."""
        failure_type = task.failure_type or FailureType.UNKNOWN

        if failure_type == FailureType.TOO_BIG:
            return EscalationAction.DECOMPOSE, {
                "task_id": task.id,
                "spec_id": task.spec_id,
                "reason": "Task is too complex for atomic implementation",
            }
        elif failure_type == FailureType.MISSING_INFO:
            return EscalationAction.RESEARCH, {
                "task_id": task.id,
                "spec_id": task.spec_id,
                "queries": task.research_queries,
                "reason": "Missing information needs to be researched",
            }
        elif failure_type == FailureType.WRONG_INFRA:
            error_history = task.research_findings.get("error_history", [])
            return EscalationAction.REQUEST_USER, {
                "task_id": task.id,
                "spec_id": task.spec_id,
                "reason": "Missing infrastructure or packages that require user action",
                "error_history": error_history[-3:],
            }
        elif failure_type == FailureType.BAD_ASSUMPTIONS:
            return EscalationAction.RESTRUCTURE, {
                "task_id": task.id,
                "spec_id": task.spec_id,
                "reason": "Fundamental assumptions are incorrect, need research",
            }
        elif failure_type == FailureType.NEEDS_RESEARCH:
            return EscalationAction.RESEARCH, {
                "task_id": task.id,
                "spec_id": task.spec_id,
                "queries": task.research_queries,
                "reason": "Specific research needed to solve the problem",
            }
        else:
            # Unknown failure, request user help
            error_history = task.research_findings.get("error_history", [])
            return EscalationAction.REQUEST_USER, {
                "task_id": task.id,
                "spec_id": task.spec_id,
                "reason": "Unable to determine root cause",
                "error_history": error_history[-3:],
            }

    def escalate_model(self, task_id: str) -> ModelTier:
        """
        Escalate to the next model tier.

        Returns the new model tier.
        """
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        current_tier = task.escalation_tier

        if current_tier == ModelTier.TIER1 or current_tier == ModelTier.SONNET:
            # Escalate to Opus
            self.db.update_task(
                task_id,
                escalation_tier=ModelTier.OPUS,
                current_model=MODEL_NAMES[ModelTier.OPUS],
                attempts=0,  # Reset attempts at new tier
            )
            return ModelTier.OPUS

        # Already at highest tier
        return current_tier

    def record_diagnosis(
        self,
        task_id: str,
        failure_type: FailureType,
        research_queries: Optional[list[str]] = None,
    ) -> None:
        """
        Record the result of a diagnosis.

        Args:
            task_id: The task that was diagnosed
            failure_type: The classified failure type
            research_queries: Optional queries for research mode
        """
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        research_findings = task.research_findings.copy()
        research_findings["diagnosis_done"] = True

        # Update execution state
        self.db.update_task(
            task_id,
            failure_type=failure_type,
            research_findings=research_findings,
        )

        # Update research queries if provided (spec field)
        if research_queries:
            self.db.update_task_spec(task_id, research_queries=research_queries)

    def record_decomposition(self, task_id: str, sub_task_ids: list[str]) -> None:
        """
        Record that a task has been decomposed.

        Args:
            task_id: The parent task that was decomposed
            sub_task_ids: IDs of the new sub-tasks
        """
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        research_findings = task.research_findings.copy()
        research_findings["decomposed"] = True
        research_findings["sub_tasks"] = sub_task_ids

        self.db.update_task(task_id, research_findings=research_findings)

    def reset_task(self, task_id: str) -> None:
        """Reset escalation state for a task."""
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        research_findings = task.research_findings.copy()
        # Clear escalation-related fields
        research_findings.pop("error_history", None)
        research_findings.pop("diagnosis_done", None)
        research_findings.pop("decomposed", None)
        research_findings.pop("sub_tasks", None)

        # Update task with reset values
        # Note: update_task doesn't handle setting fields to NULL,
        # so we need to do a direct SQL update for failure_type
        import json
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET attempts = ?,
                    escalation_tier = ?,
                    current_model = ?,
                    failure_type = NULL,
                    research_findings = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    0,
                    ModelTier.SONNET.value,
                    MODEL_NAMES[ModelTier.SONNET],
                    json.dumps(research_findings),
                    task_id,
                ),
            )

    def reset_all(self, project_id: Optional[str] = None) -> None:
        """Reset all escalation state for a project.

        Args:
            project_id: Project ID to reset. If None, uses controller's project_id.
        """
        pid = project_id or self.project_id
        tasks = self.db.list_tasks(pid)

        for task in tasks:
            self.reset_task(task.id)

    def get_model_for_task(self, task_id: str) -> str:
        """Get the current model to use for a task."""
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        return task.current_model

    def get_escalation_summary(self) -> dict:
        """Get a summary of escalation state across all tasks in the project."""
        tasks = self.db.list_tasks(self.project_id)

        sonnet_count = 0
        opus_count = 0
        diagnosed_count = 0
        decomposed_count = 0
        stuck_count = 0

        for task in tasks:
            if task.research_findings.get("decomposed", False):
                decomposed_count += 1
            elif task.escalation_tier == ModelTier.TIER1 or task.escalation_tier == ModelTier.SONNET:
                sonnet_count += 1
            elif task.escalation_tier == ModelTier.TIER2 or task.escalation_tier == ModelTier.OPUS:
                opus_count += 1

            if task.research_findings.get("diagnosis_done", False):
                diagnosed_count += 1

            if (
                (task.escalation_tier == ModelTier.TIER2 or task.escalation_tier == ModelTier.OPUS) and
                task.attempts >= MAX_ATTEMPTS_PER_MODEL and
                task.research_findings.get("diagnosis_done", False)
            ):
                stuck_count += 1

        return {
            "tasks_at_sonnet": sonnet_count,
            "tasks_at_opus": opus_count,
            "tasks_diagnosed": diagnosed_count,
            "tasks_decomposed": decomposed_count,
            "tasks_stuck": stuck_count,
            "total_tracked": len(tasks),
        }

    def get_stuck_tasks(self) -> list[dict]:
        """Get list of tasks that are stuck after full escalation."""
        tasks = self.db.list_tasks(self.project_id)
        stuck = []

        for task in tasks:
            if (
                (task.escalation_tier == ModelTier.TIER2 or task.escalation_tier == ModelTier.OPUS) and
                task.attempts >= MAX_ATTEMPTS_PER_MODEL and
                task.research_findings.get("diagnosis_done", False)
            ):
                error_history = task.research_findings.get("error_history", [])
                stuck.append({
                    "task_id": task.id,
                    "spec_id": task.spec_id,
                    "failure_type": task.failure_type.value if task.failure_type else "unknown",
                    "total_attempts": task.attempts,
                    "research_queries": task.research_queries,
                    "last_errors": [e.get("error_msg", "") for e in error_history[-3:]],
                })

        return stuck
