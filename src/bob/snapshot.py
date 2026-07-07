"""bob.snapshot — deterministic pytest snapshot enforcement.

pytest with xdist halts after ~20-25 failures non-deterministically.
Before/after snapshots end up containing different subsets. The snapshot
path MUST run pytest with --maxfail=0; if xdist is used, --maxfail=0
MUST be enforced at the snapshot boundary.

Public API
----------
enforce_maxfail_zero(argv) -> list[str]
    Return argv with --maxfail=0 injected and any existing --maxfail
    flag stripped, guaranteeing a deterministic snapshot regardless of
    xdist worker count.
run_pytest_snapshot(argv, runner=...) -> PytestSnapshotResult
    Enforce --maxfail=0 at the snapshot boundary and run pytest via the
    supplied runner, returning a structured result carrying the exact
    argv that was executed.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

_MAXFAIL_RE = re.compile(r"^--maxfail(=.*)?$")
MAXFAIL_ZERO = "--maxfail=0"

__all__ = [
    "enforce_maxfail_zero",
    "run_pytest_snapshot",
    "PytestSnapshotResult",
    "MAXFAIL_ZERO",
]


def enforce_maxfail_zero(argv: list[str]) -> list[str]:
    """Return argv with --maxfail=0 injected at the snapshot boundary.

    Strips any existing --maxfail flag (including non-zero values and
    duplicate --maxfail=0 entries) and injects --maxfail=0 immediately
    after the first element (the pytest command), ensuring it appears
    before any xdist -n / --numprocesses flags.

    Args:
        argv: Base pytest argument list. Must be a list of strings. May
              contain any --maxfail value; it will be replaced with
              --maxfail=0.

    Returns:
        New list with exactly one --maxfail=0, positioned at index 1
        (or index 0 when argv is empty).

    Raises:
        ValueError: If argv is not a list, or contains non-string elements.
    """
    if not isinstance(argv, list):
        raise ValueError(
            f"argv must be a list of strings, got {type(argv).__name__!r}"
        )
    for i, arg in enumerate(argv):
        if not isinstance(arg, str):
            raise ValueError(
                f"argv[{i}] must be a str, got {type(arg).__name__!r}: {arg!r}"
            )

    cleaned = [arg for arg in argv if not _MAXFAIL_RE.match(arg)]
    if cleaned:
        return [cleaned[0], MAXFAIL_ZERO] + cleaned[1:]
    return [MAXFAIL_ZERO]


@dataclass(frozen=True)
class PytestSnapshotResult:
    """Structured result of a deterministic pytest snapshot run.

    Attributes:
        argv: The exact argument list that was executed, with --maxfail=0
              guaranteed present at the snapshot boundary.
        returncode: Process exit code from the runner.
        stdout: Captured standard output (empty string if unavailable).
        stderr: Captured standard error (empty string if unavailable).
    """

    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess:
    """Run pytest argv as a subprocess, capturing output."""
    return subprocess.run(argv, capture_output=True, text=True)


def run_pytest_snapshot(argv, runner=_default_runner) -> PytestSnapshotResult:
    """Run a deterministic pytest snapshot with --maxfail=0 enforced.

    pytest-xdist halts after ~20-25 failures non-deterministically, so
    before/after snapshots capture different failure subsets. This function
    enforces --maxfail=0 at the snapshot boundary (via enforce_maxfail_zero)
    before invoking the runner, guaranteeing the full test set runs
    regardless of xdist worker count.

    Args:
        argv: Base pytest argument list (list of strings). Any existing
              --maxfail flag is stripped and replaced with --maxfail=0.
        runner: Callable taking the finalized argv and returning an object
                with ``returncode`` and, optionally, ``stdout``/``stderr``
                attributes (e.g. subprocess.CompletedProcess). Defaults to a
                real subprocess runner.

    Returns:
        PytestSnapshotResult carrying the executed argv and the runner's
        returncode/stdout/stderr.

    Raises:
        ValueError: If argv is not a list of strings, or runner is not
                    callable.
    """
    if not callable(runner):
        raise ValueError(
            f"runner must be callable, got {type(runner).__name__!r}"
        )

    final_argv = enforce_maxfail_zero(argv)
    completed = runner(final_argv)

    returncode = getattr(completed, "returncode", None)
    if returncode is None:
        raise ValueError(
            "runner result must expose a 'returncode' attribute, got "
            f"{type(completed).__name__!r}"
        )

    return PytestSnapshotResult(
        argv=final_argv,
        returncode=returncode,
        stdout=getattr(completed, "stdout", "") or "",
        stderr=getattr(completed, "stderr", "") or "",
    )
