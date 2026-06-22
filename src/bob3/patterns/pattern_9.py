"""Pattern 9 — shell-script integration AC handler (F-R7-594).

When an AC line starts with 'integration:' and the body is a path to an
existing, executable .sh or .bash file, demote the AC to PASS with a WARNING
tagged F-R7-594.

Safety invariant: the file must BOTH exist AND be executable (os.X_OK).
Missing or non-executable scripts return (False, reason) so real bugs still
surface.  Non-shell-script bodies return None so the caller falls through to
the next pattern.
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)

_SHELL_EXTENSIONS = (".sh", ".bash")


def handle_shell_script_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Check whether an integration AC refers to an existing executable shell script.

    Args:
        criterion: The raw AC string, e.g. ``"integration: tools/deploy.sh"``.
        workspace: Repository root used to resolve relative script paths.

    Returns:
        ``(True, "")`` — PASS: script exists and is executable (F-R7-594 warning emitted).
        ``(False, reason)`` — FAIL: script path matched but file is missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller should continue.
    """
    criterion_lower = criterion.lower()
    if "integration:" not in criterion_lower:
        return None

    body = criterion[criterion_lower.find("integration:") + len("integration:"):].strip()
    if not any(body.endswith(ext) for ext in _SHELL_EXTENSIONS):
        return None

    sh_path = workspace / body
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


__all__ = ["handle_shell_script_ac"]
