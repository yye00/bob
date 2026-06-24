"""bob.ac_handler — acceptance-criteria handler dispatch (Pattern 9 and siblings).

Public API
----------
handle_integration_ac(criterion, workspace) -> tuple[bool, str] | None
    Pattern 9 (F-R7-594): primary entry point — when an 'integration:' AC body
    is a path to an existing, executable .sh or .bash file, demote the AC to
    PASS with a WARNING.  Returns (True, '') on PASS-demotion, (False, reason)
    when the script is missing or non-executable, and None when the criterion
    is not a shell-script integration AC (caller should continue to the next
    pattern).

demote_shell_script_integration(criterion, workspace) -> tuple[bool, str] | None
demote_shell_script_integration_ac(criterion, workspace) -> tuple[bool, str] | None
    Aliases for ``handle_integration_ac`` kept for backward compatibility.
"""

from __future__ import annotations

import pathlib

from bob.verifier.shell_script_ac import handle_shell_script_ac


def handle_integration_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9 shell-script integration AC handler (F-R7-594).

    When an AC line starts with 'integration:' and the body is a path to an
    existing, executable .sh or .bash file, demote the AC to PASS with a
    WARNING log line tagged 'F-R7-594'.

    Returns:
        ``(True, "")``  — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller
        should continue to the next pattern.
    """
    return handle_shell_script_ac(criterion, workspace)


def demote_shell_script_integration(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9 shell-script integration AC handler (F-R7-594).

    Alias for :func:`handle_integration_ac`.
    """
    return handle_integration_ac(criterion, workspace)


#: Canonical alias expected by the AC verifier (F-R7-594).
demote_shell_script_integration_ac = demote_shell_script_integration

__all__ = [
    "handle_integration_ac",
    "demote_shell_script_integration",
    "demote_shell_script_integration_ac",
]
