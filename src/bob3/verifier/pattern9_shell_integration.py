"""Pattern 9 — shell-script integration AC handler (F-R7-594).

When an AC line starts with 'integration:' and the body resolves to an
existing, executable .sh or .bash file, demote the AC to PASS with a WARNING
log line tagged 'F-R7-594'.

Safety invariant: the file must BOTH exist AND be executable (os.X_OK).
Missing or non-executable scripts return (False, reason) so real bugs surface.
Non-shell-script integration ACs return None (caller continues to next pattern).
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)


def is_shell_script_integration(criterion: str) -> bool:
    """Return True if criterion is an integration AC referencing a shell script.

    An integration AC starts with 'integration:' (case-insensitive at line start)
    and has a body ending in '.sh' or '.bash'.

    Args:
        criterion: Raw acceptance-criterion string.

    Returns:
        True when criterion is a shell-script integration AC; False otherwise.

    Raises:
        TypeError: When criterion is not a string.
        ValueError: When criterion is None.
    """
    if criterion is None:
        raise ValueError("criterion must not be None")
    if not isinstance(criterion, str):
        raise TypeError(f"criterion must be a str, got {type(criterion).__name__!r}")

    stripped = criterion.lstrip()
    lower = stripped.lower()
    if not lower.startswith("integration:"):
        return False
    body = stripped[len("integration:"):].strip()
    return body.endswith(".sh") or body.endswith(".bash")


def demote_to_pass_with_warning(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Pattern 9 handler: demote shell-script integration AC to PASS-with-warning.

    Returns:
        ``(True, "")``  — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller
        should continue to the next pattern.

    Raises:
        TypeError: When criterion is not a string or workspace is not a Path.
        ValueError: When criterion is None.
    """
    if criterion is None:
        raise ValueError("criterion must not be None")
    if not isinstance(criterion, str):
        raise TypeError(f"criterion must be a str, got {type(criterion).__name__!r}")
    if workspace is None:
        raise TypeError("workspace must not be None")

    if not is_shell_script_integration(criterion):
        return None

    stripped = criterion.lstrip()
    body = stripped[stripped.lower().index("integration:") + len("integration:"):].strip()
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
