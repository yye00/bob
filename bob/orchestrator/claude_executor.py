"""
Claude CLI Executor
===================

Execute tasks using the `claude` CLI (Claude Code) as a subprocess.
This provides a reliable way to run Claude without depending on the SDK.
"""

import asyncio
import subprocess
import os
import signal
import time
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Result of a Claude execution."""
    success: bool
    output: str
    error: Optional[str]
    exit_code: int
    duration_seconds: float


class ClaudeExecutor:
    """
    Execute Claude Code CLI for task completion.
    
    Uses subprocess to run `claude` with the task prompt.
    Supports both synchronous completion detection and streaming output.
    """
    
    def __init__(
        self,
        project_dir: Path,
        model: str = "claude-sonnet-4-20250514",
        timeout_seconds: int = 3600,  # 1 hour default
        on_output: Optional[Callable[[str], None]] = None,
        non_interactive: bool = False,
    ):
        """
        Initialize the executor.

        Args:
            project_dir: Working directory for claude
            model: Claude model to use
            timeout_seconds: Maximum execution time
            on_output: Optional callback for streaming output
            non_interactive: Whether to run in non-interactive mode (disable TUI, auto-select defaults)
        """
        self.project_dir = project_dir
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.on_output = on_output
        self.non_interactive = non_interactive
        self._process: Optional[subprocess.Popen] = None
        
    async def execute(self, prompt: str) -> ExecutionResult:
        """
        Execute a task with Claude Code.
        
        Args:
            prompt: The task prompt to send to Claude
            
        Returns:
            ExecutionResult with success status and output
        """
        start_time = time.time()
        
        # Build the claude command
        # Using --dangerously-skip-permissions for autonomous operation
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
        ]

        # Add --print flag for non-interactive mode (disables TUI)
        if self.non_interactive:
            cmd.append("--print")

        cmd.append(prompt)
        
        # Set up environment
        env = os.environ.copy()
        env["ANTHROPIC_MODEL"] = self.model
        
        try:
            # Start the process
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_dir),
                env=env,
            )
            
            # Collect output with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    self._process.communicate(),
                    timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                self._process.kill()
                await self._process.wait()
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Execution timed out after {self.timeout_seconds} seconds",
                    exit_code=-1,
                    duration_seconds=time.time() - start_time,
                )
            
            duration = time.time() - start_time
            exit_code = self._process.returncode
            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace")
            
            # Determine success based on exit code
            # Claude Code returns 0 on success
            success = exit_code == 0
            
            # Check for common failure patterns in output
            failure_patterns = [
                "Error:",
                "Failed to",
                "Could not",
                "Exception:",
                "Traceback (most recent call last):",
            ]
            
            if success:
                for pattern in failure_patterns:
                    if pattern in output or pattern in error_output:
                        # May have had errors but claude handled them
                        # Check if there's a completion indicator
                        if "✓" in output or "completed" in output.lower():
                            break
                        # Otherwise might be a failure
                        # success = False  # Don't override - trust exit code
            
            return ExecutionResult(
                success=success,
                output=output,
                error=error_output if error_output else None,
                exit_code=exit_code,
                duration_seconds=duration,
            )
            
        except FileNotFoundError:
            return ExecutionResult(
                success=False,
                output="",
                error="Claude CLI not found. Is 'claude' installed and in PATH?",
                exit_code=-1,
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
                exit_code=-1,
                duration_seconds=time.time() - start_time,
            )
        finally:
            self._process = None
            
    def cancel(self):
        """Cancel the current execution if running."""
        if self._process:
            try:
                self._process.terminate()
                # Give it a moment to terminate gracefully
                time.sleep(0.5)
                if self._process.poll() is None:
                    self._process.kill()
            except Exception:
                pass


async def execute_task_with_claude(
    project_dir: Path,
    prompt: str,
    model: str = "claude-sonnet-4-20250514",
    timeout_seconds: int = 3600,
    non_interactive: bool = False,
) -> ExecutionResult:
    """
    Convenience function to execute a task with Claude.

    Args:
        project_dir: Working directory
        prompt: Task prompt
        model: Claude model
        timeout_seconds: Maximum execution time
        non_interactive: Whether to run in non-interactive mode

    Returns:
        ExecutionResult
    """
    executor = ClaudeExecutor(
        project_dir=project_dir,
        model=model,
        timeout_seconds=timeout_seconds,
        non_interactive=non_interactive,
    )
    return await executor.execute(prompt)
