"""Error-path tests for bob3.orchestrator.resume_interrupted_work (feature 2d9615ff).

Verifies that invalid input raises ValueError and the function does not
silently succeed (error path AC).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Error path: invalid project_id raises ValueError
# ---------------------------------------------------------------------------


def test_none_project_id_raises_value_error():
    """None project_id must raise ValueError, not silently succeed."""
    from bob3.orchestrator import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work(None)  # type: ignore[arg-type]


def test_empty_string_project_id_raises_value_error():
    """Empty string project_id must raise ValueError."""
    from bob3.orchestrator import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work("")


def test_whitespace_only_project_id_raises_value_error():
    """Whitespace-only project_id must raise ValueError."""
    from bob3.orchestrator import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work("   ")


def test_integer_project_id_raises_value_error():
    """Non-string project_id (int) must raise ValueError."""
    from bob3.orchestrator import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work(42)  # type: ignore[arg-type]


def test_list_project_id_raises_value_error():
    """Non-string project_id (list) must raise ValueError."""
    from bob3.orchestrator import resume_interrupted_work
    with pytest.raises(ValueError):
        resume_interrupted_work(["proj-id"])  # type: ignore[arg-type]


def test_value_error_message_contains_received_value():
    """ValueError message must describe the invalid input received."""
    from bob3.orchestrator import resume_interrupted_work
    with pytest.raises(ValueError, match="project_id"):
        resume_interrupted_work("")


def test_value_error_raised_before_db_access():
    """ValueError must be raised before any DB call (fast-fail path)."""
    from unittest.mock import patch
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        with pytest.raises(ValueError):
            resume_interrupted_work("")
        mock_db.list_features.assert_not_called()


def test_valid_project_id_does_not_raise():
    """A valid non-empty project_id must not raise ValueError."""
    from unittest.mock import patch
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work("valid-proj-id")
    assert isinstance(result, list)


def test_uuid_style_project_id_does_not_raise():
    """A UUID-style project_id must not raise."""
    from unittest.mock import patch
    from bob3.orchestrator import resume_interrupted_work
    with patch("bob3.orchestrator.periodic_resume_scan.db") as mock_db:
        mock_db.list_features.return_value = []
        result = resume_interrupted_work("2d9615ff-4181-4546-836e-4dbbfafd5bad")
    assert isinstance(result, list)
