"""Pattern 9 — shell-script integration AC handler — demote to PASS-with-warning (F-R7-594).

When an AC line starts with ``integration:`` and the body is a path to an
existing, executable ``.sh`` or ``.bash`` file, demote the AC to PASS with a
WARNING tagged ``F-R7-594``.

Safety invariant: the file must BOTH exist AND be executable (os.X_OK).
Missing or non-executable scripts return ``(False, reason)`` so real bugs
still surface.  Non-shell-script bodies return ``None`` so the caller falls
through to the next pattern.
"""

from __future__ import annotations

import pathlib

from bob.verifier.shell_script_ac import handle_shell_script_ac


def pattern_9_shell_script_integration_ac_handler_demote_pass(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9 shell-script integration AC handler (F-R7-594).

    Demotes a shell-script integration AC to PASS-with-warning when the
    referenced script exists and is executable.

    Returns:
        ``(True, "")``  — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller
        should continue to the next pattern.
    """
    return handle_shell_script_ac(criterion, workspace)


__all__ = ["pattern_9_shell_script_integration_ac_handler_demote_pass"]
