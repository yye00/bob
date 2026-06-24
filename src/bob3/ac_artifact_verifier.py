"""AC artifact-existence verifier — canonical entry point for bob3.

Pre-pytest pass MUST verify that every AC of the form
``pytest: <path>``, ``File exists: <path>``, ``File modified: <path>``,
or ``Function defined: <module>.<symbol>`` resolves to an actual
artifact. Missing artifact -> AC fails with reason
``ARTIFACT_MISSING:<path>``, never swallowed as a generic pytest
exit code.

Public API
----------
verify_ac_artifacts(acs, workspace) -> list[ArtifactMiss]
    Check every AC string and return a list of ArtifactMiss for failures.
    Raises ValueError when acs is not a list or workspace is None.
    Raises TypeError when any element of acs is not a string.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from bob3.verification.ac_artifact_check import (
    ArtifactMiss,
    verify_ac_artifacts as _verify_ac_artifacts,
)


def verify_ac_artifacts(
    acs: list[str],
    workspace: Union[str, Path],
) -> list[ArtifactMiss]:
    """Check every AC string and return a list of ArtifactMiss for failures.

    Recognized prefixes: ``pytest:``, ``File exists:``, ``File modified:``,
    ``File modified or created:``, ``Function defined:``.
    Unrecognized prefixes produce a miss with ``kind='unknown_prefix'``.

    Args:
        acs: List of acceptance criteria strings. Each item must be a str.
        workspace: Root directory of the project workspace. Paths in ACs
            are resolved relative to this directory. Must not be ``None``.

    Returns:
        A (possibly empty) list of :class:`ArtifactMiss` objects — one per
        failing AC. An empty list means all checked ACs resolved to real
        artifacts.

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

    return _verify_ac_artifacts(acs, Path(workspace))


__all__ = ["ArtifactMiss", "verify_ac_artifacts"]
