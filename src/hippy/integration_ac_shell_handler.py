"""hippy.integration_ac_shell_handler — Pattern 9 shell-script integration AC handler (F-R7-594).

Thin hippy-side façade over :mod:`bob.integration_shell_script_demoter`.

When an ``integration:`` acceptance criterion body is a path to an existing,
executable ``.sh``/``.bash`` file, the AC is demoted to PASS with a WARNING
tagged ``F-R7-594`` rather than being hard-failed by Pattern 8 (which expects a
dotted Python module path).

Motivating defect
-----------------
Two prior-generation features NH'd at attempts=3 on a single AC each:
  - 51fc8cb1: ``integration: tools/spawn_next_generation.sh``
  - 949e97e1: ``integration: tools/self_heal.sh``
Both scripts exist on disk (mode 755) but Pattern 8 gave up on a bare
shell-script path and hard-failed the feature.

Safety invariant
----------------
The referenced file must BOTH exist AND be executable.  Real missing-script
bugs still fail (file absent OR not executable).  Non-script integration bodies
return ``None`` so the caller continues to Pattern 8.
"""

from __future__ import annotations

import pathlib

from bob.integration_shell_script_demoter import (
    demote_shell_script_integration_ac as _demote,
    is_executable_shell_script_integration as _is_executable,
)


def demote_shell_integration_ac(
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
    return _demote(criterion, workspace)


def is_executable_shell_script_integration(
    criterion: str,
    workspace: pathlib.Path,
) -> bool:
    """Return True iff *criterion* names an existing, executable shell script.

    Raises:
        TypeError: if *criterion* is not a string or *workspace* is None.
    """
    return _is_executable(criterion, workspace)


__all__ = [
    "demote_shell_integration_ac",
    "is_executable_shell_script_integration",
]
