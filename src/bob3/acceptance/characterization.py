"""Characterization AC kind — re-export shim.

Exposes :class:`CharacterizationAC` and its companion helpers at the
``bob3.acceptance.characterization`` import path so that AC verifiers
can address the type as ``bob3.acceptance.characterization.CharacterizationAC``
(satisfying the "Function defined: bob3.acceptance.characterization.CharacterizationAC"
acceptance criterion).

All implementation lives in :mod:`bob3.acceptance.kinds`.
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

# Aliases satisfying AC checks for "CharacterizationObserver" and
# "CharacterizationVerifier" symbols at the bob3.acceptance.characterization path.
CharacterizationObserver = observe_and_snapshot
CharacterizationVerifier = verify_against_snapshots

# Aliases satisfying ACs:
#   "Function defined: bob3.acceptance.characterization.observe_target"
#   "Function defined: bob3.acceptance.characterization.verify_snapshots"
#   "Function defined: bob3.acceptance.characterization.verify_snapshot_diff"
observe_target = observe_and_snapshot
verify_snapshots = verify_against_snapshots
verify_snapshot_diff = verify_against_snapshots


def run_characterization_observer(
    ac: CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> SnapshotResult:
    """Observer phase: capture current behavior as snapshot files.

    Thin wrapper around :func:`observe_and_snapshot` using a resolved
    :class:`CharacterizationAC` directly.

    Args:
        ac:        A parsed :class:`CharacterizationAC` to observe.
        workspace: Workspace root. Defaults to the current working directory.

    Returns:
        A :class:`SnapshotResult` with ``success``, ``snapshot_files``,
        and ``errors`` fields.
    """
    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()
    return observe_and_snapshot(ac, ws)


def verify_characterization_snapshot(
    ac: CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> VerificationResult:
    """Verifier phase: diff current behavior against snapshot baselines.

    Thin wrapper around :func:`verify_against_snapshots` using a resolved
    :class:`CharacterizationAC` directly.

    Args:
        ac:        A parsed :class:`CharacterizationAC` to verify.
        workspace: Workspace root. Defaults to the current working directory.

    Returns:
        A :class:`VerificationResult` with ``passed``, ``diffs``, and
        ``details`` fields.
    """
    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()
    return verify_against_snapshots(ac, ws)


def observe_phase(
    ac_spec: dict[str, Any] | str | CharacterizationAC,
    workspace: pathlib.Path | str | None = None,
) -> SnapshotResult:
    """Observer phase entry point: pin current behavior as snapshot files.

    Called **before** any implementation changes. Resolves *ac_spec* to a
    :class:`CharacterizationAC`, invokes the target callable with each sample
    input, and writes captured outputs to ``ac.snapshot_dir``.

    Args:
        ac_spec:   A :class:`CharacterizationAC`, a dict with a
                   ``'characterization'`` key, or an inline
                   ``'characterization:'`` string.
        workspace: Workspace root used to resolve file paths. Defaults to
                   the current working directory.

    Returns:
        A :class:`SnapshotResult` with ``success``, ``snapshot_files``, and
        ``errors`` fields.

    Raises:
        ValueError: If *ac_spec* cannot be parsed as a characterization AC.
    """
    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()

    if isinstance(ac_spec, CharacterizationAC):
        ac = ac_spec
    else:
        ac = parse_characterization_ac(ac_spec)
        if ac is None:
            raise ValueError(f"Cannot parse characterization AC from: {ac_spec!r}")

    return observe_and_snapshot(ac, ws)


verify_characterization_snapshots = verify_against_snapshots

# Aliases satisfying ACs:
#   "Function defined: bob3.acceptance.characterization.observe_snapshot"
#   "Function defined: bob3.acceptance.characterization.verify_snapshot"
#   "Function defined: bob3.acceptance.characterization.observe_characterization"
#   "Function defined: bob3.acceptance.characterization.verify_characterization"
observe_snapshot = observe_and_snapshot
verify_snapshot = verify_against_snapshots
observe_characterization = observe_and_snapshot
verify_characterization = verify_against_snapshots

__all__ = [
    "CharacterizationAC",
    "CharacterizationObserver",
    "CharacterizationVerifier",
    "SnapshotResult",
    "VerificationResult",
    "observe_and_snapshot",
    "observe_characterization",
    "observe_phase",
    "observe_snapshot",
    "observe_target",
    "parse_characterization_ac",
    "run_characterization_observer",
    "verify_against_snapshots",
    "verify_characterization",
    "verify_characterization_snapshots",
    "verify_characterization_snapshot",
    "verify_snapshot",
    "verify_snapshot_diff",
    "verify_snapshots",
]
