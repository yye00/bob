"""bob75.verifier — Pattern 9 shell-script integration AC handler (F-R7-594).

Public API
----------
demote_shell_script_ac(criterion, workspace) -> tuple[bool, str] | None
    When an ``integration:`` AC body is a path to an existing, executable
    ``.sh`` or ``.bash`` file, demote the AC to PASS with a WARNING tagged
    ``F-R7-594``.

    Returns:
        ``(True, "")``        — PASS: script exists and is executable.
        ``(False, reason)``   — FAIL: script missing or not executable.
        ``None``              — not a shell-script integration AC; caller continues.
"""

from __future__ import annotations

import pathlib

from bob3.verifier.shell_script_ac import handle_shell_script_ac


def demote_shell_script_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9 shell-script integration AC handler (F-R7-594).

    When an ``integration:`` AC body is a path to an existing, executable
    ``.sh`` or ``.bash`` file, demote the AC to PASS-with-warning (F-R7-594).

    Args:
        criterion: The raw acceptance-criteria string.
        workspace: Root directory of the project workspace.

    Returns:
        ``(True, "")``      — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None``            — criterion is not a shell-script integration AC.

    Raises:
        TypeError:  When *criterion* is not a str or *workspace* is not Path-like.
        ValueError: When *workspace* is ``None``.
    """
    if not isinstance(criterion, str):
        raise TypeError(
            f"criterion must be a str, got {type(criterion).__name__!r}"
        )
    if workspace is None:
        raise ValueError("workspace must not be None")
    if not isinstance(workspace, pathlib.Path):
        workspace = pathlib.Path(workspace)

    return handle_shell_script_ac(criterion, workspace)


__all__ = ["demote_shell_script_ac"]
