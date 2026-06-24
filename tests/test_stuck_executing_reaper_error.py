"""Error-path tests for bob.reaper.detect_stuck_executing / reset_stuck_feature.

AC: pytest: tests/test_stuck_executing_reaper_error.py — invalid input raises
ValueError and the function does not silently succeed (error path).
"""

from __future__ import annotations

import pytest

from bob.reaper import detect_stuck_executing, reset_stuck_feature


# ---------------------------------------------------------------------------
# detect_stuck_executing error cases
# ---------------------------------------------------------------------------


class TestDetectStuckExecutingErrorPath:
    def test_empty_project_id_raises_value_error(self):
        """Empty string project_id must raise ValueError, not silently return."""
        with pytest.raises(ValueError, match="project_id"):
            detect_stuck_executing("")

    def test_none_project_id_raises_value_error(self):
        """None project_id must raise ValueError."""
        with pytest.raises((ValueError, TypeError)):
            detect_stuck_executing(None)  # type: ignore[arg-type]

    def test_negative_heartbeat_timeout_raises_value_error(self):
        """Negative heartbeat_timeout_seconds must raise ValueError."""
        with pytest.raises(ValueError, match="heartbeat_timeout_seconds"):
            detect_stuck_executing("proj-valid", heartbeat_timeout_seconds=-1)

    def test_very_negative_heartbeat_timeout_raises_value_error(self):
        """Very negative heartbeat_timeout_seconds must raise ValueError."""
        with pytest.raises(ValueError, match="heartbeat_timeout_seconds"):
            detect_stuck_executing("proj-valid", heartbeat_timeout_seconds=-9999)

    def test_empty_project_id_does_not_silently_return_list(self):
        """Empty project_id must not silently succeed and return an empty list."""
        try:
            result = detect_stuck_executing("")
            # If it gets here without raising, that's the silent success failure mode
            pytest.fail(
                f"detect_stuck_executing('') silently returned {result!r} "
                "instead of raising ValueError"
            )
        except (ValueError, TypeError):
            pass  # Expected — error path behaves correctly


# ---------------------------------------------------------------------------
# reset_stuck_feature error cases
# ---------------------------------------------------------------------------


class TestResetStuckFeatureErrorPath:
    def test_none_feature_raises_value_error(self):
        """None feature must raise ValueError, not silently succeed."""
        with pytest.raises(ValueError):
            reset_stuck_feature(None)  # type: ignore[arg-type]

    def test_feature_without_id_raises_value_error(self):
        """An object that lacks an 'id' attribute must raise ValueError."""

        class NoIdObject:
            status = "executing"

        with pytest.raises(ValueError):
            reset_stuck_feature(NoIdObject())  # type: ignore[arg-type]

    def test_none_feature_does_not_silently_succeed(self):
        """Passing None must not silently complete without raising."""
        try:
            reset_stuck_feature(None)  # type: ignore[arg-type]
            pytest.fail(
                "reset_stuck_feature(None) did not raise — it silently succeeded, "
                "which hides a programming error"
            )
        except (ValueError, AttributeError, TypeError):
            pass  # Any of these exception types is acceptable; silent success is not

    def test_non_feature_dict_raises(self):
        """Plain dict without 'id' attribute must not silently succeed."""
        with pytest.raises((ValueError, AttributeError)):
            reset_stuck_feature({"id": "fake-id"})  # type: ignore[arg-type]
