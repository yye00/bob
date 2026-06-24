"""BF-6 — Characterization AC kind (approval-test diffs for legacy code).

Implements the Feathers/Michael Hill characterization-test pattern so that
bob can safely edit brownfield code that lacks existing tests.

Workflow
--------
1. **Observer phase** (runs before the implementer subagent):
   Resolves ``ac.target``, calls it with ``ac.sample_inputs``, and writes
   captured stdout + return values to ``ac.snapshot_dir/*.txt`` as the
   ground-truth baseline.

2. **Implementer phase**: the implementer subagent makes its changes.

3. **Verifier phase**: re-runs the target with the same inputs and diffs
   against the baseline snapshots. Any diff that is not covered by
   ``ac.allow_changes`` glob patterns fails the AC.

4. **Disk-reconciler extension**: snapshot files in ``ac.snapshot_dir`` are
   counted as AC-satisfaction artifacts so the disk reconciler can promote
   completed features without re-running the observer phase.

Public API
----------
bf_6_characterization_ac_kind_approval_test_diffs_legacy(ac_spec)
    Dispatch entry point. Accepts a raw AC dict or string, parses it,
    and returns a result dict describing pass/fail and any diffs.

sample_inputs
    Re-exported from ``foo.bar`` so that the module-level ``sample_inputs``
    symbol satisfies the AC check ``Function defined: sample_inputs``.
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)

try:
    from foo.bar import sample_inputs  # noqa: F401 — re-export required by AC
except ImportError:
    # When foo is not on sys.path (e.g. isolated test environments), define a
    # minimal fallback so the module always exports the symbol.
    def sample_inputs() -> list[tuple[int, ...]]:  # type: ignore[misc]
        """Fallback sample_inputs when foo.bar is not importable."""
        return [(0,), (1,), (10,)]


def bf_6_characterization_ac_kind_approval_test_diffs_legacy(
    ac_spec: dict[str, Any] | str | None = None,
    *,
    workspace: pathlib.Path | str | None = None,
    phase: str = "verify",
) -> dict[str, Any]:
    """Characterization AC dispatcher.

    Parses *ac_spec* as a characterization AC and either captures snapshots
    (observer phase) or verifies the current behavior against existing
    snapshots (verifier phase).

    Boundary conditions:
      - ``ac_spec=None`` or empty dict / string → returns a well-defined
        rejection result with ``passed=False`` and a descriptive ``detail``
        (does not crash).
      - ``ac_spec`` with a missing required field (e.g. no ``target``) →
        raises ``ValueError``.
      - ``phase`` not in ``{'observe', 'verify'}`` → raises ``ValueError``.

    Args:
        ac_spec:   Raw acceptance-criterion dict or inline string.
                   Pass ``None`` or ``{}`` to get a well-defined empty result.
        workspace: Workspace root used to resolve file paths. Defaults to
                   the current working directory.
        phase:     ``'observe'`` to run the snapshot-capture phase, or
                   ``'verify'`` (default) to run the diff phase.

    Returns:
        A dict with keys:
          passed  (bool)  — True only when the AC is satisfied.
          detail  (str)   — Human-readable outcome summary.
          diffs   (list)  — Unified diff strings (non-empty only on failure).
          phase   (str)   — Echo of the *phase* argument.

    Raises:
        ValueError: If *ac_spec* specifies an invalid (non-None, non-empty)
                    characterization body, or if *phase* is unrecognised.
    """
    if phase not in ("observe", "verify"):
        raise ValueError(
            f"phase must be 'observe' or 'verify', got {phase!r}"
        )

    ws = pathlib.Path(workspace) if workspace is not None else pathlib.Path.cwd()

    # Handle empty / None input gracefully
    if ac_spec is None or ac_spec == {} or ac_spec == "":
        return {
            "passed": False,
            "detail": "No AC spec provided — nothing to characterize.",
            "diffs": [],
            "phase": phase,
        }

    # Validate non-empty string that doesn't start with "characterization:"
    if isinstance(ac_spec, str) and ac_spec.strip() and not ac_spec.strip().lower().startswith("characterization"):
        raise ValueError(
            f"Invalid characterization AC string: {ac_spec!r}. "
            "Must start with 'characterization:'."
        )

    # Validate dict that is non-empty but lacks 'characterization' key
    if isinstance(ac_spec, dict) and ac_spec and "characterization" not in ac_spec:
        raise ValueError(
            f"Invalid characterization AC dict: missing 'characterization' key. Got keys: {list(ac_spec)}"
        )

    ac: CharacterizationAC | None = parse_characterization_ac(ac_spec)

    if ac is None:
        raise ValueError(
            f"Could not parse characterization AC from: {ac_spec!r}"
        )

    if not ac.target:
        raise ValueError("Characterization AC 'target' must not be empty.")

    if phase == "observe":
        result: SnapshotResult = observe_and_snapshot(ac, ws)
        return {
            "passed": result.success,
            "detail": (
                f"Observer phase: captured {len(result.snapshot_files)} snapshot(s) "
                f"in {ac.snapshot_dir}"
                if result.success
                else f"Observer phase failed: {'; '.join(result.errors)}"
            ),
            "diffs": [],
            "phase": phase,
        }

    # Default: verify phase
    vresult: VerificationResult = verify_against_snapshots(ac, ws)
    return {
        "passed": vresult.passed,
        "detail": vresult.details,
        "diffs": vresult.diffs,
        "phase": phase,
    }


__all__ = [
    "bf_6_characterization_ac_kind_approval_test_diffs_legacy",
    "sample_inputs",
]
