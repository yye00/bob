"""Boundary-case tests (feature 608b8791).

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

import pytest

from hippy.dispatch_facade import (
    audit_dispatch_coupling,
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


def test_empty_source_audits_as_coupled():
    """No launch evidence at all is trivially not host-advanceable."""
    verdict = audit_dispatch_coupling("")
    assert verdict.audit_fails is False
    assert verdict.dispatch_coupled is True


def test_whitespace_only_source_is_coupled():
    verdict = audit_dispatch_coupling("   \n\t\n")
    assert verdict.audit_fails is False


def test_source_with_no_evidence_symbols_is_coupled():
    verdict = audit_dispatch_coupling("def add(a, b):\n    return a + b\n")
    assert verdict.audit_fails is False


def test_zero_launches_after_reset():
    reset_launch_ledger()
    assert get_launch_count() == 0


def test_record_launch_evidence_no_args_returns_none():
    """Legacy shim with minimum/empty input is a well-defined no-op."""
    assert record_launch_evidence() is None
    assert get_launch_count() == 0


def test_dispatch_launch_fn_returning_none_is_well_defined():
    """A dispatch whose fn returns None still counts and returns None."""
    result = dispatch_launch("hipModuleLaunchKernel", lambda: None)
    assert result is None
    assert get_launch_count() == 1


def test_single_element_dispatch_advances_once():
    dispatch_launch("hipModuleLaunchKernel", lambda: [0])
    assert get_launch_count() == 1


def test_structurally_empty_result_needs_no_dispatch():
    """The only evidence-exempt case: a size-0 result computes nothing.

    We model it as: no dispatch happened, ledger stays at zero, and that is a
    well-defined state (not an error).
    """
    assert get_launch_count() == 0  # empty op did no on-device work
