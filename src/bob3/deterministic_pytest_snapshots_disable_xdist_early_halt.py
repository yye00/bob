"""Deterministic pytest snapshots — disable xdist early-halt.

pytest-xdist halts after approximately 20–25 failures non-deterministically.
When the verifier's before/after snapshots run with xdist active, different
subsets of tests are executed in each snapshot, making regression comparison
unreliable.

This module enforces ``--maxfail=0`` at the snapshot boundary so that the
full test set always runs regardless of how many tests are failing.  The
``--maxfail=0`` flag MUST be injected before any xdist ``-n`` flags so that
xdist workers cannot override it.

Public API
----------
deterministic_pytest_snapshots_disable_xdist_early_halt(workspace, *, test_dir="tests", changed_files=None)
    Capture a per-test pass/fail snapshot with early-halt disabled.  Delegates
    to :func:`bob3.orchestrator.run_loop.capture_pytest_snapshot`, which always
    includes ``--maxfail=0`` in the pytest invocation.

MAXFAIL_FLAG : str
    The flag injected at the snapshot boundary (``"--maxfail=0"``).
"""

from __future__ import annotations

MAXFAIL_FLAG = "--maxfail=0"

__all__ = [
    "MAXFAIL_FLAG",
    "deterministic_pytest_snapshots_disable_xdist_early_halt",
]


def deterministic_pytest_snapshots_disable_xdist_early_halt(
    workspace: "str | None",
    *,
    test_dir: str = "tests",
    changed_files: "list[str] | None" = None,
) -> "dict[str, bool] | None":
    """Capture a per-test pass/fail snapshot with xdist early-halt disabled.

    Enforces ``--maxfail=0`` at the snapshot boundary so that pytest-xdist
    never halts early.  Before/after snapshots thereby always cover the same
    set of test node IDs, making regression comparison reliable.

    If xdist is available in the workspace, ``-n`` workers are added AFTER
    ``--maxfail=0`` so that the no-early-halt flag cannot be overridden.

    Args:
        workspace:     Path to the project workspace.  Returns ``None`` when
                       empty or ``None``.
        test_dir:      Directory under workspace containing the test suite
                       (default ``"tests"``).
        changed_files: Optional list of repo-relative paths of source files
                       changed by the current feature, used for pytest
                       scoping (F-R6-301).

    Returns:
        ``dict[test_nodeid, passed_bool]`` on success, or ``None`` when the
        snapshot cannot be captured (workspace missing, pytest absent, timeout,
        or no recognisable verdict lines).
    """
    from bob3.orchestrator.run_loop import capture_pytest_snapshot

    return capture_pytest_snapshot(
        workspace,
        test_dir=test_dir,
        changed_files=changed_files,
    )
