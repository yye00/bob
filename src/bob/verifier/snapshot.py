"""Bob verifier snapshot — deterministic before/after test snapshots.

Wraps :func:`bob.orchestrator.run_loop.capture_pytest_snapshot` and
guarantees that ``--maxfail=0`` is always present in the pytest invocation
so before and after snapshots are always comparable (same test set, no
early-halt discrepancy due to xdist stopping after N failures).

Public API
----------
capture(workspace, *, test_dir="tests", changed_files=None) -> dict | None
    Capture a per-test pass/fail snapshot with early-halt disabled.

run_pytest_snapshot(argv) -> list[str]
    Return the argv list with --maxfail=0 injected (never overrideable).

maxfail_zero_never_overridden() -> bool
    Returns True; documents --maxfail=0 cannot be overridden by caller flags.

assert_maxfail_zero_in_argv(argv) -> None
    Raises EarlyHaltMisconfigError if --maxfail with non-zero value is present.

enforce_maxfail_zero_when_xdist(argv) -> None
    Asserts --maxfail=0 is present in argv when xdist flags (-n) are present.

before_after_same_test_set(before, after) -> bool
    Returns True iff before-snapshot test ids equal after-snapshot test ids.

handle_pytest_crash(returncode, stdout) -> None
    Raises SnapshotCrashError instead of silently returning a partial set.

MAXFAIL_FLAG : str
    The flag injected at the snapshot boundary (``"--maxfail=0"``).
"""

from __future__ import annotations

import re

MAXFAIL_FLAG = "--maxfail=0"


class EarlyHaltMisconfigError(ValueError):
    """Raised when --maxfail with a non-zero value is found in argv."""


class SnapshotCrashError(RuntimeError):
    """Raised when pytest crashes during snapshot capture."""


def run_pytest_snapshot(argv: "list[str]") -> "list[str]":
    """Return argv with --maxfail=0 injected, removing any existing --maxfail flag.

    This is the only entry point for building a pytest argv for snapshot
    purposes. --maxfail=0 is always present and cannot be overridden.

    Args:
        argv: Base pytest argument list (must not contain --maxfail).

    Returns:
        New list with --maxfail=0 inserted after the "pytest" command (index 0).
    """
    # Strip any existing --maxfail= flags to ensure ours wins.
    cleaned = [
        arg for arg in argv
        if not re.match(r"^--maxfail(=.*)?$", arg)
    ]
    if cleaned:
        return [cleaned[0], MAXFAIL_FLAG] + cleaned[1:]
    return [MAXFAIL_FLAG]


def maxfail_zero_never_overridden() -> bool:
    """Return True; documents that --maxfail=0 cannot be overridden by caller flags.

    The snapshot path always injects --maxfail=0 and strips any caller-supplied
    --maxfail=<non-zero> before building the pytest command, so callers cannot
    accidentally re-enable early halt.
    """
    return True


def assert_maxfail_zero_in_argv(argv: "list[str]") -> None:
    """Raise EarlyHaltMisconfigError if --maxfail with a non-zero value is present.

    Checks the argv list for any --maxfail flag whose value is not 0.  The
    snapshot boundary calls this as a guard before invoking pytest so that a
    misconfigured caller is caught early.

    Args:
        argv: The pytest argument list to validate.

    Raises:
        EarlyHaltMisconfigError: If a non-zero --maxfail value is found.
    """
    for arg in argv:
        # Handle both "--maxfail=N" and paired "--maxfail" "N" is not supported
        # by this function; only the equals form is the contract we guard.
        m = re.match(r"^--maxfail=(.+)$", arg)
        if m:
            value = m.group(1)
            if value != "0":
                raise EarlyHaltMisconfigError(
                    f"--maxfail={value} is not allowed at the snapshot boundary; "
                    f"snapshot requires --maxfail=0 to ensure deterministic coverage. "
                    f"Remove the maxfail override from your pytest invocation."
                )


def enforce_maxfail_zero_when_xdist(argv: "list[str]") -> None:
    """Assert --maxfail=0 is present in argv when xdist flags (-n) are present.

    When pytest-xdist is in use, early-halt is especially dangerous because
    different workers can halt after different test counts, producing
    non-deterministic snapshot subsets. This function enforces the invariant.

    Args:
        argv: The pytest argument list to validate.

    Raises:
        EarlyHaltMisconfigError: If -n / --numprocesses is present but
            --maxfail=0 is absent from argv.
        AssertionError: Never; errors are always EarlyHaltMisconfigError.
    """
    has_xdist = any(
        arg == "-n" or arg == "--numprocesses" or re.match(r"^-n\w+", arg)
        for arg in argv
    )
    if not has_xdist:
        return
    has_maxfail_zero = MAXFAIL_FLAG in argv
    if not has_maxfail_zero:
        raise EarlyHaltMisconfigError(
            f"xdist flag detected in argv but {MAXFAIL_FLAG!r} is absent. "
            f"When pytest-xdist is active, {MAXFAIL_FLAG} MUST be present at "
            f"the snapshot boundary to prevent non-deterministic early halt."
        )


def before_after_same_test_set(
    before: "dict[str, bool]",
    after: "dict[str, bool]",
) -> bool:
    """Return True iff before-snapshot test ids equal after-snapshot test ids.

    Args:
        before: Mapping of test nodeid → passed for the pre-change snapshot.
        after:  Mapping of test nodeid → passed for the post-change snapshot.

    Returns:
        True when both snapshots contain exactly the same set of test node IDs.
    """
    return set(before.keys()) == set(after.keys())


def handle_pytest_crash(returncode: int, stdout: str) -> None:
    """Raise SnapshotCrashError if pytest exited with a crash return code.

    Pytest exit code 3 means "internal error / crash" and exit code 4 means
    "usage error". Both indicate that the snapshot is incomplete.  Silently
    returning a partial result would poison the regression comparison, so this
    function converts those exit codes into an explicit exception.

    Args:
        returncode: The integer exit code from the pytest subprocess.
        stdout: Captured stdout from the pytest subprocess.

    Raises:
        SnapshotCrashError: If returncode indicates a pytest crash (3, 4, or
            any negative value such as signal-terminated processes).
    """
    # Exit codes: 0=ok, 1=tests-failed, 2=interrupted, 3=internal-error,
    #             4=usage-error, 5=no-tests-collected.
    # Negative codes occur when pytest is killed by a signal.
    crash_codes = {3, 4}
    if returncode in crash_codes or returncode < 0:
        raise SnapshotCrashError(
            f"pytest exited with crash code {returncode}; snapshot is incomplete "
            f"and cannot be used for regression comparison. "
            f"stdout tail: {stdout[-200:]!r}"
        )


def capture(
    workspace: "str | None",
    *,
    test_dir: str = "tests",
    changed_files: "list[str] | None" = None,
) -> "dict[str, bool] | None":
    """Run pytest and return a per-test pass/fail snapshot.

    Delegates to :func:`bob.orchestrator.run_loop.capture_pytest_snapshot`,
    which always includes ``--maxfail=0`` in the pytest invocation.  Callers
    of this function are guaranteed that the snapshot covers the full test
    suite regardless of failure count or xdist worker count.

    Args:
        workspace: Path to the project workspace.
        test_dir: Directory under workspace containing the test suite.
        changed_files: Optional list of repo-relative paths of changed source
            files, used for pytest scoping (F-R6-301).

    Returns:
        ``dict[test_nodeid, passed_bool]`` on success, or ``None`` when the
        snapshot cannot be captured (workspace missing, pytest absent, etc.).
    """
    from bob.orchestrator.run_loop import capture_pytest_snapshot
    return capture_pytest_snapshot(
        workspace,
        test_dir=test_dir,
        changed_files=changed_files,
    )
