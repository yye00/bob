"""Blame-the-cause regression cascade — charge_feature_from_test entry point.

Feature 3310e08a-0932-4664-a7b2-b93bb01d88e5

Provides ``charge_feature_from_test``: given a single failing test node-id,
finds the feature whose ``pytest:`` AC owns that test path and charges it
exactly once.  Features that don't own the failing test are untouched.
"""
from __future__ import annotations

from typing import Any, Callable

__all__ = ["charge_feature_from_test"]


def charge_feature_from_test(
    *,
    failing_test: str,
    all_features: list[Any],
    increment_fn: Callable[[str], Any],
    unowned_record_fn: Callable[[Any], Any] | None = None,
) -> str | None:
    """Find the feature that owns *failing_test* and charge it.

    Walks the AC table for each feature looking for a ``pytest: <path>`` AC
    that matches *failing_test*.  If an owner is found, ``increment_fn`` is
    called with the owner's feature_id and that id is returned.  If no owner
    is found, ``unowned_record_fn`` is called (if provided) and ``None`` is
    returned.

    Args:
        failing_test: A pytest node-id such as
            ``"tests/test_foo.py::test_bar"``.
        all_features: Sequence of feature dicts or objects with ``id`` and
            ``acceptance_criteria`` fields.
        increment_fn: Called once with the owning feature_id when an owner is
            found.
        unowned_record_fn: Optional callback invoked when no owner is found.

    Returns:
        The charged feature_id, or ``None`` if the test has no owning feature.

    Raises:
        ValueError: If ``failing_test`` is not a non-empty string.
    """
    if not isinstance(failing_test, str) or not failing_test.strip():
        raise ValueError(
            f"failing_test must be a non-empty string; got {failing_test!r}"
        )

    # Lazy import to break the circular import cycle:
    # blame_feature_charger → bob3.orchestrator → bob3.run_loop → blame_feature_charger
    from bob3.orchestrator.blame_cascade import find_owner_feature, handle_unowned_failure

    owner = find_owner_feature(
        failing_test=failing_test,
        all_features=all_features,
        strict=False,
    )

    if owner is not None:
        increment_fn(owner)
        return owner

    if unowned_record_fn is not None:
        handle_unowned_failure(
            failing_test=failing_test,
            record_fn=unowned_record_fn,
        )
    return None
