"""Subagent observability mandate — forbid pytest stdout redirection.

Feature: 55010d1c-e1cc-412b-9dff-f1cf355cd9a5

Canonical module that locks the subagent observability rule into the bob spec
so future bootstraps re-apply it. All validation logic delegates to
``bob.subagent_observability``.

Root cause: a subagent invoked pytest with stdout piped through a grep filter,
producing no output for 43+ minutes while pytest ran at 49% CPU.  The streaming
output is the ONLY signal that a run is not hung.

Forbidden patterns:
- Redirecting stdout/stderr to /dev/null (``> /dev/null``, ``2>/dev/null``)
- Piping pytest output through a filter (``| grep``, ``| head``, ``| tail``, ...)
- Quiet-mode flags that suppress streaming progress (``-q``, ``--no-header``)
"""

from __future__ import annotations

from bob.subagent_observability import forbid_pytest_stdout_redirection  # noqa: F401
from bob.subagent_observability import validate_pytest_command  # noqa: F401
from bob.subagent_observability import validate_pytest_output_streaming  # noqa: F401

__all__ = [
    "forbid_pytest_stdout_redirection",
    "validate_pytest_command",
    "validate_pytest_output_streaming",
]
