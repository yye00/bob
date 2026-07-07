"""Error-path tests (feature 608b8791).

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from hippy.dispatch_facade import (
    audit_dispatch_coupling,
    dispatch_launch,
    get_launch_count,
    reset_launch_ledger,
)


@pytest.fixture(autouse=True)
def _clean_ledger():
    reset_launch_ledger()
    yield
    reset_launch_ledger()


def test_empty_entry_point_raises():
    with pytest.raises(ValueError, match="entry_point"):
        dispatch_launch("", lambda: 1)
    assert get_launch_count() == 0


def test_whitespace_entry_point_raises():
    with pytest.raises(ValueError, match="entry_point"):
        dispatch_launch("   ", lambda: 1)


def test_non_string_entry_point_raises():
    with pytest.raises(ValueError, match="entry_point"):
        dispatch_launch(None, lambda: 1)


def test_non_callable_fn_raises():
    with pytest.raises(ValueError, match="fn must be a callable"):
        dispatch_launch("hipModuleLaunchKernel", "not_callable")
    assert get_launch_count() == 0


def test_unknown_entry_point_raises_and_does_not_advance():
    """An unrecognized name cannot serve as launch evidence."""
    with pytest.raises(ValueError, match="unknown driver entry point"):
        dispatch_launch("totallyMadeUpCall", lambda: 1)
    assert get_launch_count() == 0


def test_unknown_entry_point_does_not_silently_succeed():
    called = {"ran": False}

    def fn():
        called["ran"] = True
        return 1

    with pytest.raises(ValueError):
        dispatch_launch("notAKernel", fn)
    # fn must not have been invoked — validation happens before dispatch.
    assert called["ran"] is False


def test_audit_non_string_source_raises():
    with pytest.raises(ValueError, match="source must be a string"):
        audit_dispatch_coupling(123)


def test_audit_none_source_raises():
    with pytest.raises(ValueError, match="source must be a string"):
        audit_dispatch_coupling(None)
