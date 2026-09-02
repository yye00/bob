"""Shared test fixtures and isolation hooks for bob tests.

Several modules under ``bob`` keep state at module level (memoized
singletons, dedup sets, signal handlers). When tests run in the same
interpreter process, that state leaks between tests and causes
order-dependent failures. The autouse fixture in this file resets
the known leak points after every test.

Specifically reset:

- ``bob.orchestrator.run_loop._PROXY_LOGGED_FEATURE_IDS`` — bounded
  dedup set used by proxy-cost logging.
- ``bob.mcp_lifecycle._active_processes`` — registry mapping config
  names to live MCP subprocesses. Cleared (NOT killed); each owner is
  responsible for stopping its own process via its ``stop()`` method.
- ``bob.mcp_lifecycle._manager`` — global MCPLifecycleManager
  singleton built lazily by ``get_mcp_manager``.
- Signal handlers installed by ``OrchestrationLoop._install_signal_handlers``
  for SIGINT and SIGTERM.
- bob-relevant environment variables (``BOB_DATABASE_PATH``,
  ``BOB_MEMORY_DIR``, ``BOB_COST_PER_TURN_PROXY``, ...) are captured
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


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --mutation-score-threshold CLI option (AC: CLI command)."""
    parser.addoption(
        "--mutation-score-threshold",
        action="store",
        default=None,
        type=float,
        help=(
            "Minimum mutation score (0.0–1.0) required to pass the mutation gate. "
            "Default: 0.75. Overrides MUTATION_SCORE_THRESHOLD when set."
        ),
    )


# Env vars known to influence bob module behaviour. Anything a test
# might touch directly (instead of via ``monkeypatch.setenv``) belongs
# here, otherwise the value leaks to the next test. Restoring is done
# by *capture-and-restore* (not unconditional ``pop``) so a value
# legitimately set by the surrounding pytest invocation (e.g. CI) is
# preserved.
_BOB_ENV_VARS_TO_SNAPSHOT = (
    "BOB_DATABASE_PATH",
    "BOB_MEMORY_DIR",
    "BOB_COST_PER_TURN_PROXY",
    "BOB_SNAPSHOT_TIMEOUT",
    "BOB_TEST_RUN_TIMEOUT",
    # R10-010 / R10-011: orchestration tuning knobs read by run_loop.py
    "BOB_FAILURE_THRESHOLD_FOR_RESEARCH",
    "BOB_CONFIDENCE_DECAY_PER_FAILURE",
    "BOB_RCA_TIMEOUT_SECONDS",
    "BOB_RCA_MAX_TURNS",
    "BOB_RCA_ENABLED",
    # Round 0 Task 1 (Gap #1): independent evaluator agent
    "BOB_EVALUATOR_ENABLED",
    "BOB_EVALUATOR_REQUIRED",
    "BOB_EVALUATOR_TIMEOUT_SECONDS",
    "BOB_EVALUATOR_MAX_TURNS",
    "BOB_INDEPENDENT_TEST_WRITER",
    "BOB_TEST_ROOTS",
    "BOB_FEATURE_TIMEOUT_SECONDS",
    "BOB_MAX_REFINEMENT_ATTEMPTS",
    "BOB_MAX_COST_USD",
    # Autonomous runtime: dedicated research-agent provider boundary and
    # optional unlimited Claude Code turn budget.
    "BOB_RESEARCH_MODE",
    "BOB_CLAUDE_HERMETIC",
    "BOB_REQUIRED_MODEL",
    "BOB_SUB_AGENT_MAX_TURNS",
    "BOB_PER_ATTEMPT_COST_CAP",
    # Frozen-registry mode
    "BOB_FROZEN_REGISTRY",
    # F-R6-307: pre-spawn cost projection gate. Default-disabled in tests
    # so existing cost-arithmetic tests (which use $1 caps and don't
    # populate history) keep passing. Tests that exercise the gate
    # itself set this explicitly via monkeypatch.
    "BOB_COST_PROJECTION_GATE",
)


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset bob module-level state between tests for isolation."""
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
        k: os.environ.get(k) for k in _BOB_ENV_VARS_TO_SNAPSHOT
    }

    # R10-009: ``execute_feature``'s failure path now invokes
    # ``spawn_rca_agent`` once the second-or-later attempt fails. In
    # production this is desired; in tests, however, we don't want
    # every failure-path test to launch a real Claude SDK subprocess.
    # Default ``BOB_RCA_ENABLED=0`` so pre-existing tests behave
    # exactly as they did before R10-009 was wired in. Tests that
    # need RCA to fire (test_r10_failure_recovery.py) explicitly
    # mock ``spawn_rca_agent`` AND/OR set ``BOB_RCA_ENABLED=1``.
    # Mocking at ``bob.orchestrator.run_loop.spawn_rca_agent``
    # short-circuits the SDK call regardless of this flag.
    if "BOB_RCA_ENABLED" not in os.environ:
        os.environ["BOB_RCA_ENABLED"] = "0"

    # R10-011: confidence decay per failed attempt is on by default in
    # production (0.15) so the low-confidence research trigger
    # (Trigger 3 in ``needs_research``) re-fires on retries. In tests,
    # however, decay can push confidence below 0.5 mid-test and cause
    # ``_run_research`` to spawn a real research sub-agent (most
    # pre-R10 retry tests do not mock ``spawn_research_agent``).
    # Default decay to 0.0 here so failure-path tests behave as they
    # did before R10-011 was wired in. Tests that exercise decay
    # explicitly (test_r10_failure_recovery.py) override via
    # ``monkeypatch.setenv("BOB_CONFIDENCE_DECAY_PER_FAILURE", ...)``
    # or call ``_decay_confidence_after_failure`` directly.
    if "BOB_CONFIDENCE_DECAY_PER_FAILURE" not in os.environ:
        os.environ["BOB_CONFIDENCE_DECAY_PER_FAILURE"] = "0"

    # Round 0 Task 1 (Gap #1): the verification-passed branch in
    # ``execute_feature`` now invokes ``spawn_evaluator_agent`` before
    # committing. In production this is desired; in tests, however, we
    # don't want every commit-path test to launch a real Claude SDK
    # subprocess (the existing tests mock ``spawn_sub_agent`` at the
    # ``run_loop`` import site, which does not intercept the evaluator's
    # internal call into ``claude_executor.spawn_sub_agent``). Default
    # ``BOB_EVALUATOR_ENABLED=0`` so pre-existing tests behave exactly
    # as they did before the evaluator was wired in. Tests that need
    # the evaluator to fire (test_evaluator_agent.py) mock
    # ``spawn_evaluator_agent`` directly OR set ``BOB_EVALUATOR_ENABLED=1``.
    if "BOB_EVALUATOR_ENABLED" not in os.environ:
        os.environ["BOB_EVALUATOR_ENABLED"] = "0"

    # F-R6-307: pre-spawn cost projection gate. In production this is on
    # and refuses spawns when the projected total would blow past the
    # cap. In tests, however, most cost-arithmetic tests use $1 caps with
    # no historical run data, which trips the conservative fallback
    # estimate ($1.50) and turns every spawn into a needs_human transition.
    # Default the gate OFF here so pre-existing tests behave exactly as
    # they did before F-R6-307 was wired in. Tests that exercise the gate
    # itself (test_cost_projection.py::test_run_loop_integration_...)
    # explicitly enable it via monkeypatch.
    if "BOB_COST_PROJECTION_GATE" not in os.environ:
        os.environ["BOB_COST_PROJECTION_GATE"] = "0"

    yield

    # Reset module-level state
    try:
        import bob.registry_transfer as _rt
        _rt._FROZEN = False
    except ImportError:
        pass

    try:
        from bob.orchestrator import run_loop
        if hasattr(run_loop, "_PROXY_LOGGED_FEATURE_IDS"):
            run_loop._PROXY_LOGGED_FEATURE_IDS.clear()
    except ImportError:
        pass

    try:
        from bob import mcp_lifecycle
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
