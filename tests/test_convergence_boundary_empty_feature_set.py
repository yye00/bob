"""Tests for convergence boundary: empty feature set edge case.

Acceptance criterion:
- pytest: tests/test_convergence_boundary_empty_feature_set.py
  asserts compares_by_spec_slot([],[]) returns True (zero-element edge)
"""

from __future__ import annotations

import pytest


class TestConvergenceBoundaryEmptyFeatureSet:
    def test_compares_by_spec_slot_empty_lists_returns_true(self):
        """compares_by_spec_slot([], []) must return True — zero-element edge case."""
        from bob.orchestrator.convergence import compares_by_spec_slot

        result = compares_by_spec_slot([], [])
        assert result is True

    def test_compares_by_spec_slot_no_args_returns_true(self):
        """compares_by_spec_slot() with no arguments must return True."""
        from bob.orchestrator.convergence import compares_by_spec_slot

        assert compares_by_spec_slot() is True

    def test_compares_by_spec_slot_none_args_returns_true(self):
        """compares_by_spec_slot(None, None) must return True."""
        from bob.orchestrator.convergence import compares_by_spec_slot

        assert compares_by_spec_slot(None, None) is True

    def test_empty_set_diff_is_converged(self, tmp_path, monkeypatch):
        """Symmetric difference of two empty slot sets is empty → converged."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots
        from bob.db import init_database

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_a))
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        slots_a = get_completed_spec_slots(db_a)
        slots_b = get_completed_spec_slots(db_b)

        assert slots_a == set()
        assert slots_b == set()
        diff = slots_a.symmetric_difference(slots_b)
        assert diff == set()
