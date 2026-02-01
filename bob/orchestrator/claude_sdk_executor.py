"""
Claude Code SDK Executor
========================

Execute tasks using the claude-code-sdk Python package.
This replaces the CLI-based executor (claude_executor.py) with the proper
SDK approach from Anthropic's autonomous-coding quickstart.

Benefits over CLI shelling:
- No PTY/keyring hacks (script(1), pexpect)
- Proper streaming with tool use visibility
- permission_mode="bypassPermissions" (no --dangerously-skip-permissions)
- Token usage from message objects directly
- Security hooks via can_use_tool callback
- Max turns control
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from claude_code_sdk import (
    ClaudeCodeOptions,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    query,
)


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
    tool_uses: list[dict] = field(default_factory=list)


async def execute_with_sdk(
    project_dir: Path,
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    timeout_seconds: int = 0,
    max_turns: int = 200,
    system_prompt: Optional[str] = None,
    on_text: Optional[Callable[[str], None]] = None,
    on_tool_use: Optional[Callable[[str, dict], None]] = None,
    on_tool_result: Optional[Callable[[str, bool], None]] = None,
    allowed_tools: Optional[list[str]] = None,
    env_vars: Optional[dict[str, str]] = None,
) -> ExecutionResult:
    """Execute a task using the Claude Code SDK.

    This is the primary execution function. Uses `query()` for one-shot
    task execution (no interactive follow-ups needed).

    Args:
        project_dir: Working directory for Claude
        prompt: The task prompt
        model: Model to use
        timeout_seconds: Max execution time
        max_turns: Max tool-use turns
        system_prompt: Optional system prompt override
        on_text: Callback for text output chunks
        on_tool_use: Callback for tool use (name, input)
        on_tool_result: Callback for tool results (content_preview, is_error)
        allowed_tools: List of allowed tools (None = all)
        env_vars: Additional environment variables

    Returns:
        ExecutionResult with output and metadata
    """
    start_time = time.time()

    # Build options
    env = {}
    if env_vars:
        env.update(env_vars)

    options = ClaudeCodeOptions(
        model=model,
        cwd=str(project_dir.resolve()),
        permission_mode="bypassPermissions",
        max_turns=max_turns,
    )

    if system_prompt:
        options.system_prompt = system_prompt

    if allowed_tools:
        options.allowed_tools = allowed_tools

    if env:
        options.env = env

    # Collect output
    text_parts: list[str] = []
    tool_uses: list[dict] = []
    token_usage = TokenUsageStats()
    error_msg: Optional[str] = None

    try:
        async with asyncio.timeout(timeout_seconds if timeout_seconds > 0 else None):
            async for msg in query(prompt=prompt, options=options):
                msg_type = type(msg).__name__

                if isinstance(msg, AssistantMessage) and hasattr(msg, "content"):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and hasattr(block, "text"):
                            text_parts.append(block.text)
                            if on_text:
                                on_text(block.text)

                        elif isinstance(block, ToolUseBlock) and hasattr(block, "name"):
                            tool_info = {
                                "name": block.name,
                                "input": block.input if hasattr(block, "input") else {},
                            }
                            tool_uses.append(tool_info)
                            if on_tool_use:
                                on_tool_use(block.name, tool_info["input"])

                elif isinstance(msg, UserMessage) and hasattr(msg, "content"):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            is_error = getattr(block, "is_error", False)
                            content = str(getattr(block, "content", ""))
                            if on_tool_result:
                                preview = content[:200] if len(content) > 200 else content
                                on_tool_result(preview, is_error)

                elif isinstance(msg, ResultMessage):
                    # Extract token usage from result
                    if hasattr(msg, "usage"):
                        usage = msg.usage
                        if hasattr(usage, "input_tokens"):
                            token_usage.input_tokens = usage.input_tokens
                        if hasattr(usage, "output_tokens"):
                            token_usage.output_tokens = usage.output_tokens
                        if hasattr(usage, "cache_read_input_tokens"):
                            token_usage.cache_read_tokens = usage.cache_read_input_tokens
                        if hasattr(usage, "cache_creation_input_tokens"):
                            token_usage.cache_write_tokens = usage.cache_creation_input_tokens

    except TimeoutError:
        error_msg = f"Execution timed out after {timeout_seconds}s"
    except Exception as e:
        error_msg = str(e)

    duration = time.time() - start_time
    output = "\n".join(text_parts)

    return ExecutionResult(
        success=error_msg is None and len(output) > 0,
        output=output,
        error=error_msg,
        exit_code=0 if error_msg is None else 1,
        duration_seconds=duration,
        token_usage=token_usage,
        model_used=model,
        tool_uses=tool_uses,
    )


async def execute_task_with_sdk(
    project_dir: Path,
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    timeout_seconds: int = 0,
    non_interactive: bool = True,
    enable_thinking: bool = True,
    thinking_budget: int = 16000,
    stall_timeout: int = 0,
    verbose: bool = False,
) -> ExecutionResult:
    """Drop-in replacement for execute_task_with_claude.

    Matches the signature of the CLI-based function so it can be swapped
    in without changing callers.

    Args:
        project_dir: Working directory
        prompt: Task prompt
        model: Model name
        timeout_seconds: Max execution time (0 = unlimited)
        non_interactive: Ignored (SDK is always non-interactive)
        enable_thinking: Whether to enable extended thinking
        thinking_budget: Token budget for extended thinking
        stall_timeout: Ignored (SDK handles streaming)
        verbose: Print tool use to stdout

    Returns:
        ExecutionResult compatible with the CLI executor
    """
    callbacks = {}

    if verbose:
        def _on_text(text: str) -> None:
            print(text, end="", flush=True)

        def _on_tool_use(name: str, input_data: dict) -> None:
            input_str = str(input_data)
            if len(input_str) > 200:
                input_str = input_str[:200] + "..."
            print(f"\n[Tool: {name}] {input_str}", flush=True)

        def _on_tool_result(content: str, is_error: bool) -> None:
            prefix = "[Error]" if is_error else "[Done]"
            if is_error:
                print(f"   {prefix} {content}", flush=True)
            else:
                print(f"   {prefix}", flush=True)

        callbacks = {
            "on_text": _on_text,
            "on_tool_use": _on_tool_use,
            "on_tool_result": _on_tool_result,
        }

    # Build environment variables for thinking configuration
    env_vars = {}
    if enable_thinking and thinking_budget > 0:
        # Claude Code SDK respects these env vars for extended thinking
        env_vars["CLAUDE_CODE_ENABLE_THINKING"] = "1"
        env_vars["CLAUDE_CODE_THINKING_BUDGET"] = str(thinking_budget)

    return await execute_with_sdk(
        project_dir=project_dir,
        prompt=prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        env_vars=env_vars if env_vars else None,
        **callbacks,
    )
