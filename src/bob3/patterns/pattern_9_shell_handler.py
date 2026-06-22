"""bob3.patterns.pattern_9_shell_handler — Pattern 9 shell-script AC handler (F-R7-594).

When an AC line starts with 'integration:' and the body is a path matching
``**/*.sh`` or ``**/*.bash`` that exists AND is executable (mode 0o755 /
os.X_OK), demote the AC to PASS and emit a WARNING tagged F-R7-594.

Safety invariants:
  - Missing script → (False, reason).  Real missing-script bugs still fail.
  - Non-executable script → (False, reason).
  - Non-shell body → None.  Falls through to the next handler (pytest path).
  - Empty / blank criterion → ValueError.
  - Criterion without 'integration:' prefix → ValueError.
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)

_SHELL_EXTENSIONS = (".sh", ".bash")


def demote_shell_script_ac(
    criterion: str,
    workspace: pathlib.Path | str,
) -> tuple[bool, str] | None:
    """Evaluate a single integration AC for the shell-script demotion rule.

    Args:
        criterion: The raw AC string, e.g. ``"integration: tools/deploy.sh"``.
        workspace: Repository root used to resolve relative script paths.

    Returns:
        ``(True, "")`` — PASS: script exists and is executable (F-R7-594 warning emitted).
        ``(False, reason)`` — FAIL: script path matched but file is missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller should continue.

    Raises:
        ValueError: If *criterion* is empty/blank or contains no 'integration:' prefix
                    at all (i.e. completely invalid input rather than a non-matching AC).
    """
    if not criterion or not criterion.strip():
        raise ValueError("criterion must not be empty or blank")

    criterion_stripped = criterion.strip()
    criterion_lower = criterion_stripped.lower()

    if not criterion_lower.startswith("integration:"):
        raise ValueError(
            f"criterion does not start with 'integration:': {criterion_stripped!r}"
        )

    body = criterion_stripped[len("integration:"):].strip()

    if not any(body.endswith(ext) for ext in _SHELL_EXTENSIONS):
        return None

    workspace = pathlib.Path(workspace)
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


__all__ = ["demote_shell_script_ac"]
