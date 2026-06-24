"""Tests that _transition_to_pending_decomposition atomically updates DB."""

from unittest.mock import MagicMock, patch, call

import pytest

from bob.models import Feature
from bob.orchestrator.run_loop import (
    _transition_to_pending_decomposition,
)


def make_feature(**kwargs):
    defaults = dict(
        id="feat-persist",
        project_id="proj-001",
        name="Persist Test Feature",
        status="ready",
        refinement_attempts=2,
        readiness_score=0.65,
        max_refinement_attempts=5,
        conf_spec_understanding=0.65,
        conf_impl_correctness=0.65,
        conf_test_adequacy=0.65,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestTransitionToPendingDecomposition:
    def test_calls_db_update_with_pending_decomposition_status(self):
        f = make_feature()
        mock_updated = MagicMock()
        mock_updated.status = "pending_decomposition"

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.update_feature.return_value = mock_updated
            result = _transition_to_pending_decomposition(f)

        mock_db.update_feature.assert_called_once_with(
            f.id, status="pending_decomposition"
        )

    def test_returns_updated_feature(self):
        f = make_feature()
        mock_updated = MagicMock()
        mock_updated.status = "pending_decomposition"

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.update_feature.return_value = mock_updated
            result = _transition_to_pending_decomposition(f)

        assert result is mock_updated

    def test_status_is_pending_decomposition(self):
        f = make_feature()
        mock_updated = MagicMock()
        mock_updated.status = "pending_decomposition"

        with patch("bob.orchestrator.run_loop.db") as mock_db:
            mock_db.update_feature.return_value = mock_updated
            result = _transition_to_pending_decomposition(f)

        assert result.status == "pending_decomposition"
