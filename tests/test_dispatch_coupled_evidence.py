"""Dispatch-coupled launch-evidence tests (feature 608b8791).

The oracle-not-gameable core: launch evidence MUST be advanced only by a real
driver dispatch observed at the single facade. A host backend that bumps its
own ledger — or calls the legacy self-bump helper — must NOT pass.
"""

from __future__ import annotations

import pytest

from hippy.dispatch_facade import (
    DISPATCH_ENTRY_POINTS,
    NON_DISPATCH_HIP_CALLS,
    DispatchCouplingError,
    audit_dispatch_coupling,
    assert_dispatch_coupled,
    dispatch_launch,
    get_launch_count,
    record_launch_evidence,
    reset_launch_ledger,
)


@pytest.fixture(autouse=True)
def _clean_ledger():
    reset_launch_ledger()
    yield
    reset_launch_ledger()


# ---------------------------------------------------------------------------
# dispatch_launch is the ONLY thing that advances the ledger
# ---------------------------------------------------------------------------

def test_real_dispatch_advances_ledger():
    before = get_launch_count()
    result = dispatch_launch("hipModuleLaunchKernel", lambda: 42)
    assert result == 42
    assert get_launch_count() == before + 1


def test_vendor_compute_call_advances_ledger():
    dispatch_launch("hipblasSgemm", lambda: None)
    assert get_launch_count() == 1


def test_sync_is_not_dispatch_evidence():
    """A device SYNC executes but does NOT advance the ledger."""
    dispatch_launch("hipDeviceSynchronize", lambda: None)
    assert get_launch_count() == 0


def test_memcpy_is_not_dispatch_evidence():
    """A bare hipMemcpy is copying, not compute — no evidence."""
    dispatch_launch("hipMemcpy", lambda: None)
    assert get_launch_count() == 0


def test_failed_dispatch_does_not_advance_ledger():
    def boom():
        raise RuntimeError("driver error")

    with pytest.raises(RuntimeError):
        dispatch_launch("hipModuleLaunchKernel", boom)
    assert get_launch_count() == 0


# ---------------------------------------------------------------------------
# The legacy self-bump helper is a NO-OP
# ---------------------------------------------------------------------------

def test_record_launch_evidence_is_noop():
    record_launch_evidence()
    record_launch_evidence("anything", foo="bar")
    assert get_launch_count() == 0


def test_no_public_setter_advances_ledger():
    """Host code cannot reach any public function that advances the ledger."""
    record_launch_evidence()
    assert get_launch_count() == 0
    # Only a genuine dispatch moves it.
    dispatch_launch("hipGraphLaunch", lambda: None)
    assert get_launch_count() == 1


# ---------------------------------------------------------------------------
# Static anti-cheat: the five modelled cheats
# ---------------------------------------------------------------------------

CHEAT_HOST_SELF_BUMP = '''
_launch_ledger = 0

def record_launch_evidence():
    global _launch_ledger
    _launch_ledger += 1

def multiply(a, b):
    out = [x * y for x, y in zip(a, b)]   # host loop, no dispatch
    record_launch_evidence()              # self-bump
    return out
'''

CHEAT_FREE_FLOATING_COUNTER = '''
launch_count = 0

def multiply(a, b):
    global launch_count
    out = [x * y for x, y in zip(a, b)]
    launch_count += 1                     # free-floating bump outside facade
    return out
'''

GOOD_DISPATCH_COUPLED = '''
_LAUNCH_LEDGER = 0

def dispatch_launch(entry_point, fn, *args, **kwargs):
    global _LAUNCH_LEDGER
    result = fn(*args, **kwargs)
    _LAUNCH_LEDGER += 1                    # only inside the facade
    return result

def record_launch_evidence(*a, **k):
    return None                           # no-op

def multiply(a, b):
    return dispatch_launch("hipModuleLaunchKernel", _kernel, a, b)
'''


def test_cheat_host_self_bump_helper_fails_audit():
    verdict = audit_dispatch_coupling(CHEAT_HOST_SELF_BUMP)
    assert verdict.audit_fails is True
    assert not verdict.dispatch_coupled
    assert "launch evidence is not dispatch-coupled" in verdict.reason


def test_cheat_free_floating_counter_fails_audit():
    verdict = audit_dispatch_coupling(CHEAT_FREE_FLOATING_COUNTER)
    assert verdict.audit_fails is True
    assert "launch evidence is not dispatch-coupled" in verdict.reason


def test_dispatch_coupled_source_passes_audit():
    verdict = audit_dispatch_coupling(GOOD_DISPATCH_COUPLED)
    assert verdict.audit_fails is False
    assert verdict.dispatch_coupled is True


def test_our_own_facade_module_is_dispatch_coupled():
    """The shipped facade must pass its own anti-cheat."""
    from pathlib import Path
    import hippy.dispatch_facade as mod

    src = Path(mod.__file__).read_text()
    verdict = audit_dispatch_coupling(src)
    assert verdict.audit_fails is False, verdict.reason


def test_assert_dispatch_coupled_raises_on_cheat():
    with pytest.raises(DispatchCouplingError, match="not dispatch-coupled"):
        assert_dispatch_coupled(CHEAT_HOST_SELF_BUMP)


def test_assert_dispatch_coupled_passes_good_source():
    assert_dispatch_coupled(GOOD_DISPATCH_COUPLED)  # no raise


# ---------------------------------------------------------------------------
# Entry-point taxonomy invariants
# ---------------------------------------------------------------------------

def test_dispatch_and_non_dispatch_sets_are_disjoint():
    assert DISPATCH_ENTRY_POINTS.isdisjoint(NON_DISPATCH_HIP_CALLS)


def test_sync_and_memcpy_classified_non_dispatch():
    assert "hipDeviceSynchronize" in NON_DISPATCH_HIP_CALLS
    assert "hipMemcpy" in NON_DISPATCH_HIP_CALLS
    assert "hipModuleLaunchKernel" in DISPATCH_ENTRY_POINTS
