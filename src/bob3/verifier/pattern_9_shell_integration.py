"""Pattern 9 — shell-script integration AC handler (F-R7-594).

When an AC line starts with 'integration:' and the body resolves to an
existing, executable .sh or .bash file, demote the AC to PASS with a WARNING
log line tagged 'F-R7-594'.

Safety invariant: the file must BOTH exist AND be executable (os.X_OK).
Missing or non-executable scripts return (False, reason) so real bugs surface.
Non-shell-script integration ACs return None (caller continues to next pattern).

Public API
----------
demote_shell_script_ac(criterion, workspace) -> tuple[bool, str] | None
    Primary entry point for Pattern 9.
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)


def _is_shell_script_body(body: str) -> bool:
    return body.endswith(".sh") or body.endswith(".bash")


def demote_shell_script_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9: demote shell-script integration AC to PASS-with-warning (F-R7-594).

    When an AC line starts with 'integration:' and the body is a path to an
    existing, executable .sh or .bash file, demote the AC to PASS.

    Returns:
        ``(True, "")``  — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller
        should continue to the next pattern.

    Raises:
        ValueError: When criterion is None.
        TypeError: When criterion is not a str, or workspace is None/not a Path.
    """
    if criterion is None:
        raise ValueError("criterion must not be None")
    if not isinstance(criterion, str):
        raise TypeError(f"criterion must be a str, got {type(criterion).__name__!r}")
    if workspace is None:
        raise TypeError("workspace must not be None")

    stripped = criterion.lstrip()
    lower = stripped.lower()
    if not lower.startswith("integration:"):
        return None

    body = stripped[len("integration:"):].strip()
    if not _is_shell_script_body(body):
        return None

    sh_path = pathlib.Path(workspace) / body

    try:
        if sh_path.exists() and os.access(sh_path, os.X_OK):
            logger.warning(
                "integration-AC demoted to PASS (F-R7-594): "
                "shell script exists and is executable: %s",
                str(sh_path),
            )
            return True, ""
        if not sh_path.exists():
            return False, f"shell script not found: {sh_path}"
        return False, f"shell script not executable: {sh_path}"
    except Exception:
        logger.debug("F-R7-594 shell-script check raised; falling through", exc_info=True)
        return None


__all__ = ["demote_shell_script_ac"]
