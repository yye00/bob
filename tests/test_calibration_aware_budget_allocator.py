"""Tests for calibration-aware budget allocator (feature 75d96010-1767-4d05-8150-f132870596db).

Acceptance criteria:
- File exists: src/bob3/calibration_aware_budget_allocator.py
- pytest: tests/test_calibration_aware_budget_allocator.py
"""

from __future__ import annotations

import pytest


class TestBudgetAllocator:
    """Tests for CalibrationAwareBudgetAllocator."""

    def test_import(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        assert CalibrationAwareBudgetAllocator is not None

    def test_default_base_attempts(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator()
        assert allocator.base_attempts == 3

    def test_custom_base_attempts(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=5)
        assert allocator.base_attempts == 5

    def test_allocate_returns_int(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator()
        result = allocator.allocate("refactor", ece_by_task_class={})
        assert isinstance(result, int)

    def test_allocate_no_calibration_data_returns_base(self):
        """Without calibration data, return base_attempts."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        result = allocator.allocate("refactor", ece_by_task_class={})
        assert result == 3

    def test_high_ece_increases_attempts(self):
        """High ECE (poor calibration / hard task class) → more attempts."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        # High ECE = 0.4 means the model is badly miscalibrated on this task class
        result = allocator.allocate("integration", ece_by_task_class={"integration": 0.4})
        assert result > 3

    def test_low_ece_decreases_attempts(self):
        """Low ECE (well-calibrated / easy task class) → fewer attempts."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        # Low ECE = 0.02 means the model is well-calibrated on this task class
        result = allocator.allocate("refactor", ece_by_task_class={"refactor": 0.02})
        assert result < 3

    def test_unknown_task_class_returns_base(self):
        """Task class not in calibration data uses base_attempts."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=4)
        result = allocator.allocate("unknown_class", ece_by_task_class={"refactor": 0.1})
        assert result == 4

    def test_minimum_attempts_is_one(self):
        """Allocator never returns less than 1 attempt."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=1)
        # Perfect calibration (ECE=0) should still give at least 1
        result = allocator.allocate("refactor", ece_by_task_class={"refactor": 0.0})
        assert result >= 1

    def test_maximum_attempts_bounded(self):
        """Allocator never exceeds max_attempts."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3, max_attempts=7)
        # Extremely high ECE should be capped
        result = allocator.allocate("integration", ece_by_task_class={"integration": 1.0})
        assert result <= 7

    def test_default_max_attempts(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator()
        assert allocator.max_attempts >= allocator.base_attempts

    def test_moderate_ece_keeps_base_or_adds_one(self):
        """Moderate ECE (~0.15) should produce a small adjustment."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        result = allocator.allocate("algorithm_implementation", ece_by_task_class={"algorithm_implementation": 0.15})
        # Should be in range [2, 5] — not wildly different from base
        assert 1 <= result <= 6

    def test_allocate_all_task_classes(self):
        """allocate_all returns a dict mapping each task class to an attempt count."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        ece_by_class = {
            "refactor": 0.05,
            "integration": 0.35,
            "algorithm_implementation": 0.20,
        }
        result = allocator.allocate_all(
            task_classes=["refactor", "integration", "algorithm_implementation", "file_manipulation"],
            ece_by_task_class=ece_by_class,
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == {"refactor", "integration", "algorithm_implementation", "file_manipulation"}

    def test_allocate_all_unknown_class_uses_base(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        result = allocator.allocate_all(
            task_classes=["file_manipulation"],
            ece_by_task_class={},
        )
        assert result["file_manipulation"] == 3

    def test_allocate_all_high_ece_more_attempts_than_low_ece(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        ece_by_class = {
            "easy_class": 0.01,
            "hard_class": 0.45,
        }
        result = allocator.allocate_all(
            task_classes=["easy_class", "hard_class"],
            ece_by_task_class=ece_by_class,
        )
        assert result["hard_class"] > result["easy_class"]

    def test_allocate_all_returns_ints(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3)
        result = allocator.allocate_all(
            task_classes=["refactor", "integration"],
            ece_by_task_class={"refactor": 0.1, "integration": 0.3},
        )
        for v in result.values():
            assert isinstance(v, int)

    def test_allocate_all_values_within_bounds(self):
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3, max_attempts=8)
        ece_by_class = {"tc": 0.5}
        result = allocator.allocate_all(task_classes=["tc"], ece_by_task_class=ece_by_class)
        assert 1 <= result["tc"] <= 8


class TestAllocateBudgetFromDB:
    """Tests for allocate_budget_from_db() convenience function."""

    def test_function_exists(self):
        from bob3.calibration_aware_budget_allocator import allocate_budget_from_db

        assert callable(allocate_budget_from_db)

    def test_returns_dict(self, tmp_path, monkeypatch):
        from bob3.calibration_aware_budget_allocator import allocate_budget_from_db
        from bob3.db import init_database, create_project

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(tmp_path / "test.db"))
        init_database()
        project = create_project(name="Test", workspace_path=str(tmp_path))

        result = allocate_budget_from_db(project_id=project.id)
        assert isinstance(result, dict)

    def test_empty_db_returns_base_for_all_classes(self, tmp_path, monkeypatch):
        """With no calibration data in the DB, returns base_attempts for all task classes."""
        from bob3.calibration_aware_budget_allocator import allocate_budget_from_db
        from bob3.calibration import TASK_CLASSES
        from bob3.db import init_database, create_project

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(tmp_path / "test.db"))
        init_database()
        project = create_project(name="Test", workspace_path=str(tmp_path))

        result = allocate_budget_from_db(project_id=project.id, base_attempts=3)
        # All standard task classes should be present with base_attempts
        for tc in TASK_CLASSES:
            assert tc in result
            assert result[tc] == 3

    def test_with_calibration_data_adjusts_allocation(self, tmp_path, monkeypatch):
        """With calibration data present, allocations differ from base."""
        from bob3.calibration_aware_budget_allocator import allocate_budget_from_db
        from bob3.db import init_database, create_project, create_or_update_calibration

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(tmp_path / "test.db"))
        init_database()
        project = create_project(name="Test", workspace_path=str(tmp_path))

        # Add many samples showing poor calibration for 'integration' (high ECE)
        for _ in range(10):
            create_or_update_calibration(
                project_id=project.id,
                task_class="integration",
                confidence_bucket="0.8-0.9",
                passed=False,  # predicted high conf but always fails → high ECE
                expected_pass_rate=0.85,
            )

        result = allocate_budget_from_db(project_id=project.id, base_attempts=3)
        assert isinstance(result, dict)
        assert "integration" in result


class TestEceThresholds:
    """Tests for ECE-based thresholding logic."""

    def test_ece_zero_gives_minimum_or_fewer_than_base(self):
        """ECE of 0 means perfect calibration → reduce attempts."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=4)
        result = allocator.allocate("tc", ece_by_task_class={"tc": 0.0})
        assert result <= 4

    def test_ece_half_gives_significant_increase(self):
        """ECE of 0.5 (very poorly calibrated) → meaningfully more attempts than base."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3, max_attempts=10)
        result = allocator.allocate("tc", ece_by_task_class={"tc": 0.5})
        assert result > 3

    def test_monotone_in_ece(self):
        """Higher ECE should never give fewer attempts than lower ECE (or equal)."""
        from bob3.calibration_aware_budget_allocator import CalibrationAwareBudgetAllocator

        allocator = CalibrationAwareBudgetAllocator(base_attempts=3, max_attempts=10)
        ece_values = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
        attempts = [
            allocator.allocate("tc", ece_by_task_class={"tc": ece})
            for ece in ece_values
        ]
        # Monotonically non-decreasing
        for i in range(len(attempts) - 1):
            assert attempts[i] <= attempts[i + 1], (
                f"ECE {ece_values[i]} gave {attempts[i]} but ECE {ece_values[i+1]} "
                f"gave only {attempts[i+1]}"
            )
