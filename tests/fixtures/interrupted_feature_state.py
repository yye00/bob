"""Fixture data for interrupted feature state tests (92c96882).

Provides factory helpers and named constants for creating Feature-like objects
in the 'interrupted' status, used by tests/test_orchestrator_resume_scan.py
and any other test that needs to exercise the periodic-resume-scan path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Named fixture constants
# ---------------------------------------------------------------------------

INTERRUPTED_FEATURE_ID = "92c96882-0000-0000-0000-000000000001"
INTERRUPTED_FEATURE_NAME = "Sticky-completed gate"
INTERRUPTED_FEATURE_STATUS = "interrupted"

PROJECT_ID = "proj-92c96882-fixture"


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_interrupted_feature(
    *,
    feature_id: str = INTERRUPTED_FEATURE_ID,
    name: str = INTERRUPTED_FEATURE_NAME,
    status: str = INTERRUPTED_FEATURE_STATUS,
) -> MagicMock:
    """Return a MagicMock that looks like a Feature in 'interrupted' status.

    Args:
        feature_id: UUID string for the feature.
        name: Human-readable feature name.
        status: Feature status (defaults to 'interrupted').

    Returns:
        MagicMock with .id, .name, and .status attributes.
    """
    feature = MagicMock()
    feature.id = feature_id
    feature.name = name
    feature.status = status
    return feature


def make_interrupted_feature_batch(count: int = 3) -> list[Any]:
    """Return *count* MagicMock features each in 'interrupted' status.

    Useful for testing bulk-promotion paths.

    Args:
        count: Number of feature mocks to create.

    Returns:
        List of MagicMock objects with unique feature IDs.
    """
    return [
        make_interrupted_feature(
            feature_id=f"92c96882-0000-0000-0000-{i:012d}",
            name=f"Interrupted Feature {i}",
        )
        for i in range(1, count + 1)
    ]
