"""Dispatch-coupled launch-evidence surface (hippy) — feature 75d52aa1.

GPU-execution proof MUST be DISPATCH-COUPLED, not a self-reported counter. A host
backend that bumps its own launch ledger passes every gate unless the evidence is
OBSERVED at the boundary the work must cross. This module is the AC-named entry
point for that guarantee; the mechanics live in :mod:`hippy.dispatch_facade`,
which owns the private ledger, the recognized dispatch entry points, and the
static anti-cheat.

* :func:`assert_dispatch_coupled` — raise if a source can advance launch evidence
  from host code (a callable bump helper or a free-floating counter mutated
  outside the single dispatch facade).
* :func:`record_dispatch_on_success` — advance the PRIVATE ledger only by routing
  through the facade's :func:`~hippy.dispatch_facade.dispatch_launch`; there is no
  host-callable setter that moves the counter directly.
* :func:`record_launch_evidence` — re-exported legacy self-bump shim, now a
  NO-OP: host code cannot advance the ledger by calling it.

integration: hippy.orchestrator
"""

from __future__ import annotations

from typing import Any, Callable

import hippy.orchestrator  # noqa: F401  (integration: hippy.orchestrator)

from hippy.dispatch_facade import (
    DISPATCH_ENTRY_POINTS,
    NON_DISPATCH_HIP_CALLS,
    DispatchCouplingError,
    DispatchCouplingVerdict,
    assert_dispatch_coupled,
    audit_dispatch_coupling,
    dispatch_launch,
    get_launch_count,
    record_launch_evidence,
    reset_launch_ledger,
)

__all__ = [
    "DISPATCH_ENTRY_POINTS",
    "NON_DISPATCH_HIP_CALLS",
    "DispatchCouplingError",
    "DispatchCouplingVerdict",
    "assert_dispatch_coupled",
    "audit_dispatch_coupling",
    "dispatch_launch",
    "get_launch_count",
    "record_dispatch_on_success",
    "record_launch_evidence",
    "reset_launch_ledger",
]


def record_dispatch_on_success(
    entry_point: str, fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """Advance the private ledger ONLY via a real, successful driver dispatch.

    This is the dispatch-coupled way to "record" launch evidence: it runs *fn*
    through the single facade (:func:`hippy.dispatch_facade.dispatch_launch`),
    which advances the PRIVATE counter iff *entry_point* is a recognized real
    dispatch and *fn* returns without raising. A device sync / memcpy or a failed
    dispatch records nothing. There is deliberately no host-callable setter that
    bumps the counter directly.

    Raises
    ------
    ValueError
        If *entry_point* is not a non-empty recognized driver call, or *fn* is
        not callable. The function never silently succeeds on invalid input.
    """
    return dispatch_launch(entry_point, fn, *args, **kwargs)
