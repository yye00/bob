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
- bob3-relevant environment variables (``BOB3_DATABASE_PATH``,
  ``BOB3_MEMORY_DIR``, ``BOB3_COST_PER_TURN_PROXY``, ...) are captured
  at fixture entry and restored at teardown so a test that calls
  ``os.environ[...] = ...`` directly (i.e. not via ``monkeypatch``)
  does not leak its setting into the next test.

The fixture also captures and restores the original SIGINT/SIGTERM
handlers around each test so a test that installs its own handler
cannot affect the next test.
"""

from __future__ import annotations

import os
import signal

import pytest


# Env vars known to influence bob3 module behaviour. Anything a test
# might touch directly (instead of via ``monkeypatch.setenv``) belongs
# here, otherwise the value leaks to the next test. Restoring is done
# by *capture-and-restore* (not unconditional ``pop``) so a value
# legitimately set by the surrounding pytest invocation (e.g. CI) is
# preserved.
_BOB3_ENV_VARS_TO_SNAPSHOT = (
    "BOB3_DATABASE_PATH",
    "BOB3_MEMORY_DIR",
    "BOB3_COST_PER_TURN_PROXY",
    "BOB3_SNAPSHOT_TIMEOUT",
    "BOB3_TEST_RUN_TIMEOUT",
)


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset bob3 module-level state between tests for isolation."""
    # Capture original signal handlers so we can restore them even if
    # a test installs its own (e.g. via OrchestrationLoop._install_signal_handlers).
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)

    # Snapshot env-var state. ``None`` means "was unset"; any string
    # means "was set to this value". We restore exactly that on
    # teardown so:
    #   - if the var was unset and the test set it -> we pop it
    #   - if the var was set and the test changed/unset it -> we restore the original
    #   - if neither, we leave it alone
    saved_env: dict[str, str | None] = {
        k: os.environ.get(k) for k in _BOB3_ENV_VARS_TO_SNAPSHOT
    }

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

    # Restore env-var state. Doing this AFTER the module-state resets
    # so that any module that lazily reads an env var on first use
    # observes the test's setting during the test body but the
    # *next* test starts from the captured baseline.
    for k, original_value in saved_env.items():
        if original_value is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = original_value
