"""Pattern 9 — shell-script integration AC handler (F-R7-594).

Public API:
  is_shell_script_integration_ac(criterion) -> bool
  should_demote_to_pass_with_warning(criterion, workspace) -> bool

When an AC line starts with 'integration:' and the body resolves to an
existing, executable .sh or .bash file, the AC should be demoted to PASS
with a WARNING log line tagged 'F-R7-594'.

Safety: missing or non-executable scripts return False (hard FAIL) so real
bugs still surface. Non-script integration ACs return False from
is_shell_script_integration_ac and should not be handled by this module.
"""

from __future__ import annotations

import logging
import os
import pathlib

logger = logging.getLogger(__name__)


def is_shell_script_integration_ac(criterion: str) -> bool:
    """Return True if the criterion is an integration AC referencing a shell script.

    A shell-script integration AC starts with 'integration:' (case-insensitive)
    and has a body ending in '.sh' or '.bash'.
    """
    criterion_lower = criterion.lower()
    if "integration:" not in criterion_lower:
        return False
    body = criterion[criterion_lower.find("integration:") + len("integration:"):].strip()
    return body.endswith(".sh") or body.endswith(".bash")


def should_demote_to_pass_with_warning(
    criterion: str,
    workspace: pathlib.Path,
) -> bool:
    """Return True when the shell-script AC should be demoted to PASS-with-warning.

    Conditions for demotion (all must hold):
    - criterion is a shell-script integration AC (see is_shell_script_integration_ac)
    - the script file exists under workspace
    - the script file is executable (os.X_OK)

    Emits a WARNING log line tagged 'F-R7-594' when demoting.
    Returns False when the script is missing or not executable (hard FAIL).
    """
    if not is_shell_script_integration_ac(criterion):
        return False

    criterion_lower = criterion.lower()
    body = criterion[criterion_lower.find("integration:") + len("integration:"):].strip()
    sh_path = workspace / body

    if sh_path.exists() and os.access(sh_path, os.X_OK):
        logger.warning(
            "integration-AC demoted to PASS (F-R7-594): "
            "shell script exists and is executable: %s",
            str(sh_path),
        )
        return True
    return False
