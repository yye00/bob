"""bob3.verifier.ac_validator — AC dispatch for integration ACs (Pattern 9 integration point).

This module is the canonical verifier-package integration point for Pattern 9
(F-R7-594): shell-script integration AC demotion.

Public API
----------
check_integration_ac(criterion, workspace) -> tuple[bool, str] | None
    Dispatch an 'integration:' AC through Pattern 9 first.  Returns
    ``(True, "")`` on shell-script PASS-demotion, ``(False, reason)`` on
    hard FAIL, and ``None`` when the criterion is not handled by Pattern 9
    (caller should continue to the next handler).
"""

from __future__ import annotations

import pathlib

from bob3.verifier.pattern_9_shell_integration import demote_shell_script_ac


def check_integration_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Dispatch an integration AC through Pattern 9 (F-R7-594).

    Returns:
        ``(True, "")``  — AC demoted to PASS (shell script exists and is executable).
        ``(False, reason)`` — hard FAIL (script missing or not executable).
        ``None`` — not a shell-script integration AC; caller continues to next handler.
    """
    return demote_shell_script_ac(criterion, workspace)


__all__ = ["check_integration_ac", "demote_shell_script_ac"]
