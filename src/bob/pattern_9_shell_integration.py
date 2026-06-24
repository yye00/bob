"""Pattern 9 — shell-script integration AC handler (F-R7-594).

Public re-export of :func:`bob.verifier.shell_script_ac.handle_shell_script_ac`
under the canonical name ``demote_shell_script_ac`` required by the feature spec.

When an AC line starts with ``integration:`` and the body is a path to an
existing, executable ``.sh`` or ``.bash`` file, the AC is demoted to PASS
with a WARNING tagged ``F-R7-594``.

Safety invariant: the file must BOTH exist AND be executable (os.X_OK).
Missing or non-executable scripts return ``(False, reason)`` so real bugs
still surface.  Non-shell-script bodies return ``None`` so the caller falls
through to the next pattern.
"""

from __future__ import annotations

import pathlib

from bob.verifier.shell_script_ac import handle_shell_script_ac


def demote_shell_script_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Demote a shell-script integration AC to PASS-with-warning.

    Delegates to :func:`bob.verifier.shell_script_ac.handle_shell_script_ac`.

    Returns:
        ``(True, "")`` — PASS: script exists and is executable (F-R7-594 warning emitted).
        ``(False, reason)`` — FAIL: script path matched but file is missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller should continue.
    """
    return handle_shell_script_ac(criterion, workspace)


__all__ = ["demote_shell_script_ac"]
