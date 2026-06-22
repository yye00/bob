"""Verifier module for characterization AC — exposes verify_characterization.

This module is the public entry point for the verifier phase of the
characterization AC kind. It wraps :func:`bob3.acceptance.kinds.verify_against_snapshots`
with a simplified signature for use by bob3's AC verifier and orchestrator
after implementation changes to check for behavioral regressions.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob3.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)


def verify_characterization(
    ac: CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> VerificationResult:
    """Verifier phase: re-run target and diff against existing snapshots.

    Thin wrapper around :func:`verify_against_snapshots` that accepts a
    resolved :class:`CharacterizationAC` directly. Called **after**
    implementation changes to detect behavioral regressions.

    Args:
        ac:        A parsed :class:`CharacterizationAC` to verify.
        workspace: Workspace root used to resolve file paths. Defaults to
                   the current working directory.

    Returns:
        A :class:`VerificationResult` with ``passed``, ``diffs``, and
        ``details`` fields.
    """
    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()
    return verify_against_snapshots(ac, ws)


def verify_characterization_from_spec(
    ac_spec: dict[str, Any] | str | CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> VerificationResult:
    """Verifier phase entry point: verify current behavior against snapshots.

    Called **after** implementation changes. Resolves *ac_spec* to a
    :class:`CharacterizationAC`, re-runs the target callable with each
    sample input, and diffs against the existing snapshot files in
    ``ac.snapshot_dir``. Any diff not covered by ``ac.allow_changes`` fails
    the AC.

    Args:
        ac_spec:   A :class:`CharacterizationAC`, a dict with a
                   ``'characterization'`` key, or an inline
                   ``'characterization:'`` string.
        workspace: Workspace root used to resolve file paths. Defaults to
                   the current working directory.

    Returns:
        A :class:`VerificationResult` with ``passed``, ``diffs``, and
        ``details`` fields.

    Raises:
        ValueError: If *ac_spec* cannot be parsed as a characterization AC.
    """
    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()

    if isinstance(ac_spec, CharacterizationAC):
        ac = ac_spec
    else:
        ac = parse_characterization_ac(ac_spec)
        if ac is None:
            raise ValueError(
                f"Cannot parse characterization AC from: {ac_spec!r}"
            )

    return verify_against_snapshots(ac, ws)


__all__ = [
    "verify_characterization",
    "verify_characterization_from_spec",
]
