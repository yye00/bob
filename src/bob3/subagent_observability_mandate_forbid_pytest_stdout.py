"""Subagent observability mandate — forbid pytest stdout redirection to /dev/null.

Feature: 5c8a28ea-42e3-47d9-bb56-8f1e4a8234c6

Root cause (bob3 v.13 r10): subagent d8483d98 (PID 2135582) invoked
``python -m pytest tests/ -q --tb=short 2>&1 | grep -E "FAILED|ERROR" | head -10``,
which piped pytest stdout through a grep filter. The pipe buffers output until
the run completes, so no output appeared for 43+ minutes while pytest ran at
49% CPU. The streaming output is the ONLY signal that a run is not hung.

This module is the canonical entry point that locks this rule into the bob3 v.17
spec so future bootstraps re-apply it. The underlying validation logic lives in
``bob3.subagent_observability.validate_pytest_command``.
"""

from __future__ import annotations

from bob3.subagent_observability import validate_pytest_command

__all__ = ["subagent_observability_mandate_forbid_pytest_stdout"]


def subagent_observability_mandate_forbid_pytest_stdout(
    command: str,
) -> tuple[bool, str]:
    """Validate a pytest command against the subagent observability mandate.

    Forbidden patterns that create a silent hung process with zero observability:

    - Redirecting stdout/stderr to /dev/null (``> /dev/null``, ``2>/dev/null``)
    - Piping pytest output through a filter (``| grep``, ``| head``, ``| tail``, ...)
    - Quiet-mode flags that suppress streaming progress (``-q``, ``--no-header``)

    Safe invocations stream output directly to the terminal, e.g.:
    ``python -m pytest tests/test_myfeature.py -v``

    Parameters
    ----------
    command:
        Shell command string to validate.

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` when the command is safe.
        ``(False, reason)`` when a forbidden pattern is detected, where *reason*
        describes the violation so the caller can surface an actionable error.
    """
    return validate_pytest_command(command)
