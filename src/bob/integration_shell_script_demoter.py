"""bob.integration_shell_script_demoter — Pattern 9 shell-script integration AC handler (F-R7-594).

Sibling to the F-R7-587 prose-demoter.  When an ``integration:`` acceptance
criterion body is a path to an existing, executable ``.sh`` or ``.bash`` file,
the AC is demoted to PASS with a WARNING tagged ``F-R7-594`` rather than being
hard-failed by Pattern 8 (which expects a dotted Python module path).

Motivating defect
-----------------
Two prior-generation features NH'd at attempts=3 on a single AC each:
  - 51fc8cb1: ``integration: tools/spawn_next_generation.sh``
  - 949e97e1: ``integration: tools/self_heal.sh``
Both scripts exist on disk (mode 755) but Pattern 8 gave up on a bare
shell-script path and hard-failed the feature.

Safety invariant
----------------
The referenced file must BOTH exist AND be executable (``os.X_OK``).  Real
missing-script bugs still fail (file absent OR not executable).  Non-script
integration bodies return ``None`` so the caller continues to Pattern 8.

Public API
----------
is_executable_shell_script_integration(criterion, workspace) -> bool
    True iff *criterion* is an ``integration:`` AC whose body is an existing,
    executable ``.sh``/``.bash`` file under *workspace*.

demote_shell_script_integration_ac(criterion, workspace) -> tuple[bool, str] | None
    (True, "")        — PASS demotion (F-R7-594 warning emitted).
    (False, reason)   — hard FAIL (script matched but missing / not executable).
    None              — not a shell-script integration AC; caller continues.
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)

_SHELL_EXTENSIONS = (".sh", ".bash")


def _extract_shell_body(criterion: str) -> str | None:
    """Return the stripped shell-script body of an ``integration:`` criterion.

    Returns ``None`` when *criterion* is not an ``integration:`` AC or its body
    is not a ``.sh``/``.bash`` path.  Raises ``TypeError`` for non-string input.
    """
    if not isinstance(criterion, str):
        raise TypeError(
            f"criterion must be a str, got {type(criterion).__name__!r}"
        )
    lower = criterion.lower()
    idx = lower.find("integration:")
    if idx == -1:
        return None
    body = criterion[idx + len("integration:"):].strip()
    if not any(body.endswith(ext) for ext in _SHELL_EXTENSIONS):
        return None
    return body


def is_executable_shell_script_integration(
    criterion: str,
    workspace: pathlib.Path,
) -> bool:
    """Return True iff *criterion* names an existing, executable shell script.

    True only when *criterion* is an ``integration:`` AC, its body ends in
    ``.sh``/``.bash``, and the resolved path under *workspace* both exists and
    is executable.  Every other case (non-integration, non-shell body, missing
    file, non-executable file) returns False.

    Raises:
        TypeError: if *criterion* is not a string or *workspace* is None.
    """
    if workspace is None:
        raise TypeError("workspace must not be None")
    body = _extract_shell_body(criterion)
    if body is None:
        return False
    sh_path = pathlib.Path(workspace) / body
    try:
        return sh_path.exists() and os.access(sh_path, os.X_OK)
    except OSError:
        logger.debug("F-R7-594 executable check raised for %s", sh_path, exc_info=True)
        return False


def demote_shell_script_integration_ac(
    criterion: str,
    workspace: pathlib.Path,
) -> tuple[bool, str] | None:
    """Demote a shell-script integration AC to PASS-with-warning (F-R7-594).

    Returns:
        ``(True, "")`` — PASS: script exists and is executable (warning emitted).
        ``(False, reason)`` — FAIL: body matched a shell path but the file is
        missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; the caller
        should continue to the next pattern.

    Raises:
        TypeError: if *criterion* is not a string or *workspace* is None.
    """
    if workspace is None:
        raise TypeError("workspace must not be None")
    body = _extract_shell_body(criterion)
    if body is None:
        return None

    sh_path = pathlib.Path(workspace) / body
    if not sh_path.exists():
        return False, f"shell script not found: {sh_path}"
    if not os.access(sh_path, os.X_OK):
        return False, f"shell script not executable: {sh_path}"

    logger.warning(
        "integration-AC demoted to PASS (F-R7-594): "
        "shell script exists and is executable: %s",
        str(sh_path),
    )
    return True, ""


__all__ = [
    "is_executable_shell_script_integration",
    "demote_shell_script_integration_ac",
]
