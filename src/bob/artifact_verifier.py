"""AC artifact-existence verifier for the bob package.

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

check_baseline_collection(workspace, *, test_dir, timeout) -> CollectionResult
    Gate: verify the test suite collects cleanly before baseline capture.
    Re-exported from bob.stable_baseline_gate for integration use.

enforce_stable_baseline_gate(workspace, *, test_dir, timeout) -> CollectionResult
    Enforce the stable baseline gate; raises BaselineUnstableError on failure.
    Re-exported from bob.stable_baseline_gate for integration use.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from bob.verification.ac_artifact_check import (
    ArtifactMiss,
    check_file_exists_ac,
    check_file_modified_ac,
    check_function_defined_ac,
    check_pytest_ac,
    verify_ac_artifacts as _verify_ac_artifacts,
)
from bob.stable_baseline_gate import (  # noqa: F401 — stable baseline gate integration
    BaselineUnstableError,
    CollectionResult,
    check_baseline_collection,
    enforce_stable_baseline_gate,
    should_abort_on_collection_failure,
)


def verify_ac_artifacts(
    acs: list[str],
    workspace: Union[str, Path],
) -> list[ArtifactMiss]:
    """Check every AC string and return a list of ArtifactMiss for failures.

    Args:
        acs: List of acceptance criteria strings.  Each item must be a str.
            Recognized prefixes: ``pytest:``, ``File exists:``,
            ``File modified:``, ``File modified or created:``,
            ``Function defined:``.  Unrecognized prefixes produce a miss
            with ``kind='unknown_prefix'``.
        workspace: Root directory of the project workspace.  Paths in ACs
            are resolved relative to this directory.  Must not be ``None``.

    Returns:
        A (possibly empty) list of :class:`ArtifactMiss` objects — one per
        failing AC.  An empty list means all checked ACs resolved to real
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

    return _verify_ac_artifacts(acs, workspace)


def check_artifact_exists(ac_text: str, workspace: Union[str, Path]) -> bool:
    """Check whether the artifact referenced in a single AC string exists.

    Dispatches to the appropriate check function based on the AC prefix.
    Returns True when the artifact exists, False when it is missing or the
    prefix is unrecognized.

    Args:
        ac_text: A single acceptance criteria string, e.g.
            ``"File exists: src/bob/foo.py"`` or
            ``"Function defined: bob.foo.my_func"``.
        workspace: Root directory for resolving relative paths.

    Returns:
        True if the artifact resolves to a real file/symbol, False otherwise.
    """
    if workspace is None:
        raise ValueError("workspace must not be None")
    if not isinstance(ac_text, str):
        raise TypeError(
            f"ac_text must be a str, got {type(ac_text).__name__!r}: {ac_text!r}"
        )

    ws = Path(workspace)
    text = ac_text.strip()

    if text.startswith("File exists:"):
        path = text[len("File exists:"):].strip()
        return check_file_exists_ac(path, ws)
    if text.startswith("File modified or created:"):
        path = text[len("File modified or created:"):].strip()
        return check_file_modified_ac(path, ws)
    if text.startswith("File modified:"):
        path = text[len("File modified:"):].strip()
        return check_file_modified_ac(path, ws)
    if text.startswith("pytest:"):
        path = text[len("pytest:"):].strip()
        # Strip inline comments after em-dash or regular dash
        for sep in (" — ", " -- "):
            if sep in path:
                path = path.split(sep, 1)[0].strip()
        return check_pytest_ac(path, ws)
    if text.startswith("Function defined:"):
        symbol = text[len("Function defined:"):].strip()
        return check_function_defined_ac(symbol, ws)

    # Unrecognized prefix — cannot confirm artifact exists
    return False


def verify_artifacts(
    acs: list[str],
    workspace: Union[str, Path],
) -> list[ArtifactMiss]:
    """Alias for verify_ac_artifacts — pre-pytest artifact-existence pass.

    Check every AC string and return a list of ArtifactMiss for failures.
    Missing artifact -> AC fails with reason ARTIFACT_MISSING:<path>.

    Args:
        acs: List of acceptance criteria strings.
        workspace: Root directory of the project workspace.

    Returns:
        A (possibly empty) list of ArtifactMiss objects.

    Raises:
        ValueError: When acs is not a list or workspace is None.
        TypeError: When any element of acs is not a string.
    """
    return verify_ac_artifacts(acs, workspace)


def validate_ac_artifact(ac_text: str, workspace: Union[str, Path]) -> ArtifactMiss | None:
    """Validate a single AC string and return ArtifactMiss if the artifact is missing.

    Pre-pytest check: resolves the artifact referenced in a single AC string.
    Returns None when the artifact exists, ArtifactMiss when it is missing.

    Args:
        ac_text: A single acceptance criteria string, e.g.
            ``"File exists: src/bob/foo.py"`` or
            ``"Function defined: bob.foo.my_func"``.
        workspace: Root directory for resolving relative paths.

    Returns:
        None if the artifact resolves to a real file/symbol; ArtifactMiss otherwise.

    Raises:
        ValueError: When workspace is None or ac_text is not a string.
    """
    if workspace is None:
        raise ValueError("workspace must not be None")
    if not isinstance(ac_text, str):
        raise ValueError(
            f"ac_text must be a str, got {type(ac_text).__name__!r}: {ac_text!r}"
        )
    misses = verify_ac_artifacts([ac_text], workspace)
    return misses[0] if misses else None


__all__ = [
    "ArtifactMiss",
    "BaselineUnstableError",
    "CollectionResult",
    "check_artifact_exists",
    "check_baseline_collection",
    "enforce_stable_baseline_gate",
    "should_abort_on_collection_failure",
    "validate_ac_artifact",
    "verify_ac_artifacts",
    "verify_artifacts",
]
