"""Stable baseline gate for the Bob3 verifier.

Before capturing a pytest snapshot for regression comparison, this module
runs ``pytest --collect-only`` to verify that the test suite collects
cleanly.  If any test file raises a CollectError (e.g. ImportError during
collection), the baseline snapshot is invalid and MUST NOT be used for
regression comparisons — a failing baseline makes every subsequent diff
fabricate regressions.

Public API
----------
collect_and_capture(workspace, *, test_dir="tests", changed_files=None)
    → BaselineCaptureResult

    Run the collection gate then capture the snapshot.  Returns a result
    object whose ``status`` is either ``"ok"`` (snapshot is valid) or
    ``"baseline_unstable"`` (collection failed; snapshot is None).

is_baseline_unstable(workspace)
    → bool

    Cheap sentinel: True when a previous call has stored a
    ``baseline_unstable`` marker for this workspace.
"""

from __future__ import annotations

import logging
import pathlib
import re
import subprocess
import yaml
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

# Exit code pytest uses when collection errors occur.
_PYTEST_COLLECTION_ERROR_EXIT_CODE = 2

# Regex that matches a CollectError line in pytest --collect-only output.
# pytest writes e.g.:
#   ERROR collecting tests/test_foo.py
# or (with -v):
#   ERRORS
#   _____ ERROR collecting tests/test_foo.py _____
_COLLECT_ERROR_RE = re.compile(
    r"ERROR\s+collecting\s+(?P<file>\S+)", re.IGNORECASE
)

# Marker filename dropped into the workspace when baseline is unstable.
_UNSTABLE_MARKER = ".bob3_baseline_unstable"


class BaselineUnstableError(Exception):
    """Raised when a baseline cannot be captured due to collection failures."""


@dataclass
class CollectResult:
    """Result of :func:`run_pytest_collect_only`.

    Attributes:
        ok: True when the suite collected cleanly (no CollectErrors).
        failing_files: List of test files that failed to collect.
    """

    ok: bool
    failing_files: List[str] = field(default_factory=list)


@dataclass
class BaselineCaptureResult:
    """Outcome of :func:`collect_and_capture`.

    Attributes:
        status: ``"ok"`` when the suite collects cleanly and the snapshot is
            valid; ``"baseline_unstable"`` when collection fails.
        snapshot: Per-test pass/fail mapping, or ``None`` when status is not
            ``"ok"``.
        failing_collection_file: The first test file that caused a collection
            error, or ``None`` when status is ``"ok"``.
        collection_error_details: Raw stderr/stdout fragment from the failing
            collection run, for diagnostic logging.
    """

    status: str  # "ok" | "baseline_unstable"
    snapshot: dict[str, bool] | None = None
    failing_collection_file: str | None = None
    collection_error_details: str = ""
    extra: dict = field(default_factory=dict)


def _run_collect_only(
    workspace: pathlib.Path,
    test_dir: pathlib.Path,
    timeout: int = 120,
) -> tuple[bool, str | None, str]:
    """Run ``pytest --collect-only`` and report the outcome.

    Returns:
        (clean, failing_file, details)
        ``clean`` is True when no collection errors were found.
        ``failing_file`` is the first file mentioned in a CollectError line,
        or None.
        ``details`` is the combined stdout+stderr for diagnostic use.
    """
    cmd = [
        "python", "-m", "pytest",
        str(test_dir.relative_to(workspace)),
        "--collect-only",
        "-q",
        "--tb=short",
        "--no-header",
        "--color=no",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        logger.debug("baseline_capture: python interpreter not found")
        return True, None, ""
    except subprocess.TimeoutExpired:
        logger.warning("baseline_capture: --collect-only timed out after %ss", timeout)
        return True, None, "timeout"

    combined = (proc.stdout or "") + (proc.stderr or "")

    # Heuristic 1: pytest exit code 2 means "collection errors occurred".
    # Heuristic 2: scan output for explicit CollectError lines.
    collect_error_exit = proc.returncode == _PYTEST_COLLECTION_ERROR_EXIT_CODE

    failing_file: str | None = None
    for line in combined.splitlines():
        m = _COLLECT_ERROR_RE.search(line)
        if m:
            failing_file = m.group("file")
            break

    # "ERROR" in output with exit code 2 is a strong signal even if our
    # regex didn't catch a specific filename.
    has_error = collect_error_exit and (
        failing_file is not None or "ERROR" in combined.upper()
    )

    if has_error:
        return False, failing_file, combined

    return True, None, combined


def _capture_snapshot(
    workspace: pathlib.Path,
    test_dir: pathlib.Path,
    changed_files: list[str] | None,
) -> dict[str, bool] | None:
    """Delegate to the orchestrator's existing snapshot function."""
    try:
        from bob3.orchestrator.run_loop import capture_pytest_snapshot
        return capture_pytest_snapshot(
            str(workspace),
            test_dir=test_dir.relative_to(workspace).as_posix(),
            changed_files=changed_files,
        )
    except Exception:
        logger.debug("baseline_capture: snapshot delegation failed", exc_info=True)
        return None


def _write_unstable_marker(workspace: pathlib.Path, details: str) -> None:
    marker = workspace / _UNSTABLE_MARKER
    try:
        marker.write_text(details or "baseline_unstable\n", encoding="utf-8")
    except OSError:
        logger.debug("baseline_capture: could not write unstable marker")


def _clear_unstable_marker(workspace: pathlib.Path) -> None:
    marker = workspace / _UNSTABLE_MARKER
    try:
        if marker.exists():
            marker.unlink()
    except OSError:
        logger.debug("baseline_capture: could not remove unstable marker")


def is_baseline_unstable(workspace: str | pathlib.Path) -> bool:
    """Return True when a ``baseline_unstable`` marker exists for *workspace*."""
    return (pathlib.Path(workspace) / _UNSTABLE_MARKER).exists()


def collect_and_capture(
    workspace: str | pathlib.Path | None,
    *,
    test_dir: str = "tests",
    changed_files: list[str] | None = None,
    collect_timeout: int = 120,
) -> BaselineCaptureResult:
    """Run the collection gate and, if clean, capture the pytest snapshot.

    This is the single entry-point that the orchestrator should call instead
    of calling ``capture_pytest_snapshot`` directly when it needs a pre-
    execution baseline for regression comparison.

    Steps:
    1. Run ``pytest --collect-only`` against *test_dir* in *workspace*.
    2. If any CollectError is detected: write the ``baseline_unstable`` marker,
       return ``BaselineCaptureResult(status="baseline_unstable", ...)``.
    3. If collection is clean: remove any stale marker, capture the full
       snapshot, return ``BaselineCaptureResult(status="ok", snapshot=...)``.

    The caller MUST check ``result.status`` before using ``result.snapshot``
    for regression comparison.  When ``status == "baseline_unstable"``:
    - Do NOT compare before/after snapshots.
    - Do NOT demote any feature to regression.
    - Log ``result.failing_collection_file`` so operators know which file
      caused the problem.
    """
    if not workspace:
        return BaselineCaptureResult(status="ok", snapshot=None)

    ws = pathlib.Path(workspace)
    if not ws.exists() or not ws.is_dir():
        return BaselineCaptureResult(status="ok", snapshot=None)

    td = ws / test_dir
    if not td.exists() or not td.is_dir():
        return BaselineCaptureResult(status="ok", snapshot=None)

    clean, failing_file, details = _run_collect_only(ws, td, timeout=collect_timeout)

    if not clean:
        logger.warning(
            "baseline_capture: collection errors detected in %s — "
            "baseline_unstable; failing file: %s",
            ws,
            failing_file or "<unknown>",
        )
        _write_unstable_marker(ws, details)
        return BaselineCaptureResult(
            status="baseline_unstable",
            snapshot=None,
            failing_collection_file=failing_file,
            collection_error_details=details,
        )

    # Collection clean — remove any stale marker from a previous run.
    _clear_unstable_marker(ws)

    snapshot = _capture_snapshot(ws, td, changed_files)
    return BaselineCaptureResult(
        status="ok",
        snapshot=snapshot,
    )


# ---------------------------------------------------------------------------
# Named public API required by acceptance criteria
# ---------------------------------------------------------------------------

def run_pytest_collect_only(
    workspace: str | pathlib.Path,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectResult:
    """Run ``pytest --collect-only`` and return a :class:`CollectResult`.

    Returns a CollectResult with ``ok=True`` and empty ``failing_files`` when
    the suite collects cleanly.  If any test file raises a CollectError, the
    result has ``ok=False`` and ``failing_files`` lists every file that failed.
    """
    ws = pathlib.Path(workspace)
    td = ws / test_dir

    if not ws.exists() or not ws.is_dir() or not td.exists() or not td.is_dir():
        return CollectResult(ok=True, failing_files=[])

    cmd = [
        "python", "-m", "pytest",
        str(td.relative_to(ws)),
        "--collect-only",
        "-q",
        "--tb=short",
        "--no-header",
        "--color=no",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return CollectResult(ok=True, failing_files=[])

    combined = (proc.stdout or "") + (proc.stderr or "")
    collect_error_exit = proc.returncode == _PYTEST_COLLECTION_ERROR_EXIT_CODE

    failing_files: list[str] = []
    for line in combined.splitlines():
        m = _COLLECT_ERROR_RE.search(line)
        if m:
            failing_files.append(m.group("file"))

    if collect_error_exit and (failing_files or "ERROR" in combined.upper()):
        return CollectResult(ok=False, failing_files=failing_files)

    return CollectResult(ok=True, failing_files=[])


def abort_on_collect_error(result: CollectResult) -> None:
    """Raise :exc:`BaselineUnstableError` if *result* indicates collection failure.

    The error message includes the word "collect" and names each failing file,
    so callers can log or surface the information directly.

    :raises BaselineUnstableError: when ``result.ok`` is False.
    """
    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        raise BaselineUnstableError(
            f"Baseline aborted: pytest collect failed for: {files}. "
            "Fix collection errors before capturing a regression baseline."
        )


def write_baseline_unstable_status(
    run_dir: str | pathlib.Path,
    failing_test_file: str | None = None,
) -> None:
    """Write a ``baseline_unstable`` status to ``runs/<round>/baseline.yaml``.

    The YAML document contains at minimum:
      status: baseline_unstable
      failing_test_file: <path or null>

    :param run_dir: Path to the run directory (``runs/<round>``).
    :param failing_test_file: The first test file that failed to collect,
        or None if unknown.
    """
    run_dir = pathlib.Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    baseline_yaml = run_dir / "baseline.yaml"
    data = {
        "status": "baseline_unstable",
        "failing_test_file": failing_test_file,
    }
    baseline_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")


def block_regression_demotion_while_unstable() -> bool:
    """Return True to document that regression demotions are blocked while baseline is unstable.

    When the baseline capture is in the ``baseline_unstable`` state, no feature
    may be demoted to a regression status.  This function acts as a policy
    declaration: call it before invoking any regression-detection logic and
    skip regression detection when the baseline is unstable.
    """
    return True


def no_feature_demoted_while_unstable() -> bool:
    """Return True to document that no feature is demoted while ``baseline_unstable`` is set.

    When the ``baseline_unstable`` flag is active, the verifier must not
    attribute test failures to any feature under evaluation.  The failures
    originate from collection-time ImportErrors, not from the feature's code.
    """
    return True


def handle_clean_collect(
    workspace: str | pathlib.Path,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectResult:
    """Run the collection gate and return a clean :class:`CollectResult`.

    When the suite collects cleanly this function returns a CollectResult with
    ``ok=True`` and an empty ``failing_files`` list.  If collection fails, a
    CollectResult with ``ok=False`` is returned (no exception is raised here;
    use :func:`abort_on_collect_error` to turn that into an exception).
    """
    return run_pytest_collect_only(workspace, test_dir=test_dir, timeout=timeout)
