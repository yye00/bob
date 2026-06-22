"""Spec quality gate — permanent-carry allowlist exempts forward-carried infra features.

The 0.85 spec_quality_score gate is the right policy for newly synthesized features,
but blocks permanent forward-carry infrastructure features (F-R7-478, F-R7-479,
F-R7-481) whose ACs are intentionally terse and score in the 0.6-0.75 range.

Usage::

    from bob3.spec_quality_gate_permanent_carry_allowlist_exempt_forward import (
        spec_quality_gate_permanent_carry_allowlist_exempt_forward,
    )

    if spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature):
        # skip spec_quality gate — this is a MUST-CARRY-FORWARD feature
        promotable_ids.append(fid)
    else:
        allowed, block_msg = gate_for_ready(quality_report)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bob3.spec_quality_allowlist import is_permanent_forward_carry

if TYPE_CHECKING:
    from bob3.models import Feature


def spec_quality_gate_permanent_carry_allowlist_exempt_forward(feature: "Feature") -> bool:
    """Return True when *feature* is exempt from the 0.85 spec_quality_score gate.

    A feature is exempt when ANY of the following hold:

    1. ``feature.permanent_forward_carry`` is True (explicit DB flag).
    2. ``feature.spec_slot`` contains any allowlisted pattern as a substring.
    3. ``feature.name`` contains any allowlisted pattern as a substring.

    The allowlist defaults to the three canonical infra slots (F-R7-478, F-R7-479,
    F-R7-481) and can be extended via the ``BOB3_ALLOWLIST_PATTERNS`` env var
    (comma-separated list of additional patterns).

    Parameters
    ----------
    feature:
        The Feature model to inspect.

    Returns
    -------
    bool
        True when the feature is exempt and should bypass the quality gate.
    """
    return bool(is_permanent_forward_carry(feature))
