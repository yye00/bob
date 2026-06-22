"""External baseline runners for Aider and Claude Code.

Provides run_aider_baseline() and run_claude_code_baseline() which invoke
the respective CLI tools on a task, capture timing and exit status, and
emit the same F-105 telemetry schema that internal bob3 runs produce.

This lets the sweep orchestrator compare external tool performance against
bob3's internal ablation variants without any post-processing.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bob3.telemetry import emit_telemetry_line

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variant labels written into telemetry so sweep orchestrator can filter them
# ---------------------------------------------------------------------------

AIDER_VARIANT = "aider"
CLAUDE_CODE_VARIANT = "claude-code"

# Sentinel used when a tool is not installed on the system.
_NOT_INSTALLED = "not_installed"


@dataclass
class BaselineResult:
    """Outcome of a single external baseline run."""

    run_id: str
    variant: str
    completion_status: str  # "completed" | "failed" | "not_installed"
    duration_ms: int
    returncode: int | None
    stdout: str
    stderr: str
    tool_version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _probe_tool_version(cmd: list[str]) -> str | None:
    """Return the version string reported by a CLI tool, or None."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()[:200] or None
    except Exception:
        return None


def _run_tool(
    cmd: list[str],
    *,
    cwd: Path | str | None,
    env: dict[str, str] | None,
    timeout: int,
) -> tuple[int, str, str, int]:
    """Run cmd, return (returncode, stdout, stderr, duration_ms)."""
    effective_cwd = Path(cwd) if cwd else None
    effective_env = {**os.environ, **(env or {})}

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=effective_cwd,
            env=effective_env,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        return proc.returncode, proc.stdout, proc.stderr, duration_ms
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return -1, stdout, stderr + "\n[timeout]", duration_ms
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return -1, "", str(exc), duration_ms


def _make_run_id(variant: str, spec_id: str, seed: int) -> str:
    """Deterministic run_id derived from (variant, spec_id, seed)."""
    key = f"{variant}:{spec_id}:{seed}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_aider_baseline(
    prompt: str,
    *,
    workspace: Path | str | None = None,
    spec_id: str | None = None,
    spec_version: str | None = None,
    feature_id: str | None = None,
    seed: int = 0,
    attempt_number: int = 1,
    timeout: int = 300,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
    emit_telemetry: bool = True,
) -> BaselineResult:
    """Run Aider on *prompt* and emit an F-105 telemetry record.

    If aider is not installed, the result has completion_status="not_installed"
    and a telemetry record is still emitted so the orchestrator can account for
    missing baselines.

    Args:
        prompt: The coding task description to hand to Aider.
        workspace: Working directory for the aider invocation.
        spec_id: Sweep spec identifier recorded in telemetry.
        spec_version: Spec version string recorded in telemetry.
        feature_id: Feature ID recorded in telemetry.
        seed: Random seed recorded in telemetry (Aider ignores it).
        attempt_number: Attempt counter recorded in telemetry.
        timeout: Maximum seconds to wait for the aider process.
        extra_args: Additional CLI flags appended after the prompt.
        env: Extra environment variables merged into the subprocess env.
        emit_telemetry: When False, skip writing to run.jsonl (useful in tests).

    Returns:
        BaselineResult with outcome and captured output.
    """
    effective_spec_id = spec_id or "unknown"
    run_id = _make_run_id(AIDER_VARIANT, effective_spec_id, seed)

    if shutil.which("aider") is None:
        logger.warning("aider not found on PATH; recording not_installed telemetry")
        result = BaselineResult(
            run_id=run_id,
            variant=AIDER_VARIANT,
            completion_status=_NOT_INSTALLED,
            duration_ms=0,
            returncode=None,
            stdout="",
            stderr="",
            tool_version=None,
        )
        if emit_telemetry:
            emit_telemetry_line(
                run_id=run_id,
                variant=AIDER_VARIANT,
                spec_id=effective_spec_id,
                spec_version=spec_version,
                seed=seed,
                feature_id=feature_id,
                attempt_number=attempt_number,
                completion_status=_NOT_INSTALLED,
                duration_ms=0,
                model_id=None,
            )
        return result

    tool_version = _probe_tool_version(["aider", "--version"])

    cmd = ["aider", "--message", prompt, "--yes-always", "--no-git"]
    if extra_args:
        cmd.extend(extra_args)

    returncode, stdout, stderr, duration_ms = _run_tool(
        cmd,
        cwd=workspace,
        env=env,
        timeout=timeout,
    )

    completion_status = "completed" if returncode == 0 else "failed"

    result = BaselineResult(
        run_id=run_id,
        variant=AIDER_VARIANT,
        completion_status=completion_status,
        duration_ms=duration_ms,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        tool_version=tool_version,
    )

    if emit_telemetry:
        emit_telemetry_line(
            run_id=run_id,
            variant=AIDER_VARIANT,
            spec_id=effective_spec_id,
            spec_version=spec_version,
            seed=seed,
            feature_id=feature_id,
            attempt_number=attempt_number,
            completion_status=completion_status,
            duration_ms=duration_ms,
        )

    return result


def run_claude_code_baseline(
    prompt: str,
    *,
    workspace: Path | str | None = None,
    spec_id: str | None = None,
    spec_version: str | None = None,
    feature_id: str | None = None,
    seed: int = 0,
    attempt_number: int = 1,
    timeout: int = 300,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
    emit_telemetry: bool = True,
) -> BaselineResult:
    """Run the Claude Code CLI on *prompt* and emit an F-105 telemetry record.

    Invokes the ``claude`` CLI directly (not via the Python SDK) so that
    Claude Code's own token/cost accounting is independent of bob3's internal
    sub-agent budget tracking. The result is recorded with variant="claude-code"
    in run.jsonl so the sweep orchestrator can distinguish it from bob3 runs.

    If the ``claude`` CLI is not installed, the result has
    completion_status="not_installed".

    Args:
        prompt: The coding task description passed to the claude CLI.
        workspace: Working directory for the claude invocation.
        spec_id: Sweep spec identifier recorded in telemetry.
        spec_version: Spec version string recorded in telemetry.
        feature_id: Feature ID recorded in telemetry.
        seed: Random seed recorded in telemetry.
        attempt_number: Attempt counter recorded in telemetry.
        timeout: Maximum seconds to wait for the claude process.
        extra_args: Additional CLI flags appended to the command.
        env: Extra environment variables merged into the subprocess env.
        emit_telemetry: When False, skip writing to run.jsonl (useful in tests).

    Returns:
        BaselineResult with outcome and captured output.
    """
    effective_spec_id = spec_id or "unknown"
    run_id = _make_run_id(CLAUDE_CODE_VARIANT, effective_spec_id, seed)

    # "claude" is the Claude Code CLI binary name
    cli_binary = "claude"
    if shutil.which(cli_binary) is None:
        logger.warning("claude CLI not found on PATH; recording not_installed telemetry")
        result = BaselineResult(
            run_id=run_id,
            variant=CLAUDE_CODE_VARIANT,
            completion_status=_NOT_INSTALLED,
            duration_ms=0,
            returncode=None,
            stdout="",
            stderr="",
            tool_version=None,
        )
        if emit_telemetry:
            emit_telemetry_line(
                run_id=run_id,
                variant=CLAUDE_CODE_VARIANT,
                spec_id=effective_spec_id,
                spec_version=spec_version,
                seed=seed,
                feature_id=feature_id,
                attempt_number=attempt_number,
                completion_status=_NOT_INSTALLED,
                duration_ms=0,
            )
        return result

    tool_version = _probe_tool_version([cli_binary, "--version"])

    # Run in non-interactive mode using --print to get text output
    cmd = [cli_binary, "--print", prompt]
    if extra_args:
        cmd.extend(extra_args)

    returncode, stdout, stderr, duration_ms = _run_tool(
        cmd,
        cwd=workspace,
        env=env,
        timeout=timeout,
    )

    completion_status = "completed" if returncode == 0 else "failed"

    result = BaselineResult(
        run_id=run_id,
        variant=CLAUDE_CODE_VARIANT,
        completion_status=completion_status,
        duration_ms=duration_ms,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        tool_version=tool_version,
    )

    if emit_telemetry:
        emit_telemetry_line(
            run_id=run_id,
            variant=CLAUDE_CODE_VARIANT,
            spec_id=effective_spec_id,
            spec_version=spec_version,
            seed=seed,
            feature_id=feature_id,
            attempt_number=attempt_number,
            completion_status=completion_status,
            duration_ms=duration_ms,
        )

    return result
