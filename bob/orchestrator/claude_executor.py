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
        enable_thinking: bool = False,
        thinking_budget: int = 10000,
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
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
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
        # MUST use --print (-p) for non-interactive mode (accepts piped input)
        # --print DOES execute tools (Write, Bash, etc.) — it just outputs
        # results as text instead of using the TUI.
        cmd = [
            "claude",
            "-p",
            "--dangerously-skip-permissions",
        ]

        # Enable extended thinking for complex tasks
        if self.enable_thinking:
            cmd.extend(["--thinking-budget", str(self.thinking_budget)])

        cmd.append(prompt)
        
        # Set up environment
        env = os.environ.copy()
        env["ANTHROPIC_MODEL"] = self.model
        
        try:
            # Use script(1) to provide a pseudo-TTY so Claude can access
            # GNOME keyring / D-Bus for OAuth credentials.
            # Without a PTY, Claude CLI cannot retrieve OAuth tokens from
            # the system's secret service and silently fails.
            import shutil
            script_bin = shutil.which("script")
            
            if script_bin:
                # script -q -e -c 'command' /dev/null provides a PTY wrapper.
                # -e makes script return the exit code of the child process.
                # We use shlex.quote for safe shell escaping of the prompt,
                # which can contain arbitrary multi-line text with special chars.
                import shlex
                shell_cmd = "claude -p --dangerously-skip-permissions " + shlex.quote(prompt)
                full_cmd = [script_bin, "-q", "-e", "-c", shell_cmd, "/dev/null"]
                self._process = await asyncio.create_subprocess_exec(
                    *full_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_dir),
                    env=env,
                )
            else:
                # Fallback: direct subprocess (may fail with OAuth)
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
            
            # Strip script(1) artifacts from output (carriage returns, ANSI escapes)
            import re
            output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)  # ANSI escapes
            output = output.replace('\r\n', '\n').replace('\r', '')  # CR artifacts
            
            # Determine success based on exit code
            # Claude Code returns 0 on success
            success = exit_code == 0
            
            # BUG FIX: If exit code is 0 but output is empty/whitespace,
            # this is likely a silent auth failure (OAuth credentials
            # inaccessible, Claude exits 0 via script(1) wrapper without
            # producing any output). Treat as failure.
            if success and not output.strip():
                success = False
                error_output = (error_output or "") + (
                    "\nClaude CLI exited with code 0 but produced no output. "
                    "This usually means OAuth authentication failed silently. "
                    "Try running 'claude /login' in an interactive terminal."
                )
            
            # Check for common failure patterns in output.
            # If Claude exits 0 but output contains unhandled errors
            # (no completion indicator), mark as failure.
            failure_patterns = [
                "Traceback (most recent call last):",
                "FATAL ERROR:",
                "Unhandled exception:",
            ]
            
            if success:
                for pattern in failure_patterns:
                    if pattern in output or pattern in error_output:
                        # Check if Claude handled/recovered from the error
                        if "✓" in output or "completed" in output.lower() or "successfully" in output.lower():
                            break
                        # Unrecovered error — mark as failure
                        success = False
                        error_output = (error_output or "") + (
                            f"\nDetected unrecovered failure pattern in output: {pattern}"
                        )
                        break
            
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
    enable_thinking: bool = False,
    thinking_budget: int = 10000,
) -> ExecutionResult:
    """
    Convenience function to execute a task with Claude.

    Args:
        project_dir: Working directory
        prompt: Task prompt
        model: Claude model
        timeout_seconds: Maximum execution time
        non_interactive: Whether to run in non-interactive mode
        enable_thinking: Whether to enable extended thinking
        thinking_budget: Token budget for thinking

    Returns:
        ExecutionResult
    """
    executor = ClaudeExecutor(
        project_dir=project_dir,
        model=model,
        timeout_seconds=timeout_seconds,
        non_interactive=non_interactive,
        enable_thinking=enable_thinking,
        thinking_budget=thinking_budget,
    )
    return await executor.execute(prompt)
