"""Stable baseline gate — abort verifier if collection fails.

Before capturing a pytest snapshot for regression comparison, the verifier
MUST run the collection gate to ensure the test suite collects cleanly.
If any test file raises a CollectError (ImportError, SyntaxError, etc.),
the baseline is invalid and MUST NOT be used for regression comparison.

Public API
----------
verify_collection(workspace, *, test_dir="tests", timeout=120)
    → CollectionResult

    Run ``pytest --collect-only`` and return a result object.  When the
    suite does not collect cleanly, ``result.ok`` is False and
    ``result.failing_files`` lists every file that caused an error.
    Callers MUST refuse to proceed with baseline capture when ``ok`` is False.
"""

from __future__ import annotations

from bob_legacy.baseline_gate import CollectionResult, validate_collection


class BaselineUnstableError(Exception):
    """Raised when a baseline snapshot is requested but the suite does not
    collect cleanly.  Capturing a baseline in this state would fabricate
    regressions in the "after" diff, so the verifier MUST abort instead.

    The message names every file that failed to collect so the caller can
    surface an actionable diagnostic.
    """

    def __init__(self, result: CollectionResult) -> None:
        self.result = result
        files = ", ".join(result.failing_files) or "(file not identified)"
        super().__init__(
            f"baseline is unstable: pytest --collect-only failed for: {files}"
        )


def verify_collection(
    workspace,
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Run ``pytest --collect-only`` and return a :class:`CollectionResult`.

    This is the baseline gate check that the verifier must call before
    capturing a regression baseline snapshot.  If the result has ``ok=False``,
    the verifier MUST abort baseline capture — proceeding would fabricate
    regressions in the "after" diff.

    :param workspace: Path to the project root directory, or None.
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds to wait for ``pytest --collect-only``.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return validate_collection(workspace, test_dir=test_dir, timeout=timeout)


def baseline_collection_ok(
    workspace,
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> bool:
    """Return True iff the test suite collects cleanly.

    Thin boolean predicate over :func:`verify_collection` for callers that
    only need a go/no-go signal before capturing a baseline.  When this
    returns False, the baseline is invalid and MUST NOT be captured.

    Invalid ``workspace`` types or a non-positive ``timeout`` propagate as
    ``ValueError`` — this function never silently succeeds on bad input.

    :param workspace: Path to the project root directory, or None.
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds to wait for ``pytest --collect-only``.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    """
    return verify_collection(
        workspace, test_dir=test_dir, timeout=timeout
    ).ok


def assert_baseline_collects_cleanly(
    workspace,
    *,
    test_dir: str = "tests",
    timeout: int = 120,
) -> CollectionResult:
    """Verify the baseline collects cleanly or raise :class:`BaselineUnstableError`.

    This is the gate the verifier MUST call before capturing a regression
    baseline snapshot.  On a clean collection it returns the
    :class:`CollectionResult`; on any collection failure it raises
    ``BaselineUnstableError`` (naming the failing files) so the verifier
    aborts rather than capturing an invalid "before" snapshot.

    Invalid ``workspace`` types or a non-positive ``timeout`` propagate as
    ``ValueError`` — bad input is never swallowed into a clean result.

    :param workspace: Path to the project root directory, or None.
    :param test_dir: Relative path to the test directory inside workspace.
    :param timeout: Maximum seconds to wait for ``pytest --collect-only``.
    :raises ValueError: When ``workspace`` is an invalid type or ``timeout``
        is not a positive integer.
    :raises BaselineUnstableError: When the suite does not collect cleanly.
    """
    result = verify_collection(workspace, test_dir=test_dir, timeout=timeout)
    if not result.ok:
        raise BaselineUnstableError(result)
    return result


__all__ = [
    "BaselineUnstableError",
    "CollectionResult",
    "assert_baseline_collects_cleanly",
    "baseline_collection_ok",
    "verify_collection",
]
