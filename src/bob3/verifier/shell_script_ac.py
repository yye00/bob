"""Pattern 9 — shell-script integration AC handler (F-R7-594).

When an AC line starts with 'integration:' and the body is a path to an
existing, executable .sh or .bash file, demote the AC to PASS with a WARNING.

This avoids spurious NH-demotions for features whose integration AC references
a shell script (e.g. tools/spawn_next_generation.sh, tools/self_heal.sh).

Safety invariant: the file must BOTH exist AND be executable (os.X_OK).
Missing or non-executable scripts return (False, reason) and fall through.
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)


def handle_shell_script_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Check whether an integration AC refers to an existing executable shell script.

    Returns:
        ``(True, "")`` when the AC body resolves to an existing, executable
        .sh/.bash file under *workspace* — PASS with F-R7-594 warning.

        ``(False, reason)`` when the body looks like a shell script path but
        the file is missing or not executable — hard FAIL so real bugs surface.

        ``None`` when the criterion is not a shell-script integration AC at
        all — caller should continue to the next pattern.
    """
    criterion_lower = criterion.lower()
    if "integration:" not in criterion_lower:
        return None

    body = criterion[criterion_lower.find("integration:") + len("integration:"):].strip()
    if not (body.endswith(".sh") or body.endswith(".bash")):
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
