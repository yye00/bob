"""bob3.acceptance_criteria — AC artifact-existence verifier public API.

Pre-pytest pass MUST verify that every AC of the form
``pytest: <path>``, ``File exists: <path>``, ``File modified: <path>``,
or ``Function defined: <module>.<symbol>`` resolves to an actual
artifact. Missing artifact -> AC fails with reason ARTIFACT_MISSING:<path>,
never swallowed as a generic pytest exit code.

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
        acs: List of acceptance criteria strings. Each item must be a str.
            Recognized prefixes: ``pytest:``, ``File exists:``,
            ``File modified:``, ``File modified or created:``,
            ``Function defined:``. Unrecognized prefixes produce a miss
            with ``kind='unknown_prefix'``.
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

    return verify_ac_artifacts(acs, workspace)


__all__ = [
    "ArtifactMiss",
    "ArtifactMissingError",
    "fail_feature_with_explicit_reason",
    "recognized_ac_prefixes",
    "verify_artifact_existence",
]
