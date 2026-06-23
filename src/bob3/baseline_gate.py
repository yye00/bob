"""bob3.baseline_gate — stable baseline gate for the verifier.

Re-exports :func:`validate_collection` and :class:`CollectionResult` from
:mod:`bob.baseline_gate` so callers can import from the canonical bob3
namespace without depending on the ``bob`` package directly.

Public API
----------
validate_collection(workspace, *, test_dir="tests", timeout=120)
    → CollectionResult

check_collection_health(workspace, *, test_dir="tests", timeout=120)
    → CollectionResult
    Alias for :func:`validate_collection` with an intent-revealing name.
    Returns a :class:`CollectionResult`; ``result.ok`` is True when the
    suite collects cleanly.  The verifier MUST refuse to capture a baseline
    when ``ok`` is False.

abort_if_collection_fails(workspace, *, test_dir="tests", timeout=120)
    → CollectionResult
    Run the collection gate and raise :exc:`BaselineUnstableError` when any
    test file fails to collect.  The verifier MUST call this before capturing
    a regression baseline snapshot.

CollectionResult
    Dataclass returned by :func:`validate_collection` and
    :func:`check_collection_health`.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Union

from bob.baseline_gate import CollectionResult, validate_collection  # noqa: F401
import bob3.patterns  # noqa: F401 — integration: bob3.patterns

logger = logging.getLogger(__name__)


class BaselineUnstableError(Exception):
    """Raised when the test suite fails to collect cleanly before baseline capture.

    The error message includes the word "collect" and lists the failing files
    so operators can identify which test file caused the problem.
    """


def validate_baseline_collection(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Validate that the baseline test suite collects cleanly before capture.

    AC-required function name alias for :func:`validate_collection`.
    The verifier MUST call this before capturing a regression baseline.
    When ``result.ok`` is False the caller MUST NOT proceed — the "before"
    snapshot is invalid and proceeding would fabricate regressions.

    :param workspace: Path to the project root, or None (no-op, returns ok=True).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: :class:`CollectionResult` with ``ok=True`` when collection is clean.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return validate_collection(workspace, test_dir=test_dir, timeout=timeout)


def abort_on_collection_error(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Run the baseline collection gate; raise if collection fails.

    Canonical AC-required name. Delegates to :func:`abort_on_collection_failure`.

    :param workspace: Path to the project root, or None (no-op).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: :class:`CollectionResult` with ``ok=True`` when healthy.
    :raises BaselineUnstableError: When any test file fails to collect.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return abort_on_collection_failure(workspace, test_dir=test_dir, timeout=timeout)


def abort_on_collection_failure(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Run the baseline collection gate; raise if collection fails.

    :param workspace: Path to the project root, or None (no-op).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: :class:`CollectionResult` with ``ok=True`` when healthy.
    :raises BaselineUnstableError: When any test file fails to collect.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    result = validate_collection(workspace, test_dir=test_dir, timeout=timeout)
    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        logger.warning(
            "baseline_gate: collection failure — aborting baseline capture; failing files: %s",
            files,
        )
        raise BaselineUnstableError(
            f"Baseline aborted: pytest --collect-only failed for: {files}. "
            "Fix collection errors before capturing a regression baseline."
        )
    logger.debug("baseline_gate: collection clean — baseline capture may proceed")
    return result


def abort_if_collection_fails(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Abort baseline capture if the test suite fails to collect cleanly.

    This is the canonical entry point for the stable baseline gate (feature
    3710d3ed).  The verifier MUST call this before capturing a regression
    baseline snapshot.  When any test file raises a CollectError (ImportError,
    SyntaxError, etc.) the "before" snapshot is invalid — proceeding would
    fabricate regressions in the "after" diff.

    :param workspace: Path to the project root, or None (no-op, returns ok=True).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: :class:`CollectionResult` with ``ok=True`` when collection is clean.
    :raises BaselineUnstableError: When any test file fails to collect.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return abort_on_collection_failure(workspace, test_dir=test_dir, timeout=timeout)


def should_abort_on_collection_failure(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> bool:
    """Return True if the verifier should abort due to a collection failure.

    Boolean predicate variant of :func:`abort_on_collection_failure`.

    :param workspace: Path to the project root, or None (returns False when None).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: True if the verifier MUST abort; False when collection is clean.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    result = validate_collection(workspace, test_dir=test_dir, timeout=timeout)
    if not result.ok:
        files = ", ".join(result.failing_files) if result.failing_files else "<unknown>"
        logger.warning(
            "baseline_gate: collection failure — verifier should abort; failing files: %s",
            files,
        )
        return True
    logger.debug("baseline_gate: collection clean — verifier may proceed")
    return False


def check_collection_clean(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Check whether the test suite collects cleanly before baseline capture.

    Canonical entry point required by the stable baseline gate AC.  The
    verifier MUST call this before capturing a regression baseline and MUST
    refuse to proceed when ``result.ok`` is False — a collection failure
    means the "before" snapshot is invalid and any regression diff fabricates
    failures.

    :param workspace: Path to the project root, or None (no-op, returns ok=True).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: :class:`CollectionResult` with ``ok=True`` when collection is clean.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return validate_collection(workspace, test_dir=test_dir, timeout=timeout)


def check_collection_health(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Check whether the test suite collects cleanly before baseline capture.

    This is an intent-revealing alias for :func:`validate_collection`.
    The verifier MUST call this before capturing a regression baseline and
    MUST refuse to proceed when ``result.ok`` is False — a collection failure
    means the "before" snapshot is invalid and any regression diff fabricates
    failures.

    :param workspace: Path to the project root, or None (no-op, returns ok=True).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: :class:`CollectionResult` with ``ok=True`` when healthy.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return validate_collection(workspace, test_dir=test_dir, timeout=timeout)


def check_baseline_collection(
    workspace: Union[str, pathlib.Path, None],
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Gate function: verify the test suite collects cleanly before baseline capture.

    Intent-revealing entry point for the stable baseline gate.  The verifier
    MUST call this (or :func:`abort_on_collection_failure`) before capturing a
    regression baseline.  When ``result.ok`` is False the caller MUST NOT
    proceed — the "before" snapshot is invalid.

    :param workspace: Path to the project root, or None (no-op, returns ok=True).
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds for ``pytest --collect-only``.
    :returns: :class:`CollectionResult` with ``ok=True`` when collection is clean.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return validate_collection(workspace, test_dir=test_dir, timeout=timeout)


__all__ = [
    "BaselineUnstableError",
    "CollectionResult",
    "abort_if_collection_fails",
    "abort_on_collection_error",
    "abort_on_collection_failure",
    "check_baseline_collection",
    "check_collection_clean",
    "check_collection_health",
    "should_abort_on_collection_failure",
    "validate_baseline_collection",
    "validate_collection",
]
