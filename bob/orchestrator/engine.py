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
import os
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
from bob.orchestrator.claude_executor import ClaudeExecutor, execute_task_with_claude

# SDK executor — preferred, falls back to CLI if SDK unavailable
try:
    from bob.orchestrator.claude_sdk_executor import execute_task_with_sdk
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
from bob.orchestrator.escalation import EscalationController
from bob.orchestrator.failure_classifier import classify_failure, ClassificationResult
from bob.orchestrator.task_decomposer import TaskDecomposer
from bob.orchestrator.research_controller import ResearchController
from bob.observability.cost_tracker import CostTracker
from bob.observability.logger import EventType, LogContext, create_logger
from bob.observability.telemetry import RunTelemetry
from bob.orchestrator.debug_journal import DebugJournal
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
        non_interactive: bool = False,
        use_opus_default: bool = False,
        enable_thinking: bool = False,
        thinking_budget: int = 10000,
        max_debug_attempts: int = 3,
        stall_timeout: int = 600,
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
            non_interactive: Whether to run in non-interactive mode (disable TUI, auto-select defaults)
            max_debug_attempts: Maximum debug attempts per verification failure (default: 3)
            stall_timeout: Seconds without file modifications before killing process (default: 600)
        """
        self.default_model = default_model
        self.max_retries = max_retries
        self.enable_escalation = enable_escalation
        self.enable_research = enable_research
        self.enable_decomposition = enable_decomposition
        self.max_cost_per_project = max_cost_per_project
        self.max_cost_per_session = max_cost_per_session
        self.warn_at_percent = warn_at_percent
        self.non_interactive = non_interactive
        self.use_opus_default = use_opus_default
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
        self.max_debug_attempts = max_debug_attempts
        self.stall_timeout = stall_timeout

        # If use_opus_default, override the default model
        if use_opus_default:
            self.default_model = "claude-opus-4-5-20251101"


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

        # Initialize telemetry
        self.telemetry = RunTelemetry(workspace=project_dir)

        # Initialize structured logger (JSON logs → .bob/logs/)
        self.logger = create_logger("orchestrator", project_workspace=Path(project_dir))
        self.logger.set_context(project_id=project_id)

        # Initialize debug journal (MemGPT-style on-disk debug history)
        self.debug_journal = DebugJournal(project_dir)

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

    def _cleanup_task_debug(self, task: Task) -> None:
        """Clean up debug journal for a completed task.
        
        Called automatically when a task completes successfully.
        The journal has already been marked RESOLVED, so we can
        safely remove it to prevent accumulation.
        """
        if self.debug_journal.has_journal(task.spec_id):
            self.debug_journal.clear_journal(task.spec_id)

    def _check_dependencies(self, task: Task) -> tuple[bool, dict[str, str]]:
        """
        Check if all dependencies for a task are met.

        Args:
            task: Task to check dependencies for

        Returns:
            Tuple of (deps_met, deps_status)
            deps_met is True if all dependencies are COMPLETED
            deps_status is a dict mapping spec_id to status string
        """
        if not task.depends_on:
            # No dependencies - all met
            return True, {}

        deps_status = {}
        deps_met = True

        for dep_spec_id in task.depends_on:
            try:
                dep_task = self.db.get_task_by_spec_id(self.project_id, dep_spec_id)
                if dep_task:
                    deps_status[dep_spec_id] = dep_task.status.value
                    if dep_task.status != TaskStatus.COMPLETED:
                        deps_met = False
                else:
                    # Dependency task not found
                    deps_status[dep_spec_id] = "not_found"
                    deps_met = False
            except Exception:
                # Error fetching dependency
                deps_status[dep_spec_id] = "error"
                deps_met = False

        return deps_met, deps_status

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
        self.logger.set_context(task_id=task.id, model=self.current_model)

        # Start telemetry for this task
        self.telemetry.start_task_attempt(
            task_id=task.id,
            spec_id=task.spec_id,
            title=task.title,
            model=self.current_model,
        )
        self.logger.info(
            f"Starting task {task.spec_id}: {task.title}",
            event_type=EventType.TASK_STARTED,
            model=self.current_model,
        )

        # Check project cost limit before starting
        can_continue, budget_msg = self.check_project_cost_limit()
        if not can_continue:
            # Cost limit exceeded - block the task
            self.db.update_task(task.id, status=TaskStatus.BLOCKED)
            self.telemetry.end_task_attempt(task.id, success=False, error_message=budget_msg)
            self.telemetry.set_task_final_status(task.id, "blocked")
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
                self.telemetry.end_task_attempt(task.id, success=False, error_message=session_msg)
                self.telemetry.set_task_final_status(task.id, "blocked")
                return TaskStatus.BLOCKED, session_msg

            if session_msg:
                # Display warning
                pass

        # Update task to in_progress
        # Note: attempts will be incremented by record_attempt in escalation controller
        self.db.update_task(task.id, status=TaskStatus.IN_PROGRESS)

        try:
            # Execute task using Claude CLI executor
            # Note: The CLI executor handles all Claude interactions directly
            # via pexpect/subprocess. The SDK client is not needed.
            success, error = await self._execute_with_client(None, prompt)

            if success:
                # Verify outputs before claiming victory
                from bob.orchestrator.verifier import verify_task_outputs
                verified, verify_msg = verify_task_outputs(task, self.project_dir)

                self.telemetry.record_verification(task.id, verified, verify_msg)
                if verified:
                    self.logger.info(
                        f"Verification passed for {task.spec_id}",
                        event_type=EventType.VERIFICATION_PASSED,
                    )
                else:
                    self.logger.warning(
                        f"Verification failed for {task.spec_id}: {verify_msg[:200]}",
                        event_type=EventType.VERIFICATION_FAILED,
                    )

                if not verified:
                    # === MULTI-DEBUG LOOP (MemGPT-style) ===
                    # Instead of stuffing all error history into the prompt (which
                    # eats the context window), we:
                    # 1. Store full debug history in a journal file on disk
                    # 2. Inject only a compact summary into the debug prompt
                    # 3. Tell Claude where the journal is so it can read on-demand
                    max_debug = self.config.max_debug_attempts
                    print(f"\n🔍 Verification failed for {task.spec_id}:")
                    print(verify_msg)
                    print(f"\n🐛 Entering debug mode (up to {max_debug} attempts)...")
                    self.logger.info(
                        f"Entering debug mode for {task.spec_id} (up to {max_debug} attempts)",
                        event_type=EventType.DEBUG_MODE_ENTERED,
                        max_debug_attempts=max_debug,
                    )

                    # Record first failure to journal
                    self.debug_journal.record_attempt(
                        spec_id=task.spec_id,
                        task_title=task.title,
                        attempt_number=0,
                        verification_error=verify_msg,
                        approach_taken="Initial implementation",
                    )

                    debug_succeeded = False

                    for debug_attempt in range(max_debug):
                        print(f"\n🔧 Debug attempt {debug_attempt + 1}/{max_debug}...")

                        self.telemetry.start_task_attempt(
                            task_id=task.id,
                            spec_id=task.spec_id,
                            title=task.title,
                            model=self.current_model,
                            is_debug=True,
                            debug_attempt_number=debug_attempt + 1,
                        )

                        # Build a LEAN debug prompt using journal summary
                        # (not full error history — Claude can read the journal file)
                        debug_prompt = self._build_debug_prompt(
                            task, prompt, verify_msg, debug_attempt
                        )
                        debug_success, debug_error = await self._execute_with_client(None, debug_prompt)

                        if debug_success:
                            # Re-verify after debug attempt
                            verified2, verify_msg2 = verify_task_outputs(task, self.project_dir)
                            self.telemetry.record_verification(task.id, verified2, verify_msg2)

                            if verified2:
                                print(f"\n✅ Debug fix worked on attempt {debug_attempt + 1}! Verification passed for {task.spec_id}")
                                self.logger.info(
                                    f"Debug fix worked on attempt {debug_attempt + 1} for {task.spec_id}",
                                    event_type=EventType.DEBUG_MODE_SUCCEEDED,
                                    debug_attempt=debug_attempt + 1,
                                )
                                self.debug_journal.record_success(task.spec_id, debug_attempt + 1)
                                self.telemetry.record_debug(task.id, debug_attempt + 1, success=True)
                                self.telemetry.end_task_attempt(task.id, success=True)
                                debug_succeeded = True
                                break
                            else:
                                # Debug didn't fix it — record to journal, continue
                                print(f"\n🔍 Debug attempt {debug_attempt + 1} didn't fix verification:")
                                print(verify_msg2)
                                self.debug_journal.record_attempt(
                                    spec_id=task.spec_id,
                                    task_title=task.title,
                                    attempt_number=debug_attempt + 1,
                                    verification_error=verify_msg2,
                                )
                                verify_msg = verify_msg2  # Update for next iteration
                                self.telemetry.record_debug(
                                    task.id, debug_attempt + 1, success=False,
                                    error_message=verify_msg2,
                                )
                                self.telemetry.end_task_attempt(
                                    task.id, success=False, error_message=verify_msg2,
                                )
                        else:
                            # Debug execution itself failed
                            error_detail = f"Debug execution failed: {debug_error}"
                            self.debug_journal.record_attempt(
                                spec_id=task.spec_id,
                                task_title=task.title,
                                attempt_number=debug_attempt + 1,
                                verification_error=error_detail,
                                approach_taken="Debug execution crashed",
                            )
                            self.telemetry.record_debug(
                                task.id, debug_attempt + 1, success=False,
                                error_message=error_detail,
                            )
                            self.telemetry.end_task_attempt(
                                task.id, success=False, error_message=error_detail,
                            )

                    if debug_succeeded:
                        deps_met, deps_status = self._check_dependencies(task)
                        self.escalation.record_attempt(
                            task_id=task.id,
                            success=True,
                            deps_met=deps_met,
                        )
                        self.db.update_task(task.id, status=TaskStatus.COMPLETED)
                        self._cleanup_task_debug(task)  # Remove journal after success
                        self.telemetry.set_task_final_status(task.id, "completed")
                        return TaskStatus.COMPLETED, None
                    else:
                        # All debug attempts exhausted — escalate
                        error_msg = (
                            f"Verification failed after {max_debug} debug attempts.\n"
                            f"Error history:\n" + "\n---\n".join(previous_errors)
                        )
                        self.telemetry.set_task_final_status(task.id, "failed")
                        return await self._handle_failure(task, error_msg)

                # Outputs verified on first try - record success
                print(f"\n✅ Verification passed for {task.spec_id}")
                self.logger.info(
                    f"Task {task.spec_id} completed successfully (first try)",
                    event_type=EventType.TASK_COMPLETED,
                )
                deps_met, deps_status = self._check_dependencies(task)
                self.escalation.record_attempt(
                    task_id=task.id,
                    success=True,
                    deps_met=deps_met,
                )
                # Update task status to completed
                self.db.update_task(task.id, status=TaskStatus.COMPLETED)
                self._cleanup_task_debug(task)  # Remove any leftover journal
                self.telemetry.end_task_attempt(task.id, success=True)
                self.telemetry.set_task_final_status(task.id, "completed")
                return TaskStatus.COMPLETED, None

            else:
                # Task failed - classify and decide action
                self.telemetry.end_task_attempt(task.id, success=False, error_message=error)
                self.telemetry.set_task_final_status(task.id, "failed")
                return await self._handle_failure(task, error)

        except Exception as e:
            # Unexpected error during execution
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(
                f"Task {task.spec_id} failed with unexpected error: {e}",
                event_type=EventType.TASK_FAILED,
                exc_info=True,
            )
            self.telemetry.end_task_attempt(task.id, success=False, error_message=error_msg)
            try:
                self.telemetry.set_task_final_status(task.id, "failed")
                return await self._handle_failure(task, error_msg)
            except Exception as inner_e:
                # Last resort: if even _handle_failure throws, ensure we
                # never leave a task stuck in IN_PROGRESS
                print(f"\n❌ CRITICAL: _handle_failure also failed for {task.spec_id}: {inner_e}")
                self.db.update_task(task.id, status=TaskStatus.FAILED)
                return TaskStatus.FAILED, f"Double fault: {error_msg} / {inner_e}"
        finally:
            # SAFETY NET: Never leave a task stuck at IN_PROGRESS.
            # If we reach this point and the task is still IN_PROGRESS,
            # something went wrong — force it to FAILED so the runner
            # doesn't spin forever.
            try:
                current = self.db.get_task(task.id)
                if current and current.status == TaskStatus.IN_PROGRESS:
                    print(f"\n⚠️  Safety net: Task {task.spec_id} still IN_PROGRESS after "
                          f"execute_task() — forcing to FAILED")
                    self.db.update_task(task.id, status=TaskStatus.FAILED)
            except Exception:
                pass  # Don't let safety net itself cause issues

    def _build_debug_prompt(
        self,
        task: Task,
        original_prompt: str,
        verify_errors: str,
        debug_attempt: int = 0,
    ) -> str:
        """
        Build a LEAN debug prompt using MemGPT-style retrieval.
        
        Instead of stuffing all debug history into the prompt (which eats
        the context window and degrades reasoning), we:
        
        1. Include ONLY the current error (what needs fixing NOW)
        2. Include a compact summary of previous attempts (~1 line each)
        3. Point Claude to the on-disk debug journal for full details
        4. List existing files (so Claude knows what to read/edit)
        5. Include the verify script (so Claude can test its fix)
        
        The original task spec is NOT duplicated here — Claude can read it
        from the spec file or the journal if needed.
        
        Target: ~500-800 tokens for the debug prompt itself (vs 3000+ before).
        """
        # List files that exist in the expected outputs
        existing_files = []
        for output in task.expected_outputs:
            file_path = self.project_dir / output.path
            if file_path.exists():
                try:
                    line_count = sum(1 for line in open(file_path) if line.strip())
                    existing_files.append(f"  - {output.path} ({line_count} lines)")
                except Exception:
                    existing_files.append(f"  - {output.path} (exists)")
        
        files_section = "\n".join(existing_files) if existing_files else "  (no files created yet)"
        
        # Include the verify_script so Claude can run it itself
        verify_section = ""
        if task.verify_script:
            verify_section = f"""
## Verify Script
```bash
{task.verify_script.strip()}
```
"""
        
        # Get compact journal summary (1 line per previous attempt)
        # Full history is on disk — Claude can read it if needed
        journal_summary = self.debug_journal.get_compact_summary(task.spec_id)
        journal_path = self.debug_journal.journal_path(task.spec_id)
        rel_journal = os.path.relpath(journal_path, self.project_dir)
        
        journal_section = ""
        if journal_summary:
            journal_section = f"""
## Debug History (compact — read `{rel_journal}` for full traces)
{journal_summary}
"""
        
        attempt_num = debug_attempt + 1
        
        debug_prompt = f"""# DEBUG MODE: Fix Verification Failures (attempt {attempt_num})

## Task: {task.title} ({task.spec_id})

Your code exists but FAILED verification. DO NOT rewrite from scratch.
READ your code, find the bug, FIX it.

## Your Files
{files_section}

## Current Error (FIX THIS)
```
{verify_errors}
```
{journal_section}
## Instructions
1. READ each file listed above
2. Find the root cause of the error
3. FIX the specific issue — edit, don't rewrite
4. Run the verify script to confirm
{verify_section}
If you need the original task requirements, they're in the task spec.
If you need full error traces from previous attempts, read: `{rel_journal}`
"""
        return debug_prompt

    def _get_workspace_inventory(self) -> str:
        """Build a file inventory of the workspace with line counts.
        
        Lists all files in the project directory (excluding hidden dirs,
        __pycache__, .git, node_modules, etc.) with their line counts.
        """
        import os
        
        skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                     '.bob', '.tox', '.mypy_cache', '.pytest_cache', '.eggs',
                     'dist', 'build', '*.egg-info'}
        
        inventory_lines = []
        try:
            for root, dirs, files in os.walk(self.project_dir):
                # Filter out skipped directories
                dirs[:] = [d for d in dirs if d not in skip_dirs and not d.endswith('.egg-info')]
                
                rel_root = os.path.relpath(root, self.project_dir)
                if rel_root == '.':
                    rel_root = ''
                
                for fname in sorted(files):
                    if fname.startswith('.'):
                        continue
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.join(rel_root, fname) if rel_root else fname
                    try:
                        line_count = sum(1 for _ in open(fpath))
                        inventory_lines.append(f"  {rel_path} ({line_count} lines)")
                    except Exception:
                        inventory_lines.append(f"  {rel_path} (binary/unreadable)")
        except Exception:
            return "  (could not scan workspace)"
        
        if not inventory_lines:
            return "  (empty workspace)"
        
        # Limit to 100 files to avoid prompt bloat
        if len(inventory_lines) > 100:
            inventory_lines = inventory_lines[:100]
            inventory_lines.append(f"  ... and {len(inventory_lines) - 100} more files")
        
        return "\n".join(inventory_lines)

    async def _execute_with_client(
        self,
        client: Any,
        prompt: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Execute task with Claude Code SDK (preferred) or CLI (fallback).

        Args:
            client: Claude SDK client (unused, kept for API compatibility)
            prompt: Prompt to send

        Returns:
            Tuple of (success, error_message)
        """
        if _SDK_AVAILABLE:
            # Use the Claude Code SDK (Python package)
            result = await execute_task_with_sdk(
                project_dir=self.project_dir,
                prompt=prompt,
                model=self.current_model,
                timeout_seconds=3600,  # 1 hour timeout
                verbose=True,  # Show tool use for monitoring
            )
        else:
            # Fallback to CLI executor
            result = await execute_task_with_claude(
                project_dir=self.project_dir,
                prompt=prompt,
                model=self.current_model,
                timeout_seconds=3600,
                non_interactive=self.config.non_interactive,
                enable_thinking=self.config.enable_thinking,
                thinking_budget=self.config.thinking_budget,
                stall_timeout=self.config.stall_timeout,
            )

        # Record stall detection if it occurred
        if result.exit_code == -2 and self.current_task:
            self.telemetry.record_stall(
                task_id=self.current_task.id,
                stall_duration_seconds=self.config.stall_timeout,
            )
            self.logger.warning(
                f"Stall detected for {self.current_task.spec_id}: "
                f"no file modifications for {self.config.stall_timeout}s",
                event_type=EventType.STALL_DETECTED,
                stall_timeout=self.config.stall_timeout,
            )

        # Record token usage in telemetry
        if result.token_usage and self.current_task:
            self.logger.info(
                f"Token usage for {self.current_task.spec_id}: "
                f"in={result.token_usage.input_tokens}, "
                f"out={result.token_usage.output_tokens}, "
                f"cache_read={result.token_usage.cache_read_tokens}, "
                f"cache_write={result.token_usage.cache_write_tokens}",
                input_tokens=result.token_usage.input_tokens,
                output_tokens=result.token_usage.output_tokens,
                cache_read_tokens=result.token_usage.cache_read_tokens,
                cache_write_tokens=result.token_usage.cache_write_tokens,
                cost_usd=result.cost_usd,
                model_used=result.model_used,
            )
            # Feed into cost tracker if we have a session
            if self.session_id:
                try:
                    from bob.observability.cost_tracker import TokenUsage
                    usage = TokenUsage(
                        input_tokens=result.token_usage.input_tokens,
                        output_tokens=result.token_usage.output_tokens,
                        cache_read_tokens=result.token_usage.cache_read_tokens,
                        cache_write_tokens=result.token_usage.cache_write_tokens,
                    )
                    self.cost_tracker.track_session(
                        session_id=self.session_id,
                        model=result.model_used or self.current_model,
                        usage=usage,
                    )
                except Exception:
                    pass  # Cost tracking should never crash execution

        if result.success:
            return True, None
        else:
            error_msg = result.error or f"Claude execution failed with exit code {result.exit_code}"
            if result.output:
                # Include last part of output for context
                output_lines = result.output.strip().split('\n')
                last_lines = '\n'.join(output_lines[-10:])
                error_msg = f"{error_msg}\n\nLast output:\n{last_lines}"
            return False, error_msg

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
        # Build FULL error history from stored state + current error.
        # Previous code only passed a single-element list, so
        # check_repeated_errors (threshold=2) could never trigger.
        stored_history = task.research_findings.get("error_history", [])
        current_error = {
            "timestamp": datetime.now().isoformat(),
            "model": self.current_model,
            "error_msg": error,  # Key must be "error_msg" for classifier
            "error": error,      # Keep both for compatibility
            "attempt": task.attempts,
        }
        error_history = stored_history + [current_error]

        # Check dependencies
        deps_met, deps_status = self._check_dependencies(task)

        # Classify the failure
        classification = classify_failure(
            task=task,
            error_history=error_history,
            deps_status=deps_status,
        )

        # Record the attempt in escalation controller
        self.escalation.record_attempt(
            task_id=task.id,
            success=False,
            error_msg=error,
            error_type=classification.failure_type.value if classification.failure_type else None,
            deps_met=deps_met,
        )

        # Reload task to get updated attempts count
        task = self.db.get_task(task.id)
        # Update failure type
        self.db.update_task(task.id, failure_type=classification.failure_type)

        # Determine escalation action
        if self.config.enable_escalation:
            action, context = self.escalation.get_next_action(
                task_id=task.id,
                deps_met=deps_met,
            )
        else:
            # Without escalation, just mark as failed after max retries
            if task.attempts >= self.config.max_retries:
                action = EscalationAction.REQUEST_USER
            else:
                action = EscalationAction.CONTINUE

        # Execute escalation action
        self.logger.info(
            f"Escalation action for {task.spec_id}: {action.value}",
            event_type=EventType.ESCALATION_TRIGGERED,
            action=action.value,
            failure_type=classification.failure_type.value if classification.failure_type else None,
            attempts=task.attempts,
        )
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

        elif action == EscalationAction.DIAGNOSE:
            # Run root cause analysis after Opus exhausts retries
            print(f"\n🔬 Running diagnosis for {task.spec_id}...")
            # Classify the failure using full error history
            error_history = task.research_findings.get("error_history", [])
            deps_met, deps_status = self._check_dependencies(task)
            from bob.orchestrator.failure_classifier import classify_failure
            diagnosis = classify_failure(
                task=task,
                error_history=error_history,
                deps_status=deps_status,
            )
            # Record the diagnosis result
            self.escalation.record_diagnosis(
                task.id,
                failure_type=diagnosis.failure_type,
                research_queries=diagnosis.research_queries if diagnosis.research_queries else None,
            )
            print(f"   Diagnosis: {diagnosis.failure_type.value} "
                  f"(confidence: {diagnosis.confidence:.0%})")
            print(f"   Reason: {diagnosis.reason}")
            # Re-evaluate now that diagnosis is recorded — this will call
            # _get_post_diagnosis_action which routes to DECOMPOSE/RESEARCH/etc.
            post_action, post_context = self.escalation.get_next_action(
                task_id=task.id, deps_met=deps_met,
            )
            if post_action != EscalationAction.DIAGNOSE:
                # Recurse into the post-diagnosis action
                return await self._execute_escalation_action(task, post_action, classification)
            # If still DIAGNOSE (shouldn't happen), fall through to REQUEST_USER
            self.db.update_task(task.id, status=TaskStatus.BLOCKED)
            return TaskStatus.BLOCKED, f"Diagnosed as {diagnosis.failure_type.value}, needs user help"

        elif action == EscalationAction.RESTRUCTURE:
            # Bad assumptions detected — needs research and restructure
            print(f"\n🔄 Restructuring {task.spec_id} — bad assumptions detected")
            self.db.update_task(
                task.id,
                research_required=True,
                research_complete=False,
                status=TaskStatus.PENDING,
            )
            return TaskStatus.PENDING, "Needs restructure via research (bad assumptions)"

        elif action == EscalationAction.SKIP:
            # Dependencies not met or task already decomposed — don't change status
            print(f"\n⏭️  Skipping {task.spec_id} — {classification.reason if hasattr(classification, 'reason') else 'deps not met or decomposed'}")
            # Don't mark as FAILED — leave current status intact
            current = self.db.get_task(task.id)
            if current and current.status == TaskStatus.IN_PROGRESS:
                # If still in_progress, move back to pending
                self.db.update_task(task.id, status=TaskStatus.PENDING)
            return current.status if current else TaskStatus.PENDING, "Skipped"

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
        import json
        from bob.orchestrator.task_decomposer import (
            generate_decomposition_prompt,
            validate_decomposition,
        )

        # Build error context from task history
        error_context = f"Task has failed {task.attempts} times."
        if task.failure_type:
            error_context += f" Failure type: {task.failure_type.value}."

        # Generate decomposition prompt
        prompt = generate_decomposition_prompt(task, error_context)

        # Execute with Claude to generate decomposition
        result = await execute_task_with_claude(
            project_dir=self.project_dir,
            prompt=prompt,
            model=self.current_model,
            timeout_seconds=600,  # 10 minute timeout for decomposition
            non_interactive=self.config.non_interactive,
        )

        if not result.success:
            # Decomposition failed
            return []

        # Read the decomposition plan
        plan_path = self.project_dir / "decomposition_plan.json"
        if not plan_path.exists():
            return []

        try:
            with open(plan_path, 'r') as f:
                plan = json.load(f)
        except Exception:
            return []

        # Extract sub-tasks and reasoning
        sub_tasks = plan.get("sub_tasks", [])
        reasoning = plan.get("reasoning", "")

        if not sub_tasks:
            return []

        # Validate decomposition
        is_valid, issues = validate_decomposition(sub_tasks, task)
        if not is_valid:
            # Invalid decomposition - return empty list
            return []

        # Use TaskDecomposer to create subtasks in database
        decomposition_result = self.task_decomposer.decompose_task(
            task_id=task.id,
            sub_tasks=sub_tasks,
            reasoning=reasoning,
        )

        if not decomposition_result.success:
            return []

        # Retrieve the created Task objects from the database
        created_tasks = []
        for sub in decomposition_result.sub_tasks:
            task_obj = self.db.get_task_by_spec_id(self.project_id, sub.spec_id)
            if task_obj:
                created_tasks.append(task_obj)

        return created_tasks

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
