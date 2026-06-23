"""Stable baseline gate — abort verifier if collection fails.

Public API for the bob73 package: :func:`validate_collection`.

Delegates to :mod:`bob.baseline_gate` which implements the collection
gate logic.  When a pytest collection run returns exit code 2 (collection
error), the baseline is marked invalid and callers MUST refuse to capture
a regression snapshot against it.

Usage::

    from bob73.baseline_gate import validate_collection, CollectionResult

    result = validate_collection(workspace="/path/to/project", test_dir="tests")
    if not result.ok:
        raise RuntimeError(
            f"Baseline unstable — collection errors in: {result.failing_files}"
        )
"""

from bob.baseline_gate import CollectionResult, validate_collection

__all__ = ["CollectionResult", "validate_collection"]
