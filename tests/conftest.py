"""Shared test fixtures and isolation hooks for bob3 tests.

Several modules under ``bob3`` keep state at module level (memoized
singletons, dedup sets, signal handlers). When tests run in the same
interpreter process, that state leaks between tests and causes
order-dependent failures. The autouse fixture in this file resets
the known leak points after every test.

Specifically reset:

- ``bob3.orchestrator.run_loop._PROXY_LOGGED_FEATURE_IDS`` — bounded
  dedup set used by proxy-cost logging.
- ``bob3.mcp_lifecycle._active_processes`` — registry mapping config
  names to live MCP subprocesses. Cleared (NOT killed); each owner is
  responsible for stopping its own process via its ``stop()`` method.
- ``bob3.mcp_lifecycle._manager`` — global MCPLifecycleManager
  singleton built lazily by ``get_mcp_manager``.
- Signal handlers installed by ``OrchestrationLoop._install_signal_handlers``
  for SIGINT and SIGTERM.

The fixture also captures and restores the original SIGINT/SIGTERM
handlers around each test so a test that installs its own handler
cannot affect the next test.
"""

from __future__ import annotations

import signal

import pytest


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset bob3 module-level state between tests for isolation."""
    # Capture original signal handlers so we can restore them even if
    # a test installs its own (e.g. via OrchestrationLoop._install_signal_handlers).
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)

    yield

    # Reset module-level state
    try:
        from bob3.orchestrator import run_loop
        if hasattr(run_loop, "_PROXY_LOGGED_FEATURE_IDS"):
            run_loop._PROXY_LOGGED_FEATURE_IDS.clear()
    except ImportError:
        pass

    try:
        from bob3 import mcp_lifecycle
        # Clear active_processes registry but don't kill processes
        # (they should be cleaned up by their own stop() calls).
        if hasattr(mcp_lifecycle, "_active_processes"):
            with mcp_lifecycle._registry_lock:
                mcp_lifecycle._active_processes.clear()
        if hasattr(mcp_lifecycle, "_manager"):
            mcp_lifecycle._manager = None
    except ImportError:
        pass

    # Restore signal handlers
    signal.signal(signal.SIGINT, original_sigint)
    signal.signal(signal.SIGTERM, original_sigterm)
