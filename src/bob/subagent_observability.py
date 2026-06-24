"""Subagent observability mandate — pytest command validation.

Provides validate_pytest_command to detect forbidden patterns that suppress
pytest output and create silent, hung processes with zero observability.

Root cause (bob v.13 r10): a subagent invoked pytest with stdout piped into
grep, producing no output for 43+ minutes while pytest ran at 49% CPU.
The streaming output is the ONLY signal that a run is not hung.
"""

from __future__ import annotations

import re


# Patterns that redirect or suppress pytest output entirely.
_REDIRECT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r">\s*/dev/null"),
        "stdout redirected to /dev/null — all pytest output is discarded",
    ),
    (
        re.compile(r"2>\s*/dev/null"),
        "stderr redirected to /dev/null — error output is discarded",
    ),
    (
        re.compile(r"2>&1\s*>\s*/dev/null"),
        "stdout+stderr redirected to /dev/null — all output is discarded",
    ),
]

# Patterns that pipe pytest output through a filter (captures until run ends).
_PIPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\|\s*(grep|head|tail|awk|sed|tee)\b"),
        "pytest stdout piped into a filter — output is buffered until run ends, creating a silent hung process",
    ),
]

# Flags that suppress progress output.
_QUIET_FLAGS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?<!\S)-q(?!\S)"),
        "quiet flag -q suppresses pytest progress output — streaming is the only hung-process signal",
    ),
    (
        re.compile(r"--no-header"),
        "--no-header suppresses pytest output — streaming is the only hung-process signal",
    ),
]


def validate_pytest_command(command: str) -> tuple[bool, str]:
    """Return (True, "") if *command* is a safe pytest invocation, else (False, reason).

    A safe invocation streams output directly to the terminal — no pipes into
    filters, no redirections to /dev/null, and no quiet-mode flags.

    Args:
        command: Shell command string to validate, e.g.
            ``"python -m pytest tests/test_foo.py -v"``.

    Returns:
        A two-tuple ``(ok, message)`` where *ok* is ``True`` when the command
        is safe and ``False`` otherwise.  When *ok* is ``False``, *message*
        describes the forbidden pattern so callers can surface an actionable
        error to the sub-agent.
    """
    if not command:
        return False, "empty command"

    for pattern, reason in _REDIRECT_PATTERNS:
        if pattern.search(command):
            return False, f"Forbidden redirect: {reason}"

    for pattern, reason in _PIPE_PATTERNS:
        if pattern.search(command):
            return False, f"Forbidden pipe: {reason}"

    for pattern, reason in _QUIET_FLAGS:
        if pattern.search(command):
            return False, f"Forbidden flag: {reason}"

    return True, ""


def validate_pytest_invocation(command: str) -> tuple[bool, str]:
    """Alias for validate_pytest_command — required by bob v.17 spec AC.

    See validate_pytest_command for full documentation.
    """
    return validate_pytest_command(command)


def validate_pytest_output_streaming(command: str) -> tuple[bool, str]:
    """Validate that a pytest command preserves full streaming output.

    Returns (True, "") when the command streams output directly to the terminal
    and (False, reason) when any forbidden pattern is detected that would suppress
    or capture output, creating a silent hung process with zero observability.

    Forbidden patterns:
    - Redirecting stdout/stderr to /dev/null (``> /dev/null``, ``2>/dev/null``)
    - Piping pytest output through a filter (``| grep``, ``| head``, ``| tail``, ...)
    - Quiet-mode flags that suppress streaming progress (``-q``, ``--no-header``)

    Args:
        command: Shell command string to validate.

    Returns:
        ``(True, "")`` when the command preserves streaming output.
        ``(False, reason)`` when a forbidden pattern is detected.

    Raises:
        ValueError: When *command* is None (invalid input must not silently succeed).
    """
    if command is None:
        raise ValueError("command must be a string, not None")
    return validate_pytest_command(command)


def forbid_pytest_stdout_redirection(command: str) -> tuple[bool, str]:
    """Enforce the subagent observability mandate for pytest commands.

    Raises ValueError for None input; returns (False, reason) for empty string
    or any command containing forbidden patterns; returns (True, "") for safe
    invocations that stream output directly to the terminal.

    Forbidden patterns that create a silent hung process with zero observability:
    - Redirecting stdout/stderr to /dev/null (``> /dev/null``, ``2>/dev/null``)
    - Piping pytest output through a filter (``| grep``, ``| head``, ``| tail``, ...)
    - Quiet-mode flags that suppress streaming progress (``-q``, ``--no-header``)

    Args:
        command: Shell command string to validate.

    Returns:
        ``(True, "")`` when the command is safe to run.
        ``(False, reason)`` when a forbidden pattern is detected.

    Raises:
        ValueError: When *command* is None (invalid input must not silently succeed).
    """
    if command is None:
        raise ValueError("command must be a string, not None")
    return validate_pytest_command(command)
