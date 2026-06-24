"""Baseline collection gate for bob.verifier.

This module exposes the stable baseline gate as a first-class entry point
inside the bob verifier package.  When the test suite fails to collect
cleanly (e.g. ImportError in a test file), the "before" snapshot is invalid
and any regression diff computed against it fabricates failures.

The verifier MUST call :func:`abort_on_collection_failure` before capturing
any baseline snapshot and refuse to proceed when collection is unhealthy.

Public API
----------
abort_on_collection_failure(workspace, *, test_dir="tests", timeout=120)
    Runs ``pytest --collect-only``; raises :exc:`BaselineUnstableError` if
    any test file fails to collect.  Returns a :class:`CollectionResult` when
    the suite is healthy.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Union

from bob_legacy.baseline_gate import (
    CollectionResult,
    validate_collection,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CollectionResult",
    "BaselineUnstableError",
    "abort_on_collection_failure",
    "should_abort_on_collection_failure",
]


class BaselineUnstableError(Exception):
    """Raised by :func:`abort_on_collection_failure` when collection fails.

    The error message includes the word "collect" and lists the failing files
    so operators can identify which test file caused the problem.
    """


def abort_on_collection_failure(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Run the baseline collection gate and abort if the suite fails to collect.

    This is the canonical entry point for the verifier.  Call this before
    capturing a regression baseline snapshot.  When the suite does not collect
    cleanly, a :exc:`BaselineUnstableError` is raised and the caller MUST NOT
    proceed with baseline capture or regression comparison.

    :param workspace: Path to the project root, or None (no-op when None).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: A :class:`CollectionResult` with ``ok=True`` when healthy.
    :raises BaselineUnstableError: When any test file fails to collect.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer (propagated from :func:`validate_collection`).
    """
    result = validate_collection(workspace, test_dir=test_dir, timeout=timeout)

    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        logger.warning(
            "baseline_gate: collection failure detected — aborting baseline capture; "
            "failing files: %s",
            files,
        )
        raise BaselineUnstableError(
            f"Baseline aborted: pytest --collect-only failed for: {files}. "
            "Fix collection errors before capturing a regression baseline."
        )

    logger.debug("baseline_gate: collection clean — baseline capture may proceed")
    return result


def should_abort_on_collection_failure(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> bool:
    """Return True if the verifier should abort due to a collection failure.

    This is a boolean predicate variant of :func:`abort_on_collection_failure`.
    Instead of raising :exc:`BaselineUnstableError`, it returns ``True`` when
    the suite fails to collect cleanly, allowing callers to implement their own
    abort logic without catching exceptions.

    :param workspace: Path to the project root, or None (returns False when None).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: True if the verifier MUST abort (collection failed);
              False when collection is clean and baseline capture may proceed.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer (propagated from :func:`validate_collection`).
    """
    result = validate_collection(workspace, test_dir=test_dir, timeout=timeout)

    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        logger.warning(
            "baseline_gate: collection failure — verifier should abort; "
            "failing files: %s",
            files,
        )
        return True

    logger.debug("baseline_gate: collection clean — verifier may proceed")
    return False
