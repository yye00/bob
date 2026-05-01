"""Verify the autouse fixture in conftest.py isolates module-level state.

Several modules under ``bob3`` keep module-level singletons. Without the
``_reset_module_state`` autouse fixture in :mod:`tests.conftest`, those
singletons leak state across tests in the same interpreter and cause
order-dependent failures.

These tests are deliberately ordered alphabetically (``test_a_*`` then
``test_b_*``) so pytest's default collection order runs them as
"set state" -> "verify state was reset". Both tests are also written
to be independently correct so they pass regardless of order.
"""

from __future__ import annotations


def test_a_set_proxy_logged_feature_ids():
    """Pollute the run_loop dedup set; the autouse fixture should clear it
    before the next test runs."""
    from bob3.orchestrator import run_loop

    run_loop._PROXY_LOGGED_FEATURE_IDS.add("test-id")
    assert "test-id" in run_loop._PROXY_LOGGED_FEATURE_IDS


def test_b_proxy_logged_feature_ids_was_reset():
    """If the conftest fixture is working, the previous test's pollution
    is gone."""
    from bob3.orchestrator import run_loop

    assert "test-id" not in run_loop._PROXY_LOGGED_FEATURE_IDS


def test_a_set_mcp_manager_singleton():
    """Pollute the mcp_lifecycle singleton; the autouse fixture should
    reset it back to None."""
    from bob3 import mcp_lifecycle

    sentinel = object()
    mcp_lifecycle._manager = sentinel  # type: ignore[assignment]
    assert mcp_lifecycle._manager is sentinel


def test_b_mcp_manager_singleton_was_reset():
    """The autouse fixture should have set ``_manager`` back to None."""
    from bob3 import mcp_lifecycle

    assert mcp_lifecycle._manager is None


def test_a_set_active_processes():
    """Pollute the mcp_lifecycle process registry."""
    from bob3 import mcp_lifecycle

    with mcp_lifecycle._registry_lock:
        mcp_lifecycle._active_processes["test-config"] = "fake"  # type: ignore[assignment]
    assert "test-config" in mcp_lifecycle._active_processes


def test_b_active_processes_was_reset():
    """The autouse fixture should have cleared the registry."""
    from bob3 import mcp_lifecycle

    assert "test-config" not in mcp_lifecycle._active_processes


def test_a_install_signal_handler():
    """Install a custom signal handler; the autouse fixture should
    restore the original after the test ends."""
    import signal

    def custom_handler(signum, frame):
        pass

    signal.signal(signal.SIGINT, custom_handler)
    assert signal.getsignal(signal.SIGINT) is custom_handler


def test_b_signal_handler_was_restored():
    """The autouse fixture should have restored the original SIGINT
    handler — it should NOT still be the ``custom_handler`` from the
    previous test."""
    import signal

    current = signal.getsignal(signal.SIGINT)
    # The function defined inside test_a_install_signal_handler is now
    # out of scope; if isolation works the current handler is the
    # interpreter's original (default int handler or whatever pytest
    # had installed).
    assert getattr(current, "__name__", "") != "custom_handler"
