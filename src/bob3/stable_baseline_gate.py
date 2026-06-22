"""Stable baseline gate — abort verifier if collection fails.

When baseline pytest crashes at collection (e.g. ImportError in a test file),
the "before" snapshot is invalid.  Any "after" diff computed against that
snapshot fabricates regressions that do not exist.

This module provides :func:`enforce_stable_baseline_gate` as the canonical
public entry-point.  The verifier MUST call this before capturing a regression
baseline and MUST refuse to proceed when collection is unhealthy.

Usage::

    from bob3.stable_baseline_gate import enforce_stable_baseline_gate

    try:
        result = enforce_stable_baseline_gate(workspace="/path/to/workspace")
    except BaselineUnstableError as exc:
        # abort — do not compare before/after snapshots
        log.error("Baseline gate failed: %s", exc)
        return

    # collection clean — result.ok is True, proceed with baseline capture
    snapshot = result.snapshot
"""

from __future__ import annotations

import logging
import pathlib
from typing import Union

from bob.baseline_gate import CollectionResult, validate_collection  # noqa: F401

logger = logging.getLogger(__name__)


class BaselineUnstableError(Exception):
    """Raised when a baseline cannot be captured due to collection failures.

    The error message includes the word "collect" and names the failing files
    so callers can log or surface diagnostic information.
    """


def enforce_stable_baseline_gate(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Enforce the stable baseline gate: abort the verifier if collection fails.

    This is the single canonical entry-point for the stable baseline gate.
    Call this before capturing any regression baseline snapshot.  When the test
    suite fails to collect cleanly (e.g. ImportError in a test file), this
    function raises :exc:`BaselineUnstableError` and the caller MUST NOT
    proceed with baseline capture or regression comparison — the "before"
    snapshot would be invalid and any diff would fabricate regressions.

    :param workspace: Path to the project root, or None (no-op, returns
        ok=True without running pytest).
    :param test_dir: Relative path to the test directory inside *workspace*.
        Defaults to ``"tests"``.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
        Must be a positive integer. Defaults to 120.
    :returns: :class:`CollectionResult` with ``ok=True`` when the suite
        collects cleanly and baseline capture may proceed.
    :raises BaselineUnstableError: When any test file fails to collect.
        The error message includes the word "collect" and lists the failing
        files so callers can log diagnostic information.
    :raises ValueError: When *workspace* is an invalid type (not str, Path,
        or None) or *timeout* is not a positive integer.
    """
    result = validate_collection(workspace, test_dir=test_dir, timeout=timeout)

    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        logger.warning(
            "stable_baseline_gate: collection failure — aborting baseline capture; "
            "failing files: %s",
            files,
        )
        raise BaselineUnstableError(
            f"Baseline aborted: pytest collect failed for: {files}. "
            "Fix collection errors before capturing a regression baseline."
        )

    logger.debug("stable_baseline_gate: collection clean — baseline capture may proceed")
    return result


def should_abort_on_collection_failure(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> bool:
    """Return True if the verifier should abort due to a collection failure.

    Boolean predicate variant: instead of raising :exc:`BaselineUnstableError`,
    returns ``True`` when the suite fails to collect cleanly.

    :param workspace: Path to the project root, or None (returns False).
    :param test_dir: Relative path to the test directory inside *workspace*.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: True if collection failed (verifier MUST abort);
              False when collection is clean and baseline capture may proceed.
    :raises ValueError: When *workspace* is an invalid type or *timeout* is
        not a positive integer.
    """
    result = validate_collection(workspace, test_dir=test_dir, timeout=timeout)
    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        logger.warning(
            "stable_baseline_gate: collection failure — verifier should abort; "
            "failing files: %s",
            files,
        )
        return True
    logger.debug("stable_baseline_gate: collection clean — verifier may proceed")
    return False


def check_baseline_collection(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Check whether the test suite collects cleanly before baseline capture.

    Gate function for the stable baseline gate feature.  The verifier MUST
    call this before capturing a regression baseline snapshot.  When the
    result's ``ok`` attribute is False, the caller MUST NOT proceed — the
    "before" snapshot is invalid and any diff would fabricate regressions.

    Unlike :func:`enforce_stable_baseline_gate`, this function does NOT raise
    on collection failure.  Instead it returns a :class:`CollectionResult`
    with ``ok=False`` so callers can decide how to handle the failure.

    :param workspace: Path to the project root, or None (no-op, returns
        ok=True without running pytest).
    :param test_dir: Relative path to the test directory inside *workspace*.
        Defaults to ``"tests"``.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
        Must be a positive integer. Defaults to 120.
    :returns: :class:`CollectionResult` with ``ok=True`` when the suite
        collects cleanly.  When ``ok`` is False, ``failing_files`` lists the
        files that raised CollectError.
    :raises ValueError: When *workspace* is an invalid type or *timeout* is
        not a positive integer.
    """
    result = validate_collection(workspace, test_dir=test_dir, timeout=timeout)
    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        logger.warning(
            "stable_baseline_gate: collection failure — baseline capture MUST be aborted; "
            "failing files: %s",
            files,
        )
    else:
        logger.debug("stable_baseline_gate: collection clean — baseline capture may proceed")
    return result


# Alias for compatibility with bob3.verifier namespace
abort_on_collection_failure = enforce_stable_baseline_gate


__all__ = [
    "BaselineUnstableError",
    "CollectionResult",
    "abort_on_collection_failure",
    "check_baseline_collection",
    "enforce_stable_baseline_gate",
    "should_abort_on_collection_failure",
    "validate_collection",
]
