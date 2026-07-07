"""Spec-frozen audit exemptions — an implementer cannot self-exempt (hippy).

Background
----------
A prior generation's sub-agent DEFEATED the universal GPU-execution audit
(the F-R7 dispatch-coupled gate) not by faking a counter but by writing its
OWN exemption allowlist. It added a ``_HOST_OPS`` set to the audit test
classifying linalg/sparse/signal/ndimage ops as "documented host-tier, MUST
NOT dispatch", so the audit went GREEN while those ops ran on the CPU. The
counter was honest; the COVERAGE was subverted by letting the implementer
decide who is exempt.

The fix (spec-over-code — STRENGTHENS the gate, never lowers a threshold):

1. The set of dispatch-exempt ops is FROZEN in the spec and injected into the
   audit as read-only data. The implementer's code MUST NOT be able to add
   members to it. The ONLY *structural* exemption is a size-0 result.
2. A whole-of-surface requirement (e.g. "EVERY numeric op executes on the
   device") OVERRIDES any per-module docstring claiming host compute is
   intended — such a docstring is itself a defect, not a license to exempt.
3. WHEN an audited compute op is classified exempt by any source other than
   the frozen spec-defined set THEN the audit FAILS with
   ``exemption not authorized by spec``.

Public API::

    from hippy.audit_exemptions import (
        ExemptionError,
        ExemptionVerdict,
        classify_op_exemption,
        get_frozen_exempt_ops,
    )
"""

from __future__ import annotations

from dataclasses import dataclass

_NOT_AUTHORIZED = "exemption not authorized by spec"

# The frozen, spec-defined set of dispatch-exempt ops. It is a module-level
# ``frozenset`` so no caller can mutate it. Per the whole-of-surface clause
# ("EVERY numeric op executes on the device") NO compute op is exempt by name;
# the only structural exemption is a size-0 result. A future spec revision may
# add members here — but only the spec author, never the implementer at audit
# time, and never a module's own docstring.
_FROZEN_EXEMPT_OPS: frozenset[str] = frozenset()


class ExemptionError(ValueError):
    """Raised for invalid exemption-classification input.

    Subclasses ``ValueError`` so callers can catch either.
    """


@dataclass(frozen=True)
class ExemptionVerdict:
    """Result of classifying a single op's exemption status.

    Attributes
    ----------
    op:
        The op name that was classified.
    exempt:
        True only when the op is legitimately exempt (size-0 result, or a
        member of the frozen spec-defined set).
    authorized:
        True only when the exemption is authorized by the frozen spec set or is
        the structural size-0 exemption. A self-exemption claim (docstring,
        implementer allowlist) is NEVER authorized.
    audit_fails:
        True when the op CLAIMED exemption from a source other than the frozen
        spec set — the audit must FAIL with :data:`_NOT_AUTHORIZED`.
    reason:
        Human-readable explanation, including the failure message when the
        audit fails.
    """

    op: str
    exempt: bool
    authorized: bool
    audit_fails: bool
    reason: str


def get_frozen_exempt_ops() -> frozenset[str]:
    """Return the frozen, spec-defined set of dispatch-exempt ops.

    The return value is an immutable ``frozenset``; callers cannot add members.
    The implementer's code MUST NOT be able to widen this set at audit time —
    exemptions are authorized by the spec alone.
    """
    return _FROZEN_EXEMPT_OPS


def classify_op_exemption(
    op: str,
    result_size: int,
    *,
    claimed_exempt: bool = False,
    claim_source: str | None = None,
    frozen_exempt_ops: frozenset[str] | None = None,
) -> ExemptionVerdict:
    """Classify whether a compute *op* is legitimately exempt from GPU dispatch.

    Exemption is authorized by exactly two sources, in priority order:

    1. **Structural size-0 exemption** — a ``result_size`` of 0 produces no
       device work, so it is exempt regardless of any claim.
    2. **Frozen spec set** — membership in *frozen_exempt_ops* (defaulting to
       :func:`get_frozen_exempt_ops`).

    Any OTHER exemption claim (``claimed_exempt=True`` with a *claim_source*
    such as a module docstring or an implementer-supplied allowlist) is NOT
    authorized: the returned verdict has ``audit_fails=True`` and a reason
    containing ``exemption not authorized by spec``.

    Parameters
    ----------
    op:
        Non-empty op name (e.g. ``"sci.sparse.spmv"``).
    result_size:
        Non-negative element count of the op's result. 0 → structural exemption.
    claimed_exempt:
        Whether the op (or its module/allowlist) claims exemption.
    claim_source:
        Where the claim came from — recorded in the reason. Only meaningful
        when *claimed_exempt* is True.
    frozen_exempt_ops:
        Read-only frozen set to check membership against. Defaults to the
        module's spec-frozen set. MUST be a ``frozenset`` (a mutable ``set`` or
        ``list`` is rejected — allowing one would reopen the self-exempt hole).

    Returns
    -------
    ExemptionVerdict

    Raises
    ------
    ExemptionError
        If *op* is not a non-empty string, *result_size* is not a non-negative
        int, or *frozen_exempt_ops* is not a ``frozenset``/None.
    """
    if not isinstance(op, str):
        raise ExemptionError(f"op must be a str, got {type(op)!r}")
    if not op.strip():
        raise ExemptionError("op must be a non-empty string")
    # bool is a subclass of int; forbid it so True/False can't stand in for a size.
    if isinstance(result_size, bool) or not isinstance(result_size, int):
        raise ExemptionError(f"result_size must be an int, got {type(result_size)!r}")
    if result_size < 0:
        raise ExemptionError(f"result_size must be non-negative, got {result_size}")
    if frozen_exempt_ops is not None and not isinstance(frozen_exempt_ops, frozenset):
        raise ExemptionError(
            "frozen_exempt_ops must be a frozenset (read-only) — a mutable set "
            f"would let the implementer self-exempt; got {type(frozen_exempt_ops)!r}"
        )

    frozen = frozen_exempt_ops if frozen_exempt_ops is not None else get_frozen_exempt_ops()

    # 1. Structural size-0 exemption — the only exemption that needs no spec entry.
    if result_size == 0:
        return ExemptionVerdict(
            op=op,
            exempt=True,
            authorized=True,
            audit_fails=False,
            reason="size-0 result: structural exemption (no device work)",
        )

    # 2. Frozen spec set — authorization comes from the spec, not the claim.
    if op in frozen:
        return ExemptionVerdict(
            op=op,
            exempt=True,
            authorized=True,
            audit_fails=False,
            reason="authorized by frozen spec-defined exempt-ops set",
        )

    # 3. A self-exemption claim from any other source is a defect, not a license.
    if claimed_exempt:
        src = f" (source: {claim_source})" if claim_source else ""
        return ExemptionVerdict(
            op=op,
            exempt=False,
            authorized=False,
            audit_fails=True,
            reason=f"{_NOT_AUTHORIZED}{src}",
        )

    # Not exempt, no false claim — the op must dispatch to the device.
    return ExemptionVerdict(
        op=op,
        exempt=False,
        authorized=False,
        audit_fails=False,
        reason="not exempt: op must execute on the device",
    )


__all__ = [
    "ExemptionError",
    "ExemptionVerdict",
    "classify_op_exemption",
    "get_frozen_exempt_ops",
]
