"""Subagent verification module — pytest observability mandate.

Feature: 772bd0b9-94ba-44f7-ba15-099aec9a795d

Locks the subagent observability mandate into the bob3 spec so future
bootstraps re-apply it. Provides forbid_pytest_stdout_redirection as the
canonical entry point for checking that subagent pytest invocations stream
output directly to the terminal.

Root cause (bob3 v.13 r10): subagent d8483d98 (PID 2135582) invoked
``python -m pytest tests/ -q --tb=short 2>&1 | grep -E "FAILED|ERROR" | head -10``,
which piped pytest stdout through a grep filter. The pytest child (PID 2164763)
ran 43+ min at 49% CPU with stdout fd pointing at a closed pipe — zero
observability for the entire session. The streaming output is the ONLY signal
that a run is not hung.

Forbidden patterns enforced:
- Redirecting stdout/stderr to /dev/null (``> /dev/null``, ``2>/dev/null``)
- Piping pytest output through any filter (``| grep``, ``| head``, ``| tail``, ...)
- Quiet-mode flags that suppress streaming progress (``-q``, ``--no-header``)
"""

from __future__ import annotations

from bob3.subagent_observability import forbid_pytest_stdout_redirection  # noqa: F401
from bob3.subagent_observability import validate_pytest_command


__all__ = [
    "forbid_pytest_stdout_redirection",
    "validate_pytest_command",
]
