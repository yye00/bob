"""Dispatch-coupled GPU execution evidence facade (hippy).

Discovered auditing the "completed" hippy/hipsci build (bob95): even after the
backend-required static checks the shipped library computed EVERY public
numpy/scipy op on the HOST yet PASSED the launch-evidence anti-cheat. Root
cause: the "real device work happened" proof was a FREE-FLOATING counter — a
module-level ``record_launch_evidence()`` the implementation called ITSELF,
right after finishing the host loop. A proof a component can EMIT ABOUT ITSELF
is not a proof; it must be OBSERVED at the boundary the work must cross.

This module makes launch evidence DISPATCH-COUPLED:

* The evidence counter is PRIVATE (:data:`_LAUNCH_LEDGER`) and is advanced ONLY
  by :func:`dispatch_launch`, which wraps the single facade every backend call
  passes through — a real, successful driver dispatch (kernel launch, graph
  launch, or a vendor compute call: hipBLAS gemm, hipFFT exec, hipSOLVER,
  hipRAND generate, hipSPARSE spmv).
* A device SYNC or a bare ``hipMemcpy`` is NOT dispatch evidence — syncing and
  copying are not compute, so a host-compute-then-copy path still fails.
* The legacy self-bump helper :func:`record_launch_evidence` is now a NO-OP:
  there is NO public function host code can call to advance the ledger.
* :func:`audit_dispatch_coupling` statically fails any source in which launch
  evidence can be advanced by host code (a callable bump helper reachable from
  ``src/``, or a counter not tied to a real dispatch), with the message
  ``"launch evidence is not dispatch-coupled"``.

Public API
----------
dispatch_launch(entry_point, fn, *args, **kwargs) -> Any
record_launch_evidence(*args, **kwargs) -> None      (no-op, legacy shim)
get_launch_count() -> int
reset_launch_ledger() -> None
audit_dispatch_coupling(source) -> DispatchCouplingVerdict
DISPATCH_ENTRY_POINTS, NON_DISPATCH_HIP_CALLS
DispatchCouplingError, DispatchCouplingVerdict

integration: bob.spec_quality_score
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# integration: bob.spec_quality_score — the anti-cheat verdict feeds the
# composite spec-quality scorer, which must reject a host-advanceable ledger.
import bob.spec_quality_score  # noqa: F401


# ---------------------------------------------------------------------------
# Recognized dispatch entry points
# ---------------------------------------------------------------------------
# A real, successful driver DISPATCH that performs on-device compute. Only these
# advance the private ledger.
DISPATCH_ENTRY_POINTS: frozenset[str] = frozenset(
    {
        "hipModuleLaunchKernel",
        "hipLaunchKernel",
        "hipGraphLaunch",
        "hipExtLaunchKernel",
        # Vendor compute libraries (a call IS a device dispatch).
        "hipblasSgemm",
        "hipblasDgemm",
        "hipblasGemmEx",
        "hipfftExec",
        "hipfftExecC2C",
        "hipfftExecR2C",
        "hipsolverGesvd",
        "hipsolverPotrf",
        "hiprandGenerate",
        "hiprandGenerateUniform",
        "hipsparseSpMV",
        "hipsparseCsrmv",
        "rocblas_sgemm",
        "rocfft_execute",
    }
)

# Calls that touch the device but perform NO compute — syncing or copying is
# not dispatch evidence. A host-compute-then-copy path must still fail.
NON_DISPATCH_HIP_CALLS: frozenset[str] = frozenset(
    {
        "hipDeviceSynchronize",
        "hipStreamSynchronize",
        "hipEventSynchronize",
        "hipMemcpy",
        "hipMemcpyAsync",
        "hipMemcpyHtoD",
        "hipMemcpyDtoH",
        "hipMalloc",
        "hipFree",
    }
)


# ---------------------------------------------------------------------------
# Private ledger — no public setter
# ---------------------------------------------------------------------------
_LAUNCH_LEDGER: int = 0


def get_launch_count() -> int:
    """Return the current dispatch-coupled launch count (read-only)."""
    return _LAUNCH_LEDGER


def reset_launch_ledger() -> None:
    """Reset the private ledger to zero (test-support only)."""
    global _LAUNCH_LEDGER
    _LAUNCH_LEDGER = 0


def dispatch_launch(entry_point: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Perform a real driver dispatch through the single facade and record it.

    *entry_point* names the driver call being wrapped. The private ledger is
    advanced ONLY when *entry_point* is a recognized real DISPATCH
    (:data:`DISPATCH_ENTRY_POINTS`) AND *fn* returns without raising. A
    non-dispatch HIP call (device sync / memcpy) executes normally but does NOT
    advance the ledger — syncing/copying is not compute.

    Raises
    ------
    ValueError
        If *entry_point* is not a non-empty string, if it is neither a known
        dispatch nor a known non-dispatch HIP call, or if *fn* is not callable.
        The function never silently succeeds on invalid input.
    """
    global _LAUNCH_LEDGER

    if not isinstance(entry_point, str) or not entry_point.strip():
        raise ValueError("entry_point must be a non-empty string naming a driver call")
    if not callable(fn):
        raise ValueError("fn must be a callable performing the driver dispatch")

    name = entry_point.strip()
    is_dispatch = name in DISPATCH_ENTRY_POINTS
    is_non_dispatch = name in NON_DISPATCH_HIP_CALLS
    if not is_dispatch and not is_non_dispatch:
        raise ValueError(
            f"unknown driver entry point {name!r}: not a recognized dispatch "
            f"or HIP call; cannot serve as launch evidence"
        )

    result = fn(*args, **kwargs)

    # Advance the ledger ONLY on a successful real dispatch. A sync/memcpy that
    # returns is deliberately NOT counted.
    if is_dispatch:
        _LAUNCH_LEDGER += 1
    return result


def record_launch_evidence(*args: Any, **kwargs: Any) -> None:
    """Legacy self-bump helper — NO-OP.

    Host code used to call this to "prove" device execution. It can no longer
    advance the ledger: evidence is dispatch-coupled and only
    :func:`dispatch_launch` (observing a real driver dispatch) counts. Retained
    as a no-op so legacy call sites do not crash, but it records nothing.
    """
    return None


# ---------------------------------------------------------------------------
# Static anti-cheat: launch evidence must be dispatch-coupled
# ---------------------------------------------------------------------------

class DispatchCouplingError(ValueError):
    """Raised when launch evidence is not dispatch-coupled."""


@dataclass
class DispatchCouplingVerdict:
    """Result of :func:`audit_dispatch_coupling`."""

    dispatch_coupled: bool
    audit_fails: bool
    reason: str = ""
    offending_symbols: list[str] = field(default_factory=list)


# A counter/ledger name that a compute feature might use as launch evidence.
_LEDGER_NAME_RE = re.compile(
    r"\b\w*(?:launch|dispatch|kernel|evidence|ledger|_launch_log)\w*\b",
    re.IGNORECASE,
)

# A host-callable bump helper: a def whose name advertises it advances launch
# evidence and whose body mutates such a counter.
_BUMP_HELPER_DEF_RE = re.compile(
    r"def\s+(\w*(?:record|bump|advance|increment|mark|note)\w*"
    r"(?:launch|dispatch|kernel|evidence|ledger)\w*|"
    r"\w*(?:launch|dispatch|kernel|evidence|ledger)\w*"
    r"(?:record|bump|advance|increment|mark|note)\w*)\s*\(",
    re.IGNORECASE,
)

_COUNTER_MUTATE_RE = re.compile(
    r"(\w*(?:launch|dispatch|kernel|evidence|ledger)\w*)\s*"
    r"(?:\+=\s*1|=\s*\1\s*\+\s*1|\.append\()",
    re.IGNORECASE,
)


def audit_dispatch_coupling(source: str) -> DispatchCouplingVerdict:
    """Statically decide whether *source*'s launch evidence is dispatch-coupled.

    The audit FAILS (``audit_fails=True``, reason contains
    ``"launch evidence is not dispatch-coupled"``) when the source exposes a
    way for HOST code to advance launch evidence:

    * a callable bump helper (``def record_launch_evidence(...): ... += 1``)
      that is NOT a no-op, i.e. its body mutates a launch/evidence counter; or
    * a launch/evidence counter mutated OUTSIDE the ``dispatch_launch`` facade
      (a free-floating self-bump).

    A source in which the only counter mutation lives inside ``dispatch_launch``
    (and any ``record_launch_evidence`` is a no-op) passes.

    Raises
    ------
    ValueError
        If *source* is not a string.
    """
    if not isinstance(source, str):
        raise ValueError("source must be a string of Python code to audit")

    offending: list[str] = []

    # 1) A host-callable bump helper whose body actually mutates a counter.
    for m in _BUMP_HELPER_DEF_RE.finditer(source):
        helper_name = m.group(1)
        body = _function_body(source, m.end())
        if _COUNTER_MUTATE_RE.search(body):
            offending.append(helper_name)

    # 2) A counter mutation that is not inside the dispatch_launch facade.
    for m in _COUNTER_MUTATE_RE.finditer(source):
        enclosing = _enclosing_def_name(source, m.start())
        if enclosing != "dispatch_launch":
            token = m.group(0).strip()
            if token not in offending:
                offending.append(token)

    if offending:
        return DispatchCouplingVerdict(
            dispatch_coupled=False,
            audit_fails=True,
            reason=(
                "launch evidence is not dispatch-coupled: host code can advance "
                "the ledger via " + ", ".join(sorted(set(offending)))
            ),
            offending_symbols=sorted(set(offending)),
        )

    return DispatchCouplingVerdict(
        dispatch_coupled=True,
        audit_fails=False,
        reason="launch evidence is dispatch-coupled",
    )


def assert_dispatch_coupled(source: str) -> None:
    """Raise :class:`DispatchCouplingError` when *source* is not dispatch-coupled."""
    verdict = audit_dispatch_coupling(source)
    if verdict.audit_fails:
        raise DispatchCouplingError(verdict.reason)


# ---------------------------------------------------------------------------
# Small source-slicing helpers (indentation-based, no full AST needed)
# ---------------------------------------------------------------------------

def _function_body(source: str, def_paren_end: int) -> str:
    """Return the indented body following a ``def ...(`` whose ``(`` ended at
    *def_paren_end*."""
    # Advance to the end of the def line (past the closing ``:``).
    nl = source.find("\n", def_paren_end)
    if nl == -1:
        return ""
    lines = source[nl + 1 :].splitlines()
    body: list[str] = []
    base_indent: int | None = None
    for line in lines:
        if not line.strip():
            body.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if base_indent is None:
            base_indent = indent
        if indent < base_indent:
            break
        body.append(line)
    return "\n".join(body)


def _enclosing_def_name(source: str, pos: int) -> str | None:
    """Return the name of the innermost ``def`` enclosing character *pos*."""
    prefix = source[:pos]
    lines = prefix.splitlines()
    if not lines:
        return None
    # The indentation of the line containing pos.
    target_indent = len(lines[-1]) - len(lines[-1].lstrip())
    def_re = re.compile(r"^(\s*)def\s+(\w+)\s*\(")
    for line in reversed(lines[:-1]):
        m = def_re.match(line)
        if m:
            def_indent = len(m.group(1))
            if def_indent < target_indent:
                return m.group(2)
    return None
