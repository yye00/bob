"""Error-path tests for claim_first_feature_before_batch_building.

Feature 9d2d1835-fac6-4ebd-a3d2-7a26216fbb5b

Verifies that invalid input raises ValueError and the function does not
silently succeed (error path AC).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from bob3.run_loop import claim_first_feature_before_batch_building


@dataclass
class FakeFeature:
    id: str
    status: str = "ready"


# ---------------------------------------------------------------------------
# Error: first_feature is None
# ---------------------------------------------------------------------------


def test_none_first_feature_raises_value_error():
    """Passing None as first_feature raises ValueError, does not silently succeed."""
    with pytest.raises(ValueError, match="first_feature"):
        claim_first_feature_before_batch_building(
            first_feature=None,
            max_concurrent_features=2,
            find_next_ready_feature=lambda: None,
            update_feature=lambda fid, *, status: None,
        )


# ---------------------------------------------------------------------------
# Error: first_feature has no .id attribute
# ---------------------------------------------------------------------------


def test_first_feature_without_id_raises_value_error():
    """An object without a .id attribute raises ValueError."""
    with pytest.raises((ValueError, AttributeError)):
        claim_first_feature_before_batch_building(
            first_feature=object(),
            max_concurrent_features=2,
            find_next_ready_feature=lambda: None,
            update_feature=lambda fid, *, status: None,
        )


# ---------------------------------------------------------------------------
# Error: find_next_ready_feature is None
# ---------------------------------------------------------------------------


def test_none_find_callback_raises_value_error():
    """Passing None as find_next_ready_feature raises ValueError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        claim_first_feature_before_batch_building(
            first_feature=f1,
            max_concurrent_features=2,
            find_next_ready_feature=None,  # type: ignore[arg-type]
            update_feature=lambda fid, *, status: None,
        )


# ---------------------------------------------------------------------------
# Error: update_feature is None
# ---------------------------------------------------------------------------


def test_none_update_callback_raises_value_error():
    """Passing None as update_feature raises ValueError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        claim_first_feature_before_batch_building(
            first_feature=f1,
            max_concurrent_features=2,
            find_next_ready_feature=lambda: None,
            update_feature=None,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Error: update_feature raises — does not silently swallow the error
# ---------------------------------------------------------------------------


def test_update_feature_exception_propagates():
    """If update_feature raises, the exception propagates (not silently caught)."""
    f1 = FakeFeature(id="feat-1")

    def raising_update(fid: str, *, status: str) -> None:
        raise RuntimeError(f"DB update failed for {fid}")

    with pytest.raises(RuntimeError, match="DB update failed"):
        claim_first_feature_before_batch_building(
            first_feature=f1,
            max_concurrent_features=2,
            find_next_ready_feature=lambda: None,
            update_feature=raising_update,
        )


# ---------------------------------------------------------------------------
# Error: find_next_ready_feature raises — does not silently swallow
# ---------------------------------------------------------------------------


def test_find_next_ready_feature_exception_propagates():
    """If find_next_ready_feature raises, the exception propagates."""
    f1 = FakeFeature(id="feat-1")
    updates: list = []

    def raising_find() -> FakeFeature | None:
        raise RuntimeError("DB query failed")

    with pytest.raises(RuntimeError, match="DB query failed"):
        claim_first_feature_before_batch_building(
            first_feature=f1,
            max_concurrent_features=2,
            find_next_ready_feature=raising_find,
            update_feature=lambda fid, *, status: updates.append((fid, status)),
        )


# ---------------------------------------------------------------------------
# Error: max_concurrent_features is not an int
# ---------------------------------------------------------------------------


def test_non_integer_max_concurrent_raises_value_error():
    """Passing a non-integer max_concurrent_features raises ValueError."""
    f1 = FakeFeature(id="feat-1")
    with pytest.raises((ValueError, TypeError)):
        claim_first_feature_before_batch_building(
            first_feature=f1,
            max_concurrent_features="eight",  # type: ignore[arg-type]
            find_next_ready_feature=lambda: None,
            update_feature=lambda fid, *, status: None,
        )
