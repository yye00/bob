"""bob3.ac_verifier — AC artifact-existence verifier (F-R7-7422b3bb).

Pre-pytest pass MUST verify that every AC of the form
`pytest: <path>`, `File exists: <path>`, `File modified: <path>`,
or `Function defined: <module>.<symbol>` resolves to an actual
artifact. Missing artifact -> AC fails with reason
ARTIFACT_MISSING:<path>, never swallowed as a generic pytest
exit code.

Public API
----------
verify_artifact_existence(acs, workspace) -> list[ArtifactMiss]
    Check every AC string and return a list of ArtifactMiss for failures.
    Raises ValueError when acs is not a list or workspace is None.

ArtifactMiss
    Dataclass with fields: ac_text, expected_path, kind, reason.

ArtifactMissingError
    Raised by fail_feature_with_explicit_reason when misses are present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from bob3.verification.ac_artifact_check import (
    ArtifactMiss,
    ArtifactMissingError,
    fail_feature_with_explicit_reason,
    recognized_ac_prefixes,
    verify_ac_artifacts,
)
from bob3.verifier.shell_script_ac import handle_shell_script_ac


def demote_shell_script_integration_ac(
    criterion: str,
    workspace: Union[str, Path],
) -> tuple[bool, str] | None:
    """Pattern 9 — shell-script integration AC handler (F-R7-594).

    When an AC line starts with ``integration:`` and the body is a path to an
    existing, executable ``.sh`` or ``.bash`` file under *workspace*, demote
    the AC to PASS with a WARNING tagged ``F-R7-594``.

    Args:
        criterion: The AC criterion string to evaluate.
        workspace: Root directory of the project workspace.

    Returns:
        ``(True, "")``  — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC; caller
        should continue to the next pattern.

    Raises:
        ValueError: When *workspace* is ``None``.
        TypeError: When *criterion* is not a string.
    """
    if not isinstance(criterion, str):
        raise TypeError(
            f"criterion must be a str, got {type(criterion).__name__!r}"
        )
    if workspace is None:
        raise ValueError("workspace must not be None")
    return handle_shell_script_ac(criterion, Path(workspace))


def handle_shell_script_integration(
    criterion: str,
    workspace: Union[str, Path],
) -> tuple[bool, str] | None:
    """Pattern 9 — shell-script integration AC handler (F-R7-594).

    Alias for :func:`demote_shell_script_integration_ac` satisfying AC
    ``Function defined: bob3.ac_verifier.handle_shell_script_integration``.

    Args:
        criterion: The AC criterion string to evaluate.
        workspace: Root directory of the project workspace.

    Returns:
        ``(True, "")``  — AC demoted to PASS; script exists and is executable.
        ``(False, reason)`` — hard FAIL; script missing or not executable.
        ``None`` — criterion is not a shell-script integration AC.

    Raises:
        ValueError: When *workspace* is ``None``.
        TypeError: When *criterion* is not a string.
    """
    return demote_shell_script_integration_ac(criterion, workspace)


def verify_artifact_exists(
    acs: list[str],
    workspace: Union[str, Path],
) -> list[ArtifactMiss]:
    """Alias for verify_artifact_existence — satisfies AC 'Function defined: bob3.ac_verifier.verify_artifact_exists'."""
    return verify_artifact_existence(acs, workspace)


def verify_artifact_existence(
    acs: list[str],
    workspace: Union[str, Path],
) -> list[ArtifactMiss]:
    """Check every AC string and return a list of ArtifactMiss for failures.

    Pre-pytest pass: verifies every AC of the form ``pytest: <path>``,
    ``File exists: <path>``, ``File modified: <path>``, or
    ``Function defined: <module>.<symbol>`` resolves to an actual artifact.
    Missing artifact -> AC fails with reason ARTIFACT_MISSING:<path>.
    The failure is never swallowed as a generic pytest exit code.

    Args:
        acs: List of acceptance criteria strings.  Each item must be a str.
            Recognized prefixes: ``pytest:``, ``File exists:``,
            ``File modified:``, ``File modified or created:``,
            ``Function defined:``.  Unrecognized prefixes produce a miss
            with ``kind='unknown_prefix'``.
        workspace: Root directory of the project workspace.  Paths in ACs
            are resolved relative to this directory.  Must not be ``None``.

    Returns:
        A (possibly empty) list of :class:`~bob3.verification.ac_artifact_check.ArtifactMiss`
        objects — one per failing AC.  An empty list means all checked ACs
        resolved to real artifacts.

    Raises:
        ValueError: When ``acs`` is not a list or ``workspace`` is ``None``.
        TypeError: When any element of ``acs`` is not a string.
    """
    if not isinstance(acs, list):
        raise ValueError(
            f"acs must be a list of strings, got {type(acs).__name__!r}"
        )
    if workspace is None:
        raise ValueError("workspace must not be None")

    for i, item in enumerate(acs):
        if not isinstance(item, str):
            raise TypeError(
                f"acs[{i}] must be a str, got {type(item).__name__!r}: {item!r}"
            )

    return verify_ac_artifacts(acs, workspace)


__all__ = [
    "ArtifactMiss",
    "ArtifactMissingError",
    "demote_shell_script_integration_ac",
    "fail_feature_with_explicit_reason",
    "handle_shell_script_integration",
    "recognized_ac_prefixes",
    "verify_artifact_exists",
    "verify_artifact_existence",
]
