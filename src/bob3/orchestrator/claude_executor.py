"""Claude Code SDK executor for Bob3 sub-agent orchestration.

This module wraps the claude-code-sdk Python package to spawn, manage,
and communicate with Claude Code sub-agents. It is the ONLY mechanism
Bob3 uses to interact with Claude -- no shell calls, no CLI invocations,
no anthropic SDK usage.

Key classes:
    ClaudeExecutor: High-level executor for running prompts against Claude.
    ExecutionResult: Dataclass holding the response text, cost, and metadata.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any, AsyncIterator, Awaitable, Callable

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ClaudeSDKClient,
    ContentBlock,
    Message,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model name mapping
# ---------------------------------------------------------------------------

MODEL_ALIASES: dict[str, str] = {
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}

VALID_MODEL_IDS: frozenset[str] = frozenset(MODEL_ALIASES.values())

DEFAULT_SUB_AGENT_MODEL = "sonnet"
DEFAULT_SUB_AGENT_MAX_TURNS = 25
DEFAULT_SUB_AGENT_PERMISSION_MODE = "bypassPermissions"

# ---------------------------------------------------------------------------
# Parent-session environment variable guard
# ---------------------------------------------------------------------------

# Claude Code sets these vars when it launches.  The SDK merges os.environ
# into every subprocess it spawns, so if bob3 is itself running inside a
# Claude Code session these vars bleed into sub-agents and trigger a
# "nested session" conflict.  Strip them for the duration of each SDK call.
_PARENT_SESSION_VARS: tuple[str, ...] = (
    "CLAUDECODE",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_IDE_WEBSOCKET_URI",
)


@contextlib.contextmanager
def _stripped_parent_session_env():  # type: ignore[return]
    """Temporarily remove Claude Code parent-session env vars.

    The claude-code-sdk builds the subprocess environment as::

        {**os.environ, **options.env, "CLAUDE_CODE_ENTRYPOINT": "sdk-py"}

    There is no way to *delete* a key through ``options.env``; we must pop
    them from ``os.environ`` before the call and restore them afterward.
    """
    saved = {k: os.environ.pop(k) for k in _PARENT_SESSION_VARS if k in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def validate_api_key() -> str | None:
    """Check for a Claude API key in the environment.

    Checks CLAUDE_API_KEY first, then falls back to ANTHROPIC_API_KEY.
    Returns the key value if found and non-empty, or None otherwise.
    """
    key = os.environ.get("CLAUDE_API_KEY", "").strip()
    if key:
        return key
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    return None


def require_api_key() -> str:
    """Require a Claude API key, raising EnvironmentError if missing.

    Checks CLAUDE_API_KEY first, then ANTHROPIC_API_KEY.
    Raises EnvironmentError with a helpful message if neither is set.
    """
    key = validate_api_key()
    if key is not None:
        return key
    raise EnvironmentError(
        "Missing API key for Claude authentication. "
        "Set CLAUDE_API_KEY or ANTHROPIC_API_KEY in your environment. "
        "Example: export CLAUDE_API_KEY=sk-your-key-here"
    )


def resolve_model_name(model: str | None) -> str | None:
    """Resolve a model alias or full model ID to a valid Claude model ID.

    Accepts short aliases ("sonnet", "opus", "haiku") or full
    model IDs ("claude-sonnet-4-5-20250929"). Returns None when
    the input is None.
    """
    if model is None:
        return None
    normalized = model.strip().lower()
    if normalized in MODEL_ALIASES:
        return MODEL_ALIASES[normalized]
    if normalized in VALID_MODEL_IDS:
        return normalized
    if model in VALID_MODEL_IDS:
        return model
    raise ValueError(
        f"Unknown model '{model}'. "
        f"Use an alias ({', '.join(sorted(MODEL_ALIASES))}) "
        f"or a full model ID ({', '.join(sorted(VALID_MODEL_IDS))})"
    )


# ---------------------------------------------------------------------------
# Sub-agent options builder
# ---------------------------------------------------------------------------


def build_sub_agent_options(
    *,
    cwd: str | Path | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
    mcp_servers: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> ClaudeCodeOptions:
    """Build a ClaudeCodeOptions for spawning a Bob3 sub-agent.

    Applies Bob3 defaults (permission mode "bypassPermissions", default
    max turns, model resolution from aliases).
    """
    kwargs: dict[str, Any] = {}

    if cwd is not None:
        kwargs["cwd"] = str(cwd)
        # Ensure bob3 skills are available at <cwd>/.claude/skills/ so
        # the sub-agent can discover them. Idempotent — only re-links on
        # bob3 upgrades. Non-fatal on failure (skills are advisory).
        try:
            from bob3.skills_installer import (
                install_skills_to_workspace,
                verify_skills_integrity,
            )

            install_skills_to_workspace(cwd)
            # Defense-in-depth: a previous sub-agent (running with
            # bypassPermissions in the same workspace) could have
            # replaced a bob3 skill symlink with a malicious directory.
            # Audit and force-replace any tampered entries before the
            # next sub-agent loads skills. Logged at WARNING when
            # anything is replaced. Non-fatal on internal failure.
            verify_skills_integrity(cwd)
        except Exception as exc:
            logger.debug("Skill installation skipped: %s", exc)

    try:
        resolved_model = resolve_model_name(model)
    except ValueError as exc:
        # Unknown model: fall back to the default rather than crashing the
        # entire orchestration. The caller may have supplied a stale or
        # typo'd alias; log a warning and continue with the safe default.
        logger.warning(
            "Unknown model %r (%s); falling back to default %r",
            model,
            exc,
            DEFAULT_SUB_AGENT_MODEL,
        )
        resolved_model = resolve_model_name(DEFAULT_SUB_AGENT_MODEL)
    if resolved_model is not None:
        kwargs["model"] = resolved_model

    kwargs["max_turns"] = max_turns if max_turns is not None else DEFAULT_SUB_AGENT_MAX_TURNS

    if system_prompt is not None:
        kwargs["system_prompt"] = system_prompt

    if append_system_prompt is not None:
        kwargs["append_system_prompt"] = append_system_prompt

    if allowed_tools is not None:
        kwargs["allowed_tools"] = list(allowed_tools)

    if disallowed_tools is not None:
        kwargs["disallowed_tools"] = list(disallowed_tools)

    kwargs["permission_mode"] = (
        permission_mode if permission_mode is not None else DEFAULT_SUB_AGENT_PERMISSION_MODE
    )

    if mcp_servers is not None:
        kwargs["mcp_servers"] = dict(mcp_servers)

    env_dict: dict[str, str] = dict(env) if env else {}

    # F081: Forward CLAUDE_API_KEY / ANTHROPIC_API_KEY to sub-agent env
    if "ANTHROPIC_API_KEY" not in env_dict:
        api_key = validate_api_key()
        if api_key is not None:
            env_dict["ANTHROPIC_API_KEY"] = api_key

    if env_dict:
        kwargs["env"] = env_dict

    return ClaudeCodeOptions(**kwargs)


# ---------------------------------------------------------------------------
# Stderr-capture helper (R10-013)
# ---------------------------------------------------------------------------


def _attach_stderr_capture(
    options: "ClaudeCodeOptions | None",
    buffer: "IO[str]",
) -> "ClaudeCodeOptions":
    """Return a ClaudeCodeOptions configured to mirror SDK stderr to ``buffer``.

    The SDK only writes to ``options.debug_stderr`` when
    ``"debug-to-stderr"`` is present in ``options.extra_args``. We set both
    so the underlying ``claude`` Node.js process's stderr is captured into
    ``buffer`` for diagnostic surfacing on spawn-time failures (R10-013).

    ``buffer`` MUST be a real file-backed text stream (e.g. one returned
    by :func:`tempfile.NamedTemporaryFile`) — the SDK calls ``.fileno()``
    on it to wire up an OS-level redirect (R10-018). An ``io.StringIO``
    does NOT have a ``fileno()`` and will fail every spawn.

    A new options object is constructed (rather than mutating in place)
    because the caller may reuse ``options`` across multiple sub-agent
    spawns and we don't want our debug-stderr config to leak.
    """
    if options is None:
        return ClaudeCodeOptions(
            extra_args={"debug-to-stderr": None},
            debug_stderr=buffer,
        )
    # Build a new options object preserving every set field. Mirroring
    # the same key list as ``_merge_mcp`` below so we keep field coverage
    # in sync if the SDK adds more options.
    kwargs: dict[str, Any] = {}
    if options.cwd is not None:
        kwargs["cwd"] = options.cwd
    if options.model is not None:
        kwargs["model"] = options.model
    if options.max_turns is not None:
        kwargs["max_turns"] = options.max_turns
    if options.system_prompt is not None:
        kwargs["system_prompt"] = options.system_prompt
    if options.append_system_prompt is not None:
        kwargs["append_system_prompt"] = options.append_system_prompt
    if options.allowed_tools is not None:
        kwargs["allowed_tools"] = list(options.allowed_tools)
    if options.disallowed_tools is not None:
        kwargs["disallowed_tools"] = list(options.disallowed_tools)
    if options.permission_mode is not None:
        kwargs["permission_mode"] = options.permission_mode
    if options.env is not None:
        kwargs["env"] = dict(options.env)
    if options.mcp_servers is not None:
        kwargs["mcp_servers"] = dict(options.mcp_servers)
    # Preserve any caller-supplied extra_args; merge in debug-to-stderr.
    extra = dict(options.extra_args) if options.extra_args else {}
    extra.setdefault("debug-to-stderr", None)
    kwargs["extra_args"] = extra
    kwargs["debug_stderr"] = buffer
    try:
        return ClaudeCodeOptions(**kwargs)
    except TypeError:
        # Older SDK versions may not accept every key here. Drop the
        # debug fields and return the original options on the assumption
        # that capturing stderr is best-effort.
        kwargs.pop("extra_args", None)
        kwargs.pop("debug_stderr", None)
        try:
            return ClaudeCodeOptions(**kwargs)
        except TypeError:
            return options


def _format_spawn_exception(
    exc: BaseException,
    captured_stderr: str | None = None,
    *,
    max_stderr_chars: int = 1000,
) -> str:
    """Return a diagnostic-rich error message for a spawn failure (R10-013).

    Combines the exception's str() with any ``exit_code``/``stderr``
    attributes (set by ``ProcessError``), the ``__cause__`` chain, and
    the tail of ``captured_stderr`` (already-read string from the
    file-backed stderr buffer; see R10-018). The output replaces the
    SDK's unhelpful ``"Check stderr output for details"`` placeholder
    so operators see the actual stderr the subprocess emitted.
    """
    parts: list[str] = [f"{type(exc).__name__}: {exc}"]

    exit_code = getattr(exc, "exit_code", None)
    if exit_code is not None:
        parts.append(f"exit_code={exit_code}")

    sdk_stderr = getattr(exc, "stderr", None)
    if sdk_stderr and sdk_stderr != "Check stderr output for details":
        parts.append(f"sdk_stderr={sdk_stderr!s}")

    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        parts.append(f"cause={type(cause).__name__}: {cause}")

    if captured_stderr:
        tail = captured_stderr[-max_stderr_chars:]
        parts.append(f"captured_stderr_tail=\n{tail}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    """Holds the outcome of a single Claude executor run."""

    text: str = ""
    is_error: bool = False
    error_message: str = ""
    duration_ms: int = 0
    num_turns: int = 0
    session_id: str = ""
    total_cost_usd: float | None = None
    tool_uses: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Content-block text extraction
# ---------------------------------------------------------------------------


def extract_text_from_blocks(blocks: list[ContentBlock]) -> str:
    """Pull plain text out of a list of content blocks.

    Only TextBlock instances contribute text; tool-use and tool-result
    blocks are silently skipped.
    """
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, TextBlock):
            parts.append(block.text)
    return "\n".join(parts)


def extract_tool_names(blocks: list[ContentBlock]) -> list[str]:
    """Return tool names from any ToolUseBlock instances in blocks."""
    names: list[str] = []
    for block in blocks:
        if isinstance(block, ToolUseBlock):
            names.append(block.name)
    return names


# ---------------------------------------------------------------------------
# Message processing
# ---------------------------------------------------------------------------


def process_message(msg: Message, result: ExecutionResult) -> None:
    """Update result in-place by interpreting a single SDK message.

    Handles AssistantMessage, ResultMessage, UserMessage, and SystemMessage.
    """
    if isinstance(msg, AssistantMessage):
        text = extract_text_from_blocks(msg.content)
        if text:
            if result.text:
                result.text += "\n" + text
            else:
                result.text = text
        result.tool_uses.extend(extract_tool_names(msg.content))

    elif isinstance(msg, ResultMessage):
        result.duration_ms = msg.duration_ms
        result.num_turns = msg.num_turns
        result.session_id = msg.session_id
        result.total_cost_usd = msg.total_cost_usd
        result.is_error = msg.is_error
        if msg.is_error and msg.result:
            result.error_message = msg.result

    elif isinstance(msg, UserMessage):
        logger.debug("UserMessage received during execution")

    elif isinstance(msg, SystemMessage):
        logger.debug("SystemMessage (subtype=%s) received", msg.subtype)

    result.messages.append(msg)


# ---------------------------------------------------------------------------
# Async streaming helper
# ---------------------------------------------------------------------------


async def stream_query(
    prompt: str,
    *,
    options: ClaudeCodeOptions | None = None,
) -> AsyncIterator[Message]:
    """Thin async-generator wrapper around claude_code_sdk.query.

    Yields each Message exactly as returned by the SDK's async iterator.
    """
    async for msg in query(prompt=prompt, options=options):
        yield msg


# ---------------------------------------------------------------------------
# Typed message stream handler
# ---------------------------------------------------------------------------

MessageCallback = Callable[[Message, ExecutionResult], Awaitable[None] | None]


class MessageStreamHandler:
    """Typed handler for async message streams from Claude SDK.

    Provides per-message-type callback registration so callers can react
    to specific message types as they arrive.
    """

    def __init__(self) -> None:
        self.on_assistant_message: MessageCallback | None = None
        self.on_result_message: MessageCallback | None = None
        self.on_error: MessageCallback | None = None
        self.on_system_message: MessageCallback | None = None
        self.on_user_message: MessageCallback | None = None
        self.on_any_message: MessageCallback | None = None

    async def _invoke(
        self,
        callback: MessageCallback | None,
        msg: Message,
        result: ExecutionResult,
    ) -> None:
        if callback is None:
            return
        ret = callback(msg, result)
        if ret is not None and hasattr(ret, "__await__"):
            await ret

    async def consume(
        self,
        stream: AsyncIterator[Message],
        *,
        result: ExecutionResult | None = None,
    ) -> ExecutionResult:
        """Consume an entire async message stream, dispatching to handlers."""
        if result is None:
            result = ExecutionResult()

        async for msg in stream:
            process_message(msg, result)

            if isinstance(msg, AssistantMessage):
                await self._invoke(self.on_assistant_message, msg, result)
            elif isinstance(msg, ResultMessage):
                await self._invoke(self.on_result_message, msg, result)
                if msg.is_error:
                    await self._invoke(self.on_error, msg, result)
            elif isinstance(msg, SystemMessage):
                await self._invoke(self.on_system_message, msg, result)
            elif isinstance(msg, UserMessage):
                await self._invoke(self.on_user_message, msg, result)

            await self._invoke(self.on_any_message, msg, result)

        return result


# ---------------------------------------------------------------------------
# High-level executor
# ---------------------------------------------------------------------------


class ClaudeExecutor:
    """High-level executor for running prompts against Claude via the SDK.

    Wraps claude_code_sdk.query() to provide a simple async interface
    for Bob3 orchestration. Returns ExecutionResult with accumulated
    text, metadata, and cost information.
    """

    def __init__(
        self,
        *,
        default_options: ClaudeCodeOptions | None = None,
    ) -> None:
        self.default_options = default_options

    async def execute(
        self,
        prompt: str,
        *,
        options: ClaudeCodeOptions | None = None,
        on_message: MessageCallback | None = None,
    ) -> ExecutionResult:
        """Execute a prompt and return the accumulated result.

        Args:
            prompt: The prompt to send to Claude.
            options: ClaudeCodeOptions to use. Falls back to default_options
                if not provided.
            on_message: Optional callback invoked for each message received.

        Returns:
            ExecutionResult with accumulated text, cost, and metadata.
        """
        opts = options or self.default_options

        handler = MessageStreamHandler()
        if on_message is not None:
            handler.on_any_message = on_message

        # Strip parent-session env vars so they don't leak into the
        # SDK-spawned subprocess. Mirrors the guard around
        # ``spawn_sub_agent`` -- without this, calling ``.execute()``
        # directly (e.g. from a new feature or integration test) would
        # propagate CLAUDE_CODE_SESSION_ID and trigger a nested-session
        # conflict.
        with _stripped_parent_session_env():
            stream = stream_query(prompt, options=opts)
            return await handler.consume(stream)


# ---------------------------------------------------------------------------
# Sub-agent spawning (F057)
# ---------------------------------------------------------------------------


@dataclass
class SpawnResult:
    """Result of spawning a sub-agent, combining the execution result
    with the database tracking record."""

    execution_result: ExecutionResult
    agent_run: Any  # SubAgentRun from bob3.models (avoided import cycle)


async def spawn_sub_agent(
    *,
    project_id: str,
    purpose: str,
    prompt: str,
    target_type: str | None = None,
    target_id: str | None = None,
    parent_run_id: str | None = None,
    options: ClaudeCodeOptions | None = None,
    mcp_enabled: str | None = None,
    enable_puppeteer: bool = False,
    on_message: MessageCallback | None = None,
) -> SpawnResult:
    """Spawn a Claude sub-agent with full database tracking.

    Creates a sub_agent_runs record, executes the prompt via
    claude_code_sdk.query(), tracks cost/token/duration metrics,
    and updates the record when execution completes.

    Args:
        project_id: Project this agent run belongs to.
        purpose: Purpose of the agent (e.g. implement_feature, rca_analyst).
        prompt: The prompt to send to the Claude sub-agent.
        target_type: Optional target type (e.g. "feature", "task").
        target_id: Optional target ID (e.g. feature or task ID).
        parent_run_id: Optional parent agent run ID for hierarchy tracking.
        options: ClaudeCodeOptions to configure the sub-agent.
        mcp_enabled: Optional JSON string of enabled MCP plugins.
        enable_puppeteer: When True, adds Puppeteer MCP to the sub-agent (F105).
        on_message: Optional callback invoked for each message received.

    Returns:
        SpawnResult containing the execution result and the agent run record.
    """
    from bob3 import db
    from bob3.orchestrator.mcp_config import (
        build_perplexity_mcp_dict,
        build_puppeteer_mcp_dict,
    )

    def _merge_mcp(opts: ClaudeCodeOptions | None, extra: dict[str, Any]) -> ClaudeCodeOptions:
        """Return a new ClaudeCodeOptions with ``extra`` merged into mcp_servers."""
        if opts is None:
            return build_sub_agent_options(mcp_servers=extra)
        existing_servers = dict(opts.mcp_servers) if opts.mcp_servers else {}
        existing_servers.update(extra)
        kwargs: dict[str, Any] = {}
        if opts.cwd is not None:
            kwargs["cwd"] = opts.cwd
        if opts.model is not None:
            kwargs["model"] = opts.model
        if opts.max_turns is not None:
            kwargs["max_turns"] = opts.max_turns
        if opts.system_prompt is not None:
            kwargs["system_prompt"] = opts.system_prompt
        if opts.append_system_prompt is not None:
            kwargs["append_system_prompt"] = opts.append_system_prompt
        if opts.allowed_tools is not None:
            kwargs["allowed_tools"] = list(opts.allowed_tools)
        if opts.disallowed_tools is not None:
            kwargs["disallowed_tools"] = list(opts.disallowed_tools)
        if opts.permission_mode is not None:
            kwargs["permission_mode"] = opts.permission_mode
        if opts.env is not None:
            kwargs["env"] = dict(opts.env)
        kwargs["mcp_servers"] = existing_servers
        return ClaudeCodeOptions(**kwargs)

    if mcp_enabled is not None:
        mcp_list = json.loads(mcp_enabled)
    else:
        mcp_list = []

    # F105: Merge Puppeteer MCP into options when enabled
    if enable_puppeteer:
        options = _merge_mcp(options, build_puppeteer_mcp_dict())
        if "puppeteer" not in mcp_list:
            mcp_list.append("puppeteer")

    # Auto-inject Perplexity MCP for implementation sub-agents when an API
    # key is configured. The README advertises that sub-agents can use
    # Perplexity; without this branch only spawn_research_agent honored
    # that. Skipped silently when PERPLEXITY_API_KEY is unset so projects
    # without a Perplexity subscription continue to work unchanged.
    if os.environ.get("PERPLEXITY_API_KEY", "").strip():
        existing_servers = dict(options.mcp_servers) if options and options.mcp_servers else {}
        if "perplexity" not in existing_servers:
            options = _merge_mcp(options, build_perplexity_mcp_dict())
            if "perplexity" not in mcp_list:
                mcp_list.append("perplexity")

    mcp_enabled = json.dumps(mcp_list) if mcp_list else mcp_enabled

    # Truncate prompt for summary (first 200 chars)
    prompt_summary = prompt[:200] if len(prompt) > 200 else prompt

    # Step 1: Create the agent run record before execution
    agent_run = db.create_agent_run(
        project_id=project_id,
        purpose=purpose,
        target_type=target_type,
        target_id=target_id,
        parent_run_id=parent_run_id,
        prompt_summary=prompt_summary,
        mcp_enabled=mcp_enabled,
        status="running",
    )

    # Step 2: Execute the agent via claude_code_sdk.
    # Strip parent-session env vars for the duration so they don't leak
    # into the sub-agent process (the SDK merges os.environ into its env).
    #
    # R5-007: When the caller wraps this in ``asyncio.wait_for`` and the
    # timeout fires, asyncio cancels this coroutine. Without the
    # try/finally below, the inner async generator returned by
    # ``stream_query`` is not always awaited to completion before the
    # cancel propagates back to the caller, which means the SDK's own
    # ``query.close()`` (which terminates the underlying ``claude``
    # Node.js subprocess) may never run. The sub-agent process leaks.
    #
    # The fix: explicitly call ``aclose()`` on the async generator inside
    # a finally block. ``aclose()`` runs any ``finally`` clauses inside
    # the generator (including the SDK's ``query.close()`` which calls
    # ``transport.close()``, which sends SIGTERM to the subprocess).
    # If the SDK still leaks (older versions, transport changes), we
    # also emit a SECURITY warning so the operator knows to inspect.
    result = ExecutionResult()
    # R10-013: Wire a writable text buffer into ``options.debug_stderr``
    # plus ``extra_args={"debug-to-stderr": None}`` so the SDK's CLI
    # subprocess streams its stderr into our buffer. When the subprocess
    # dies before producing any messages (the F013 sub-agent spawn-time
    # failure pattern: duration_ms=0, num_turns=0), the SDK raises
    # ``ProcessError(stderr="Check stderr output for details")`` with no
    # diagnostic. The buffer below captures the actual stderr we can
    # surface in ``error_message`` so operators can act on the failure.
    #
    # R10-018: The buffer MUST be a real file-backed stream because the
    # SDK calls ``.fileno()`` on it to set up an OS-level subprocess
    # redirect. ``io.StringIO`` raises ``UnsupportedOperation: fileno``
    # and breaks every spawn — that bug landed with R10-013 and made
    # every sub-agent in the swedish-circle resume fail with
    # ``CLIConnectionError: Failed to start Claude Code: fileno``.
    # ``NamedTemporaryFile`` has a real fd; we ``unlink`` it after
    # reading so it does not litter ``/tmp``.
    stderr_buf = tempfile.NamedTemporaryFile(
        mode="w+",
        encoding="utf-8",
        delete=False,
        prefix="bob3_subagent_stderr_",
    )
    stderr_path = stderr_buf.name
    captured_stderr = ""
    options = _attach_stderr_capture(options, stderr_buf)
    stream: AsyncIterator[Message] | None = None
    # R9-001: Track whether we obtained a clean result so the finally
    # block can pick the right terminal status. Without this flag, a
    # CancelledError (timeout / Ctrl-C) would leave the agent_runs row
    # at status='running' forever — the previous code only updated the
    # row AFTER the try/except/finally block, which CancelledError
    # skipped on its way out of the coroutine. The flag flips True only
    # when ``handler.consume`` returned without raising.
    consume_completed = False
    cancelled = False
    updated_run = None
    try:
        handler = MessageStreamHandler()
        if on_message is not None:
            handler.on_any_message = on_message

        with _stripped_parent_session_env():
            stream = stream_query(prompt, options=options)
            try:
                result = await handler.consume(stream)
                consume_completed = True
            except asyncio.CancelledError:
                logger.warning(
                    "SECURITY: Sub-agent (purpose=%s, target=%s/%s, run_id=%s) "
                    "was cancelled before completion; attempting to close the "
                    "SDK stream so the underlying claude Node.js process is "
                    "terminated. If you continue to see orphaned claude "
                    "processes after a timeout, run `pgrep -f claude` and "
                    "kill them manually.",
                    purpose,
                    target_type,
                    target_id,
                    getattr(agent_run, "id", None),
                )
                cancelled = True
                raise
    except asyncio.CancelledError:
        # Ensure the finally below still runs to close the stream, then
        # re-raise so the caller (asyncio.wait_for) sees the timeout.
        cancelled = True
        raise
    except Exception as exc:
        result.is_error = True
        # R10-013: Replace the SDK's placeholder
        # "Command failed with exit code 1\nError output: Check stderr output for details"
        # with the actual stderr we captured via ``debug_stderr`` plus
        # ``exit_code`` / ``__cause__`` / ``args`` for diagnostic value.
        # R10-018: pull the captured stderr out of the file-backed buffer
        # before the finally block deletes it.
        try:
            stderr_buf.flush()
            stderr_buf.seek(0)
            captured_stderr = stderr_buf.read()
        except Exception:
            captured_stderr = ""
        result.error_message = _format_spawn_exception(exc, captured_stderr)
    finally:
        # Best-effort close of the SDK stream so the SDK's own
        # ``query.close()`` finally-block runs (it terminates the
        # underlying subprocess via ``transport.close()``).
        if stream is not None:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except asyncio.CancelledError:
                    # aclose itself can raise CancelledError; we're already
                    # in the cancellation path so just continue.
                    cancelled = True
                except Exception:
                    logger.warning(
                        "SECURITY: Failed to cleanly close the claude SDK "
                        "stream after cancellation; the underlying claude "
                        "Node.js process may still be running. Check "
                        "`pgrep -f claude` and kill if needed.",
                        exc_info=True,
                    )

        # R10-018: clean up the tempfile-backed stderr buffer. We close
        # then unlink so the file does not litter ``/tmp`` even if the
        # spawn succeeded. ``delete=False`` was required so the SDK
        # subprocess could open the fd by name on platforms where the
        # temporary directory and the cwd differ. Failures here are
        # best-effort: the in-flight exception (if any) must not be
        # masked.
        try:
            stderr_buf.close()
        except Exception:
            pass
        try:
            os.unlink(stderr_path)
        except OSError:
            pass

        # R9-001: Always update the agent_run row before unwinding, even
        # when the coroutine was cancelled. Previously this update lived
        # AFTER the try/except/finally block and CancelledError skipped
        # it entirely, leaving every timed-out sub-agent at
        # status='running' forever — polluting audit queries and cost
        # reporting. ``BaseException`` is caught defensively because
        # this finally must not mask the in-flight cancellation if the
        # DB write itself misbehaves.
        if cancelled:
            final_status = "interrupted"
        elif consume_completed and not result.is_error:
            final_status = "completed"
        else:
            final_status = "failed"

        try:
            now = datetime.now()
            updated_run = db.update_agent_run(
                agent_run.id,
                status=final_status,
                cost_usd=result.total_cost_usd,
                duration_ms=result.duration_ms,
                completed_at=now.isoformat(),
            )
        except BaseException:  # noqa: BLE001 — last-ditch cleanup
            logger.warning(
                "Failed to finalize sub_agent_runs row %s to status=%s; "
                "row may remain at 'running'. This is best-effort "
                "cleanup so the in-flight exception is not masked.",
                getattr(agent_run, "id", None),
                final_status,
                exc_info=True,
            )

    return SpawnResult(
        execution_result=result,
        agent_run=updated_run or agent_run,
    )


# ---------------------------------------------------------------------------
# Research agent spawning (F101)
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = (
    "You are a research agent. Use the Perplexity MCP tools to search the web "
    "and gather information. Return a clear, structured summary of your findings."
)


async def spawn_research_agent(
    *,
    project_id: str,
    query: str,
    purpose: str = "research",
    target_type: str | None = None,
    target_id: str | None = None,
    parent_run_id: str | None = None,
    max_turns: int = 10,
    workspace: str | Path | None = None,
    on_message: MessageCallback | None = None,
) -> SpawnResult:
    """Spawn a research sub-agent with Perplexity MCP enabled.

    Creates a Claude sub-agent configured with the Perplexity MCP plugin
    for web research. The agent is tracked in the sub_agent_runs table
    with mcp_enabled indicating Perplexity usage.

    Use cases:
    - Feature has research_required=True
    - RCA classifies failure as MISSING_INFO
    - generate-features command analyzing PDFs

    Args:
        project_id: Project this research belongs to.
        query: The research question or topic to investigate.
        purpose: Purpose of the agent run (default: "research").
        target_type: Optional target type (e.g. "feature", "task").
        target_id: Optional target ID (e.g. feature or task ID).
        parent_run_id: Optional parent agent run ID for hierarchy.
        max_turns: Maximum turns for the research agent (default: 10).
        workspace: Optional path to the project workspace. When supplied,
            ``build_sub_agent_options`` runs ``install_skills_to_workspace``
            and ``verify_skills_integrity`` against this directory before
            the research agent spawns. This is the defense-in-depth path
            for R9-007 (skill poisoning) — without ``workspace`` the
            integrity check is skipped, re-exposing R4-012.

            SECURITY TRADE-OFF: setting ``cwd`` on the sub-agent options
            also means the research agent inherits filesystem access to
            ``workspace`` (combined with the default
            ``permission_mode='bypassPermissions'`` it can read/write any
            file under that directory). For research workloads this is
            acceptable because (a) the agent's only useful tools are the
            Perplexity MCP, which doesn't need FS access; and (b) the
            same sub-agent could already touch the workspace via any
            implementation agent that previously ran there. The
            ``verify_skills_integrity`` step is what closes the
            chained-attack window where a prior malicious agent
            replaced a skill symlink.
        on_message: Optional callback invoked for each message received.

    Returns:
        SpawnResult containing the execution result and agent run record.
    """
    from bob3.orchestrator.mcp_config import build_perplexity_mcp_dict

    # Build options with Perplexity MCP configured
    mcp_servers = build_perplexity_mcp_dict()

    options = build_sub_agent_options(
        cwd=workspace,
        model=DEFAULT_SUB_AGENT_MODEL,
        max_turns=max_turns,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        mcp_servers=mcp_servers,
    )

    # Build research prompt
    prompt = f"Research the following topic and provide a detailed summary:\n\n{query}"

    # Track which MCP plugins are enabled
    mcp_enabled = json.dumps(list(mcp_servers.keys()))

    return await spawn_sub_agent(
        project_id=project_id,
        purpose=purpose,
        prompt=prompt,
        target_type=target_type,
        target_id=target_id,
        parent_run_id=parent_run_id,
        options=options,
        mcp_enabled=mcp_enabled,
        on_message=on_message,
    )


# ---------------------------------------------------------------------------
# Puppeteer browser agent (F105)
# ---------------------------------------------------------------------------

PUPPETEER_SYSTEM_PROMPT = (
    "You are a browser automation agent. Use the Puppeteer MCP tools to navigate "
    "web pages, interact with UI elements, and capture screenshots. "
    "Return a clear summary of what you found and any screenshots taken."
)


@dataclass
class ScreenshotEvidenceResult:
    """Result of capturing a screenshot as evidence.

    Combines the spawn result (agent run + execution) with the
    evidence artifact created in the database.
    """

    spawn_result: SpawnResult
    evidence: Any  # EvidenceArtifact from bob3.models


async def capture_screenshot_evidence(
    *,
    project_id: str,
    url: str,
    feature_id: str | None = None,
    task_id: str | None = None,
    parent_run_id: str | None = None,
    max_turns: int = 15,
    on_message: MessageCallback | None = None,
) -> ScreenshotEvidenceResult:
    """Capture a screenshot via Puppeteer and store it as an evidence artifact.

    Spawns a Puppeteer sub-agent to navigate to the URL and take a screenshot,
    then creates an evidence_artifact record with type='screenshot', the URL
    and agent response stored as JSON in the content field, and a SHA256 hash
    for verification.

    Args:
        project_id: Project this evidence belongs to.
        url: The URL to navigate to and screenshot.
        feature_id: Optional feature to link the evidence to.
        task_id: Optional task to link the evidence to.
        parent_run_id: Optional parent agent run ID for hierarchy.
        max_turns: Maximum turns for the browser agent (default: 15).
        on_message: Optional callback invoked for each message received.

    Returns:
        ScreenshotEvidenceResult containing the spawn result and evidence artifact.
    """
    from bob3 import db

    # Step 1-2: Spawn a Puppeteer agent to capture the screenshot
    spawn_result = await spawn_puppeteer_agent(
        project_id=project_id,
        url=url,
        task="Take a screenshot of the page for evidence.",
        purpose="screenshot_evidence",
        target_type="feature" if feature_id else None,
        target_id=feature_id,
        parent_run_id=parent_run_id,
        max_turns=max_turns,
        on_message=on_message,
    )

    # Step 4: Build content JSON with URL and agent response
    content_dict: dict[str, Any] = {
        "url": url,
        "agent_response": spawn_result.execution_result.text,
    }
    if spawn_result.execution_result.is_error:
        content_dict["error"] = True
        if spawn_result.execution_result.error_message:
            content_dict["error_message"] = spawn_result.execution_result.error_message

    content_json = json.dumps(content_dict)

    # Step 3 + 5: Create evidence artifact with type='screenshot' and computed hash
    evidence = db.create_evidence_with_hash(
        project_id=project_id,
        type="screenshot",
        content=content_json,
        feature_id=feature_id,
        task_id=task_id,
    )

    return ScreenshotEvidenceResult(
        spawn_result=spawn_result,
        evidence=evidence,
    )


async def spawn_puppeteer_agent(
    *,
    project_id: str,
    url: str,
    task: str | None = None,
    purpose: str = "browser_test",
    target_type: str | None = None,
    target_id: str | None = None,
    parent_run_id: str | None = None,
    max_turns: int = 15,
    on_message: MessageCallback | None = None,
) -> SpawnResult:
    """Spawn a sub-agent with Puppeteer MCP enabled for browser automation.

    Creates a Claude sub-agent configured with the Puppeteer MCP plugin
    for browser testing and screenshot capture. The agent is tracked in
    the sub_agent_runs table with mcp_enabled indicating Puppeteer usage.

    Use cases:
    - Feature involves web UI testing
    - Need screenshots for evidence artifacts
    - End-to-end browser testing

    Args:
        project_id: Project this browser test belongs to.
        url: The URL to navigate to.
        task: Optional specific task to perform on the page.
        purpose: Purpose of the agent run (default: "browser_test").
        target_type: Optional target type (e.g. "feature", "task").
        target_id: Optional target ID (e.g. feature or task ID).
        parent_run_id: Optional parent agent run ID for hierarchy.
        max_turns: Maximum turns for the browser agent (default: 15).
        on_message: Optional callback invoked for each message received.

    Returns:
        SpawnResult containing the execution result and agent run record.
    """
    from bob3.orchestrator.mcp_config import build_puppeteer_mcp_dict

    mcp_servers = build_puppeteer_mcp_dict()

    options = build_sub_agent_options(
        model=DEFAULT_SUB_AGENT_MODEL,
        max_turns=max_turns,
        system_prompt=PUPPETEER_SYSTEM_PROMPT,
        mcp_servers=mcp_servers,
    )

    # Build browser automation prompt
    prompt_parts = [f"Navigate to {url} using the Puppeteer tools."]
    if task:
        prompt_parts.append(f"\nTask: {task}")
    prompt_parts.append("\nTake a screenshot and report what you see on the page.")
    prompt = "\n".join(prompt_parts)

    mcp_enabled = json.dumps(list(mcp_servers.keys()))

    return await spawn_sub_agent(
        project_id=project_id,
        purpose=purpose,
        prompt=prompt,
        target_type=target_type,
        target_id=target_id,
        parent_run_id=parent_run_id,
        options=options,
        mcp_enabled=mcp_enabled,
        on_message=on_message,
    )


# ---------------------------------------------------------------------------
# RCA (Root Cause Analysis) agent (F058 + F106 Systematic Debugging)
# ---------------------------------------------------------------------------

_VALID_BLAME_TARGETS = frozenset({
    "implementation", "validation", "feature_spec",
    "infrastructure", "external", "test_flaky", "unknown",
})

_VALID_RECOMMENDED_ACTIONS = frozenset({
    # Original F058 vocabulary
    "fix_code", "fix_test", "clarify_spec", "retry",
    "investigate", "escalate",
    # R10-009 wiring vocabulary used by ``OrchestrationLoop._maybe_run_rca``
    # (run_loop.py). Lets the RCA agent return loop-level routing
    # recommendations directly, without a translation layer in the loop.
    "fix_implementation", "decompose", "research", "mark_needs_human", "skip",
})

# Actions that propose a fix (require root_cause to be present)
_FIX_ACTIONS = frozenset({
    "fix_code", "fix_test", "clarify_spec",
    "fix_implementation",
})

RCA_SYSTEM_PROMPT = (
    "You are a Root Cause Analysis (RCA) agent following the Systematic Debugging Protocol.\n\n"
    "IRON LAW: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.\n\n"
    "You MUST complete all four phases in order:\n\n"
    "## Phase 1: Root Cause Investigation (MANDATORY)\n"
    "Answer ALL of these questions before proceeding:\n"
    "- What is the exact error message or unexpected behavior?\n"
    "- What was the expected behavior vs. actual behavior?\n"
    "- What code/component is involved in the failure?\n"
    "- What inputs/state led to this failure?\n"
    "- Is this reproducible? Under what conditions?\n"
    "- What changed recently that might have caused this?\n\n"
    "## Phase 2: Hypothesis Formation\n"
    "- Form a hypothesis about the root cause\n"
    "- Identify evidence supporting this hypothesis\n\n"
    "## Phase 3: Fix Recommendation\n"
    "- Recommend a fix that addresses the root cause\n"
    "- Ensure the fix prevents recurrence\n\n"
    "## Phase 4: Verification Plan\n"
    "- Describe tests to verify the fix\n"
    "- Confirm no new issues would be introduced\n\n"
    "You MUST respond with a JSON block containing:\n"
    '  - "blame_target": one of implementation, validation, feature_spec, '
    "infrastructure, external, test_flaky, unknown\n"
    '  - "recommended_action": one of fix_code, fix_test, clarify_spec, '
    "retry, investigate, escalate\n"
    '  - "root_cause": a clear description of the root cause (REQUIRED for fix actions)\n'
    '  - "investigation": object with Phase 1 answers\n'
    '  - "hypothesis": your hypothesis about the cause\n'
    '  - "verification_plan": how to verify the fix\n\n'
    "CRITICAL: If you cannot identify a root cause, set recommended_action to "
    '"investigate" -- NEVER propose a fix without a root cause.\n\n'
    "Wrap the JSON in a ```json code fence."
)


def parse_rca_result(response_text: str) -> dict[str, str]:
    """Parse RCA agent response to extract blame_target and recommended_action.

    Looks for a JSON block (inside ```json fences or inline) in the response
    text and extracts the blame_target, recommended_action, root_cause,
    investigation, hypothesis, and verification_plan fields.

    Enforces the Systematic Debugging Protocol (F106):
    - Fix actions (fix_code, fix_test, clarify_spec) require a non-empty
      root_cause. If root_cause is missing, the action is downgraded to
      "investigate".

    Returns a dict with at least blame_target and recommended_action.
    Falls back to defaults ("unknown" / "investigate") if parsing fails.
    """
    defaults = {
        "blame_target": "unknown",
        "recommended_action": "investigate",
    }

    # Try fenced JSON first: ```json ... ```
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", response_text, re.DOTALL)
    json_str = fenced.group(1) if fenced else None

    # Fall back to inline JSON: { ... }
    if json_str is None:
        inline = re.search(r"\{[^{}]*\"blame_target\"[^{}]*\}", response_text, re.DOTALL)
        json_str = inline.group(0) if inline else None

    if json_str is None:
        return defaults

    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return defaults

    if not isinstance(parsed, dict):
        return defaults

    result: dict[str, str] = {}

    blame = parsed.get("blame_target", "unknown")
    result["blame_target"] = blame if blame in _VALID_BLAME_TARGETS else "unknown"

    action = parsed.get("recommended_action", "investigate")
    result["recommended_action"] = action if action in _VALID_RECOMMENDED_ACTIONS else "investigate"

    root_cause = parsed.get("root_cause")
    if root_cause:
        result["root_cause"] = str(root_cause)

    # F106: Enforce root-cause-before-fix rule
    # Fix actions require a root cause to be identified first.
    if result["recommended_action"] in _FIX_ACTIONS and not root_cause:
        logger.warning(
            "RCA proposed fix action '%s' without root cause — "
            "downgrading to 'investigate'",
            result["recommended_action"],
        )
        result["recommended_action"] = "investigate"

    # Extract Phase 1 investigation details if present
    investigation = parsed.get("investigation")
    if investigation:
        result["investigation"] = (
            json.dumps(investigation) if isinstance(investigation, dict) else str(investigation)
        )

    # Extract Phase 2 hypothesis if present
    hypothesis = parsed.get("hypothesis")
    if hypothesis:
        result["hypothesis"] = str(hypothesis)

    # Extract Phase 4 verification plan if present
    verification_plan = parsed.get("verification_plan")
    if verification_plan:
        result["verification_plan"] = str(verification_plan)

    return result


async def spawn_rca_agent(
    *,
    project_id: str,
    failure_evidence: str,
    error_type: str,
    error_message: str,
    target_type: str | None = None,
    target_id: str | None = None,
    parent_run_id: str | None = None,
    max_turns: int = 10,
    on_message: MessageCallback | None = None,
) -> SpawnResult:
    """Spawn an RCA (Root Cause Analysis) sub-agent.

    Analyzes a failure, determines the blame target and recommended action,
    and stores the results in the sub_agent_runs record.

    Args:
        project_id: Project this analysis belongs to.
        failure_evidence: Full failure output (test logs, error traces, etc.).
        error_type: Type of error (e.g. "test_failure", "build_failure").
        error_message: The primary error message.
        target_type: Optional target type (e.g. "task", "feature").
        target_id: Optional target ID (e.g. task or feature ID).
        parent_run_id: Optional parent agent run ID for hierarchy.
        max_turns: Maximum turns for the RCA agent (default: 10).
        on_message: Optional callback invoked for each message received.

    Returns:
        SpawnResult containing the execution result and agent run record,
        with rca_blame_target and rca_recommended_action populated.
    """
    from bob3 import db

    prompt = (
        f"Analyze the following failure using the Systematic Debugging Protocol.\n\n"
        f"Error Type: {error_type}\n"
        f"Error Message: {error_message}\n\n"
        f"Failure Evidence:\n{failure_evidence}\n\n"
        f"PHASE 1 CHECKLIST (complete ALL before proposing a fix):\n"
        f"- What is the exact error message or unexpected behavior?\n"
        f"- What was the expected behavior vs. actual behavior?\n"
        f"- What code/component is involved?\n"
        f"- What inputs/state led to this failure?\n"
        f"- Is this reproducible? Under what conditions?\n"
        f"- What changed recently that might have caused this?\n\n"
        f"After completing Phase 1, form a hypothesis (Phase 2), "
        f"recommend a fix (Phase 3), and describe a verification plan (Phase 4).\n\n"
        f"Respond with a JSON block containing blame_target, recommended_action, "
        f"root_cause, investigation, hypothesis, and verification_plan.\n\n"
        f"REMEMBER: No fix proposals without root cause identification first."
    )

    options = build_sub_agent_options(
        model=DEFAULT_SUB_AGENT_MODEL,
        max_turns=max_turns,
        system_prompt=RCA_SYSTEM_PROMPT,
    )

    # Spawn the sub-agent with purpose="rca_analyst"
    spawn_result = await spawn_sub_agent(
        project_id=project_id,
        purpose="rca_analyst",
        prompt=prompt,
        target_type=target_type,
        target_id=target_id,
        parent_run_id=parent_run_id,
        options=options,
        on_message=on_message,
    )

    # Parse RCA results from agent response
    if spawn_result.execution_result.is_error:
        rca = {"blame_target": "unknown", "recommended_action": "investigate"}
    else:
        rca = parse_rca_result(spawn_result.execution_result.text)

    # Store RCA results in the agent run record
    updated_run = db.update_agent_run(
        spawn_result.agent_run.id,
        rca_blame_target=rca["blame_target"],
        rca_recommended_action=rca["recommended_action"],
    )

    if updated_run is not None:
        spawn_result.agent_run = updated_run

    return spawn_result
