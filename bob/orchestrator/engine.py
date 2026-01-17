"""
Orchestrator Engine
===================

Main orchestration engine for task execution with escalation support.

The Orchestrator coordinates the execution of tasks by:
1. Managing task lifecycle (pending -> in_progress -> completed/failed)
2. Integrating with EscalationController for model switching
3. Using FailureClassifier to analyze errors
4. Coordinating with TaskDecomposer for complex tasks
5. Leveraging ResearchController for research-first workflow
6. Handling session management and logging
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from bob.database import DatabaseManager
from bob.models.base import (
    Task,
    TaskStatus,
    ModelTier,
    FailureType,
    EscalationAction,
)
from bob.orchestrator.client import create_client, create_research_client
from bob.orchestrator.escalation import EscalationController
from bob.orchestrator.failure_classifier import classify_failure, ClassificationResult
from bob.orchestrator.task_decomposer import TaskDecomposer
from bob.orchestrator.research_controller import ResearchController
from bob.observability.cost_tracker import CostTracker
from bob.config import ConfigManager


class OrchestratorConfig:
    """Configuration for Orchestrator behavior."""

    def __init__(
        self,
        default_model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
        enable_escalation: bool = True,
        enable_research: bool = True,
        enable_decomposition: bool = True,
        max_cost_per_project: Optional[float] = None,
        max_cost_per_session: Optional[float] = None,
        warn_at_percent: int = 80,
    ):
        """
        Initialize orchestrator configuration.

        Args:
            default_model: Default Claude model to use
            max_retries: Maximum retries before escalation
            enable_escalation: Whether to enable model escalation
            enable_research: Whether to enable research mode
            enable_decomposition: Whether to enable task decomposition
            max_cost_per_project: Maximum cost per project (USD), None for no limit
            max_cost_per_session: Maximum cost per session (USD), None for no limit
            warn_at_percent: Warn when reaching this percentage of limit (0-100)
        """
        self.default_model = default_model
        self.max_retries = max_retries
        self.enable_escalation = enable_escalation
        self.enable_research = enable_research
        self.enable_decomposition = enable_decomposition
        self.max_cost_per_project = max_cost_per_project
        self.max_cost_per_session = max_cost_per_session
        self.warn_at_percent = warn_at_percent


class Orchestrator:
    """
    Main orchestration engine for executing tasks.

    Coordinates task execution, escalation, research, and decomposition.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        project_id: str,
        project_dir: Path,
        config: Optional[OrchestratorConfig] = None,
    ):
        """
        Initialize the Orchestrator.

        Args:
            db_manager: Database manager for persistence
            project_id: Project ID for tracking
            project_dir: Project directory path
            config: Optional orchestrator configuration
        """
        self.db = db_manager
        self.project_id = project_id
        self.project_dir = project_dir
        self.config = config or OrchestratorConfig()

        # Initialize controllers
        self.escalation = EscalationController(db_manager, project_id)
        self.task_decomposer = TaskDecomposer(db_manager)
        self.research_controller = ResearchController(db_manager, project_dir)
        self.cost_tracker = CostTracker(db_manager)

        # Current execution state
        self.current_task: Optional[Task] = None
        self.current_model: str = self.config.default_model
        self.session_id: Optional[str] = None

    def check_project_cost_limit(self) -> tuple[bool, Optional[str]]:
        """
        Check if project cost is within limits.

        Returns:
            Tuple of (can_continue, message)
            can_continue is False if limit exceeded
            message describes the budget status
        """
        if self.config.max_cost_per_project is None:
            return True, None

        # Get current project costs (use stored cost for accurate limit checking)
        try:
            summary = self.cost_tracker.get_project_costs(self.project_id, use_stored_cost=True)
            current_cost = summary.total_cost
        except ValueError:
            # Project not found or no costs yet
            return True, None

        limit = self.config.max_cost_per_project
        percentage = (current_cost / limit) * 100 if limit > 0 else 0

        # Check if limit exceeded
        if current_cost >= limit:
            return False, (
                f"Project cost limit exceeded: ${current_cost:.4f} >= ${limit:.2f} "
                f"({percentage:.1f}% of budget used)"
            )

        # Check if warning threshold reached
        if percentage >= self.config.warn_at_percent:
            return True, (
                f"Warning: Approaching project cost limit - ${current_cost:.4f} / ${limit:.2f} "
                f"({percentage:.1f}% of budget used)"
            )

        return True, None

    def check_session_cost_limit(self, session_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if session cost is within limits.

        Args:
            session_id: Session ID to check

        Returns:
            Tuple of (can_continue, message)
            can_continue is False if limit exceeded
            message describes the budget status
        """
        if self.config.max_cost_per_session is None:
            return True, None

        # Get current session costs (use stored cost for accurate limit checking)
        session_cost = self.cost_tracker.get_session_cost(session_id, use_stored_cost=True)
        if not session_cost:
            return True, None

        current_cost = session_cost.cost.total_cost
        limit = self.config.max_cost_per_session
        percentage = (current_cost / limit) * 100 if limit > 0 else 0

        # Check if limit exceeded
        if current_cost >= limit:
            return False, (
                f"Session cost limit exceeded: ${current_cost:.4f} >= ${limit:.2f} "
                f"({percentage:.1f}% of budget used)"
            )

        # Check if warning threshold reached
        if percentage >= self.config.warn_at_percent:
            return True, (
                f"Warning: Approaching session cost limit - ${current_cost:.4f} / ${limit:.2f} "
                f"({percentage:.1f}% of budget used)"
            )

        return True, None

    async def execute_task(
        self,
        task: Task,
        prompt: str,
    ) -> tuple[TaskStatus, Optional[str]]:
        """
        Execute a single task with full orchestration support.

        This method:
        1. Checks cost limits before starting
        2. Updates task status to in_progress
        3. Creates appropriate client based on task needs
        4. Executes the task with the Claude SDK
        5. Handles failures with classification and escalation
        6. Updates task status based on result
        7. Returns final status and any error message

        Args:
            task: Task to execute
            prompt: Prompt to send to the agent

        Returns:
            Tuple of (final_status, error_message)
            error_message is None if successful
        """
        self.current_task = task

        # Check project cost limit before starting
        can_continue, budget_msg = self.check_project_cost_limit()
        if not can_continue:
            # Cost limit exceeded - block the task
            self.db.update_task(task.id, status=TaskStatus.BLOCKED)
            return TaskStatus.BLOCKED, budget_msg

        # Display warning if approaching limit
        if budget_msg:
            # In a real implementation, this would log or display to user
            # For now, we just note it (tests can check this via cost_tracker)
            pass

        # Check session cost limit if we have a session
        if self.session_id:
            can_continue, session_msg = self.check_session_cost_limit(self.session_id)
            if not can_continue:
                # Session cost limit exceeded - block the task
                self.db.update_task(task.id, status=TaskStatus.BLOCKED)
                return TaskStatus.BLOCKED, session_msg

            if session_msg:
                # Display warning
                pass

        # Update task to in_progress
        # Note: attempts will be incremented by record_attempt in escalation controller
        self.db.update_task(task.id, status=TaskStatus.IN_PROGRESS)

        try:
            # Determine if research is needed
            needs_research = (
                task.research_required
                and not task.research_complete
                and self.config.enable_research
            )

            # Create appropriate client
            if needs_research:
                client = create_research_client(
                    project_dir=self.project_dir,
                    model=self.current_model,
                )
            else:
                client = create_client(
                    project_dir=self.project_dir,
                    model=self.current_model,
                    enable_research=False,
                )

            # Execute task (placeholder - real execution would use Claude SDK)
            # In a real implementation, this would:
            # - Send prompt to client
            # - Stream responses
            # - Capture tool use
            # - Detect completion/failure
            success, error = await self._execute_with_client(client, prompt)

            if success:
                # Task succeeded - record success in escalation controller
                self.escalation.record_attempt(
                    task_id=task.id,
                    success=True,
                    deps_met=True,  # TODO: Check actual dependencies
                )
                # Update task status to completed
                self.db.update_task(task.id, status=TaskStatus.COMPLETED)
                return TaskStatus.COMPLETED, None

            else:
                # Task failed - classify and decide action
                return await self._handle_failure(task, error)

        except Exception as e:
            # Unexpected error during execution
            error_msg = f"Unexpected error: {str(e)}"
            return await self._handle_failure(task, error_msg)

    async def _execute_with_client(
        self,
        client: Any,
        prompt: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Execute task with Claude SDK client.

        Args:
            client: Claude SDK client
            prompt: Prompt to send

        Returns:
            Tuple of (success, error_message)
        """
        # Placeholder for actual Claude SDK execution
        # In a real implementation, this would:
        # 1. await client.query(prompt)
        # 2. async for msg in client.receive_response(): ...
        # 3. Check for success indicators in response
        # 4. Return (True, None) on success or (False, error) on failure

        # For now, return a placeholder
        return True, None

    async def _handle_failure(
        self,
        task: Task,
        error: str,
    ) -> tuple[TaskStatus, Optional[str]]:
        """
        Handle task failure with classification and escalation.

        Args:
            task: Failed task
            error: Error message

        Returns:
            Tuple of (final_status, error_message)
        """
        # Build error history from task state for classification
        error_history = [{
            "timestamp": datetime.now().isoformat(),
            "model": self.current_model,
            "error": error,
            "attempt": task.attempts,
        }]

        # Classify the failure
        classification = classify_failure(
            task=task,
            error_history=error_history,
            deps_status={},  # TODO: Get actual dependencies status
        )

        # Record the attempt in escalation controller
        self.escalation.record_attempt(
            task_id=task.id,
            success=False,
            error_msg=error,
            error_type=classification.failure_type.value if classification.failure_type else None,
            deps_met=True,  # TODO: Check actual dependencies
        )

        # Reload task to get updated attempts count
        task = self.db.get_task(task.id)
        # Update failure type
        self.db.update_task(task.id, failure_type=classification.failure_type)

        # Determine escalation action
        if self.config.enable_escalation:
            action, context = self.escalation.get_next_action(
                task_id=task.id,
                deps_met=True,  # TODO: Check actual dependencies
            )
        else:
            # Without escalation, just mark as failed after max retries
            if task.attempts >= self.config.max_retries:
                action = EscalationAction.REQUEST_USER
            else:
                action = EscalationAction.CONTINUE

        # Execute escalation action
        return await self._execute_escalation_action(task, action, classification)

    async def _execute_escalation_action(
        self,
        task: Task,
        action: EscalationAction,
        classification: ClassificationResult,
    ) -> tuple[TaskStatus, Optional[str]]:
        """
        Execute the determined escalation action.

        Args:
            task: Task being escalated
            action: Escalation action to take
            classification: Failure classification

        Returns:
            Tuple of (final_status, error_message)
        """
        if action == EscalationAction.CONTINUE:
            # Retry with same model
            self.db.update_task(task.id, status=TaskStatus.PENDING)
            return TaskStatus.PENDING, "Retrying"

        elif action == EscalationAction.ESCALATE_MODEL:
            # Escalate to more powerful model
            new_tier = self.escalation.escalate_model(task.id)
            # Reload task to get updated model info
            task = self.db.get_task(task.id)
            self.current_model = task.current_model
            # Status is already set to PENDING by escalate_model, update it explicitly
            self.db.update_task(task.id, status=TaskStatus.PENDING)
            return TaskStatus.PENDING, "Escalated to better model"

        elif action == EscalationAction.RESEARCH:
            # Needs research before continuing
            self.db.update_task(
                task.id,
                research_required=True,
                research_complete=False,
                status=TaskStatus.PENDING
            )
            return TaskStatus.PENDING, "Needs research"

        elif action == EscalationAction.DECOMPOSE:
            # Decompose into subtasks
            if self.config.enable_decomposition:
                subtasks = await self._decompose_task(task)
                if subtasks:
                    # Note: Task doesn't have sub_task_ids field, handle via research_findings
                    self.db.update_task(task.id, status=TaskStatus.DECOMPOSED)
                    return TaskStatus.DECOMPOSED, f"Decomposed into {len(subtasks)} subtasks"

            # If decomposition fails or disabled, request user help
            self.db.update_task(task.id, status=TaskStatus.FAILED)
            return TaskStatus.FAILED, "Decomposition needed but unavailable"

        elif action == EscalationAction.REQUEST_USER:
            # Needs user intervention
            self.db.update_task(task.id, status=TaskStatus.BLOCKED)
            return TaskStatus.BLOCKED, "Requires user intervention"

        else:
            # Unknown action - mark as failed
            self.db.update_task(task.id, status=TaskStatus.FAILED)
            return TaskStatus.FAILED, f"Unknown escalation action: {action}"

    async def _decompose_task(self, task: Task) -> list[Task]:
        """
        Decompose a complex task into subtasks.

        Args:
            task: Task to decompose

        Returns:
            List of subtasks
        """
        # Use task decomposer to break down the task
        # This is a placeholder - real implementation would:
        # 1. Use TaskDecomposer.analyze_task_for_decomposition
        # 2. Generate decomposition prompt
        # 3. Send to Claude for subtask generation
        # 4. Validate decomposition
        # 5. Create and persist subtasks

        return []

    def _get_model_for_tier(self, tier: Any) -> str:
        """
        Get model name for a given tier.

        Args:
            tier: Model tier (ModelTier enum or string)

        Returns:
            Model name string
        """
        if tier == ModelTier.SONNET or tier == "tier1":
            return "claude-sonnet-4-20250514"
        elif tier == ModelTier.OPUS or tier == "tier2":
            return "claude-opus-4-20250514"
        else:
            return self.config.default_model

    def get_execution_summary(self) -> dict[str, Any]:
        """
        Get summary of current execution state.

        Returns:
            Dictionary with execution statistics
        """
        return {
            "current_task_id": self.current_task.id if self.current_task else None,
            "current_model": self.current_model,
            "session_id": self.session_id,
            "config": {
                "default_model": self.config.default_model,
                "max_retries": self.config.max_retries,
                "escalation_enabled": self.config.enable_escalation,
                "research_enabled": self.config.enable_research,
                "decomposition_enabled": self.config.enable_decomposition,
            },
        }


def create_orchestrator(
    db_manager: DatabaseManager,
    project_id: str,
    project_dir: Path,
    config: Optional[OrchestratorConfig] = None,
) -> Orchestrator:
    """
    Create an Orchestrator instance.

    Args:
        db_manager: Database manager
        project_id: Project ID
        project_dir: Project directory
        config: Optional configuration

    Returns:
        Configured Orchestrator
    """
    return Orchestrator(
        db_manager=db_manager,
        project_id=project_id,
        project_dir=project_dir,
        config=config,
    )
