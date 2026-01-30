"""
Claude CLI Executor
===================

Execute tasks using the `claude` CLI (Claude Code) as a subprocess.
This provides a reliable way to run Claude without depending on the SDK.
"""

import asyncio
import json
import subprocess
import os
import signal
import threading
import time
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class TokenUsageStats:
    """Token usage from a Claude execution."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens + self.output_tokens +
                self.cache_read_tokens + self.cache_write_tokens)


@dataclass
class ExecutionResult:
    """Result of a Claude execution."""
    success: bool
    output: str
    error: Optional[str]
    exit_code: int
    duration_seconds: float
    token_usage: Optional[TokenUsageStats] = None
    model_used: Optional[str] = None
    cost_usd: Optional[float] = None


class FileModificationWatcher:
    """Watches for file modifications in a directory.

    Snapshots file modification times before execution and checks
    periodically whether any file has been modified. If no modifications
    occur within ``stall_timeout`` seconds, sets a stall flag.
    """

    def __init__(
        self,
        watch_dir: Path,
        stall_timeout: int = 600,
        check_interval: int = 60,
        on_stall: Optional[Callable[[], None]] = None,
    ) -> None:
        self.watch_dir = Path(watch_dir)
        self.stall_timeout = stall_timeout
        self.check_interval = check_interval
        self.on_stall = on_stall
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stalled = False
        self._last_modification_time: float = time.time()

        # Directories to skip when scanning
        self._skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                          '.bob', '.tox', '.mypy_cache', '.pytest_cache'}

    def _scan_mtimes(self) -> float:
        """Scan the directory and return the most recent modification time."""
        latest = 0.0
        try:
            for root, dirs, files in os.walk(self.watch_dir):
                dirs[:] = [d for d in dirs if d not in self._skip_dirs]
                for fname in files:
                    try:
                        fpath = os.path.join(root, fname)
                        mtime = os.path.getmtime(fpath)
                        if mtime > latest:
                            latest = mtime
                    except (OSError, IOError):
                        continue
        except Exception:
            pass
        return latest

    def _watch_loop(self) -> None:
        """Background thread that checks for file modifications."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self.check_interval)
            if self._stop_event.is_set():
                break

            current_latest = self._scan_mtimes()
            if current_latest > self._last_modification_time:
                self._last_modification_time = current_latest

            elapsed = time.time() - self._last_modification_time
            if elapsed >= self.stall_timeout:
                self._stalled = True
                if self.on_stall:
                    self.on_stall()
                break

    def start(self) -> None:
        """Start watching for file modifications."""
        self._last_modification_time = max(self._scan_mtimes(), time.time())
        self._stalled = False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the watcher."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    @property
    def stalled(self) -> bool:
        """Whether a stall has been detected."""
        return self._stalled


class ClaudeExecutor:
    """
    Execute Claude Code CLI for task completion.
    
    Uses subprocess to run `claude` with the task prompt.
    Supports both synchronous completion detection and streaming output.
    Includes file modification watching for stall detection.
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
        stall_timeout: int = 600,
    ):
        """
        Initialize the executor.

        Args:
            project_dir: Working directory for claude
            model: Claude model to use
            timeout_seconds: Maximum execution time
            on_output: Optional callback for streaming output
            non_interactive: Whether to run in non-interactive mode (disable TUI, auto-select defaults)
            stall_timeout: Seconds without file modifications before killing process (default: 600)
        """
        self.project_dir = project_dir
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.on_output = on_output
        self.non_interactive = non_interactive
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
        self.stall_timeout = stall_timeout
        self._process: Optional[subprocess.Popen] = None
        self._stall_killed = False
        
    async def execute(self, prompt: str) -> ExecutionResult:
        """
        Execute a task with Claude Code.
        
        Args:
            prompt: The task prompt to send to Claude
            
        Returns:
            ExecutionResult with success status and output
        """
        start_time = time.time()
        self._stall_killed = False
        
        # Build the claude command
        # Using --dangerously-skip-permissions for autonomous operation
        # MUST use --print (-p) for non-interactive mode (accepts piped input)
        # --print DOES execute tools (Write, Bash, etc.) — it just outputs
        # results as text instead of using the TUI.
        cmd = [
            "claude",
            "-p",
            "--dangerously-skip-permissions",
            "--output-format", "json",
        ]

        # Note: Extended thinking is enabled automatically when using Opus.
        # Claude CLI does not have a --thinking-budget flag.
        # Thinking is controlled by model choice, not a CLI flag.

        cmd.append(prompt)
        
        # Set up stall detection watcher
        stall_watcher: Optional[FileModificationWatcher] = None
        if self.stall_timeout > 0:
            def _on_stall():
                """Kill the process when a stall is detected."""
                self._stall_killed = True
                if self._process:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
            
            stall_watcher = FileModificationWatcher(
                watch_dir=self.project_dir,
                stall_timeout=self.stall_timeout,
                check_interval=min(60, self.stall_timeout // 2) if self.stall_timeout > 0 else 60,
                on_stall=_on_stall,
            )
        
        # Set up environment
        env = os.environ.copy()
        env["ANTHROPIC_MODEL"] = self.model
        
        try:
            # Start stall detection watcher
            if stall_watcher:
                stall_watcher.start()
            
            # Claude CLI uses OAuth tokens stored in the system's secret
            # service (GNOME keyring via D-Bus). Without a PTY, Claude
            # cannot access the keyring and silently exits with code 0.
            #
            # Strategy (in order of preference):
            # 1. script(1) — lightweight PTY wrapper (util-linux)
            # 2. pexpect — Python PTY via pty.spawn()
            # 3. Direct subprocess — last resort, may fail with OAuth
            import shutil
            import shlex
            
            script_bin = shutil.which("script")
            use_pexpect = False
            
            if script_bin:
                # script -q -e -c 'command' /dev/null provides a PTY wrapper.
                shell_cmd = "claude -p --dangerously-skip-permissions --output-format json " + shlex.quote(prompt)
                full_cmd = [script_bin, "-q", "-e", "-c", shell_cmd, "/dev/null"]
                self._process = await asyncio.create_subprocess_exec(
                    *full_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.project_dir),
                    env=env,
                )
            else:
                # No script(1) — try pexpect for PTY
                try:
                    import pexpect
                    use_pexpect = True
                except ImportError:
                    pass
                
                if not use_pexpect:
                    # Last resort: direct subprocess (may fail with OAuth)
                    self._process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=str(self.project_dir),
                        env=env,
                    )
            
            if use_pexpect:
                # Run via pexpect in a thread to not block the event loop
                import pexpect
                
                def _run_pexpect():
                    shell_cmd = "claude -p --dangerously-skip-permissions --output-format json " + shlex.quote(prompt)
                    child = pexpect.spawn(
                        "/bin/bash", ["-c", shell_cmd],
                        cwd=str(self.project_dir),
                        env=env,
                        timeout=self.timeout_seconds,
                        encoding="utf-8",
                        codec_errors="replace",
                        maxread=1024 * 1024,  # 1MB buffer
                    )
                    child.logfile_read = None
                    try:
                        child.expect(pexpect.EOF, timeout=self.timeout_seconds)
                        output = child.before or ""
                        child.close()
                        return output, child.exitstatus or 0
                    except pexpect.TIMEOUT:
                        child.kill(signal.SIGKILL)
                        child.close()
                        return "", -1
                    except Exception as e:
                        try:
                            child.close()
                        except Exception:
                            pass
                        raise e
                
                loop = asyncio.get_event_loop()
                pexpect_output, pexpect_exit = await loop.run_in_executor(None, _run_pexpect)
                
                duration = time.time() - start_time
                exit_code = pexpect_exit
                output = pexpect_output
                error_output = ""
                
                if pexpect_exit == -1:
                    return ExecutionResult(
                        success=False,
                        output="",
                        error=f"Execution timed out after {self.timeout_seconds} seconds",
                        exit_code=-1,
                        duration_seconds=duration,
                    )
            else:
                # Collect output with timeout (script or direct subprocess path)
                try:
                    stdout, stderr = await asyncio.wait_for(
                        self._process.communicate(),
                        timeout=self.timeout_seconds
                    )
                except asyncio.TimeoutError:
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

            # Parse JSON output for token usage and cost
            token_usage = None
            cost_usd = None
            model_used = None
            json_result = None
            try:
                json_result = json.loads(output.strip())
                if isinstance(json_result, dict):
                    # Extract token usage
                    usage = json_result.get("usage", {})
                    if usage:
                        token_usage = TokenUsageStats(
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
                        )
                    # Extract cost
                    cost_usd = json_result.get("cost_usd") or json_result.get("total_cost_usd")
                    # Extract model
                    model_used = json_result.get("model")
                    # Extract the actual text result for downstream consumers
                    if "result" in json_result:
                        output = json_result["result"]
                    # Check is_error field
                    if json_result.get("is_error"):
                        exit_code = 1  # Treat as failure
            except (json.JSONDecodeError, ValueError):
                # Not valid JSON — raw text output (fallback)
                pass

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
            
            # Stop stall watcher
            if stall_watcher:
                stall_watcher.stop()
            
            # Check if we were killed due to a stall
            if self._stall_killed:
                return ExecutionResult(
                    success=False,
                    output=output if 'output' in dir() else "",
                    error=f"Stall detected: no file modifications for {self.stall_timeout} seconds. Process killed.",
                    exit_code=-2,
                    duration_seconds=time.time() - start_time,
                    token_usage=token_usage,
                    model_used=model_used,
                    cost_usd=cost_usd,
                )
            
            return ExecutionResult(
                success=success,
                output=output,
                error=error_output if error_output else None,
                exit_code=exit_code,
                duration_seconds=duration,
                token_usage=token_usage,
                model_used=model_used,
                cost_usd=cost_usd,
            )
            
        except FileNotFoundError:
            if stall_watcher:
                stall_watcher.stop()
            return ExecutionResult(
                success=False,
                output="",
                error="Claude CLI not found. Is 'claude' installed and in PATH?",
                exit_code=-1,
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            if stall_watcher:
                stall_watcher.stop()
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution error: {str(e)}",
                exit_code=-1,
                duration_seconds=time.time() - start_time,
            )
        finally:
            self._process = None
            if stall_watcher:
                stall_watcher.stop()
            
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
    stall_timeout: int = 600,
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
        stall_timeout: Seconds without file modifications before killing process (default: 600)

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
        stall_timeout=stall_timeout,
    )
    return await executor.execute(prompt)
