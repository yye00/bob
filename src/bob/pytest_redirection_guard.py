"""Pytest redirection guard — forbid stdout/stderr suppression in pytest commands.

Locks the subagent observability mandate into a dedicated guard module so that
the rule survives bootstrap regeneration.

Root cause (feature dcd82948): a subagent invoked
``python -m pytest tests/ -q --tb=short 2>&1 | grep -E "FAILED|ERROR" | head -10``,
which piped pytest stdout into a grep filter that buffered until the
(never-arriving) end of the run. The pytest child ran 43+ minutes at 49% CPU
with a closed pipe on fd 1 — zero observability for the entire session.

The streaming output is the ONLY signal that a long-running test run is not
hung, so redirection to /dev/null, capture-only pipe filters, and quiet-mode
flags are all forbidden.

Delegates the detection logic to :mod:`bob.subagent_observability` so the rule
has a single source of truth.
"""

from __future__ import annotations

from bob.subagent_observability import validate_pytest_command

__all__ = [
    "forbid_pytest_stdout_redirection",
    "validate_pytest_command",
]


def forbid_pytest_stdout_redirection(command: str) -> tuple[bool, str]:
    """Enforce the subagent observability mandate for a pytest command.

    Args:
        command: Shell command string to validate, e.g.
            ``"python -m pytest tests/test_foo.py -v"``.

    Returns:
        ``(True, "")`` when the command streams output directly to the terminal
        and is safe to run. ``(False, reason)`` when a forbidden pattern is
        detected — redirection to ``/dev/null``, a capture-only pipe filter
        (``| grep``, ``| head``, ...), or a quiet-mode flag (``-q``,
        ``--no-header``).

    Raises:
        ValueError: When *command* is ``None`` — invalid input must raise
            rather than silently succeed.
    """
    if command is None:
        raise ValueError("command must be a string, not None")
    return validate_pytest_command(command)
