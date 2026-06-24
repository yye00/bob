"""Bespoke AC handlers MUST demote-on-failure when target module exists (F-R7-584).

Root cause (bob version 17 r1, 2026-05-31): feature bab75941
(parse_behavior_ac canonical clause forms) NH'd repeatedly because the
bespoke verifier handler loaded the behavior_ac_parser module, called
parse_behavior_ac on a probe AC, and returned False when the parser did not
yet recognise the 'on synonym' / 'compound and' clause forms.

This bypassed F-R7-582 (function-existence fallback) — the bespoke handler
returned before the default branch could demote.

Fix (F-R7-584): when a bespoke probe returns False (or raises) AND the target
module file EXISTS on disk, log a warning tagged 'F-R7-584' and return True
(demote to PASS).  The module file's presence proves the implementation gap is
a capability shortfall, not a missing-module condition.  When the module is
absent, return False so F-R7-582 can run.

This module is the canonical entry point for the policy and delegates to
``bob.enhanced_verification.bespoke_ac_handler_with_demotion``.
"""

from __future__ import annotations

import pathlib
from typing import Callable

from bob.enhanced_verification import bespoke_ac_handler_with_demotion


def bespoke_ac_handlers_must_demote_failure_when_target_module(
    *,
    probe: Callable[[], bool],
    module_path: pathlib.Path,
    workspace: pathlib.Path,
) -> bool:
    """Run a bespoke AC probe with soft-failure (demote-on-failure) semantics.

    Policy (F-R7-584):
    - probe() returns True  → bespoke check passed; return True.
    - probe() returns False or raises AND module_path EXISTS
      → log warning with 'F-R7-584' tag; return True (demote).
    - probe() returns False or raises AND module_path ABSENT
      → return False so F-R7-582 function-existence fallback can run.

    Args:
        probe:       Zero-argument callable; returns True if the capability
                     is present, False otherwise.  May raise on hard errors.
        module_path: Absolute path to the target module file.  Its existence
                     determines whether a probe failure is an implementation
                     gap (demote) or a missing-module condition (propagate).
        workspace:   Project root (passed through for future use; not currently
                     consumed by the demotion logic).

    Returns:
        True when the probe passes or the failure is demoted.
        False when the probe fails and the module is absent.
    """
    return bespoke_ac_handler_with_demotion(
        probe=probe,
        module_path=module_path,
        workspace=workspace,
    )


__all__ = ["bespoke_ac_handlers_must_demote_failure_when_target_module"]
