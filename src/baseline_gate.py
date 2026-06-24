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


__all__ = ["CollectionResult", "verify_collection"]
