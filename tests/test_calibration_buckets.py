"""Tests for per-task-class calibration buckets (feature 21288838-bd76-405a-9aaf-c2d5c0f889de).

Acceptance criteria:
- Function defined: bob.calibration.compute_ece_by_bucket
- pytest: tests/test_calibration_buckets.py
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Task class inference tests
# ---------------------------------------------------------------------------


class TestInferTaskClass:
    """Tests for infer_task_class() keyword heuristic."""

    def test_file_manipulation_keyword(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("Read and write configuration files to disk")
        assert result == "file_manipulation"

    def test_algorithm_implementation_keyword(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("Implement a sorting algorithm for binary search")
        assert result == "algorithm_implementation"

    def test_integration_keyword(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("Integrate with external API endpoint")
        assert result == "integration"

    def test_refactor_keyword(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("Refactor the authentication module to simplify logic")
        assert result == "refactor"

    def test_research_synthesis_keyword(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("Research and synthesize findings from multiple sources")
        assert result == "research_synthesis"

    def test_default_to_algorithm_implementation_for_unknown(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("Do some unspecified work")
        assert result == "algorithm_implementation"

    def test_case_insensitive_matching(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("REFACTOR the database layer")
        assert result == "refactor"

    def test_empty_description(self):
        from bob.calibration import infer_task_class

        result = infer_task_class("")
        assert result == "algorithm_implementation"

    def test_valid_task_classes_returned(self):
        from bob.calibration import TASK_CLASSES, infer_task_class

        descriptions = [
            "write a file to disk",
            "implement the algorithm",
            "integrate with the service",
            "refactor the module",
            "research and analyze the data",
            "completely unknown description xyz",
        ]
        for desc in descriptions:
            result = infer_task_class(desc)
            assert result in TASK_CLASSES, f"Expected one of {TASK_CLASSES}, got {result!r} for {desc!r}"


# ---------------------------------------------------------------------------
# compute_ece_by_bucket tests
# ---------------------------------------------------------------------------


class TestComputeEceByBucket:
    """Tests for compute_ece_by_bucket()."""

    def test_returns_dict(self):
        from bob.calibration import compute_ece_by_bucket

        samples = [
            {"task_class": "refactor", "predicted_conf": 0.8, "passed": True},
            {"task_class": "refactor", "predicted_conf": 0.9, "passed": True},
        ]
        result = compute_ece_by_bucket(samples)
        assert isinstance(result, dict)

    def test_empty_samples(self):
        from bob.calibration import compute_ece_by_bucket

        result = compute_ece_by_bucket([])
        assert result == {}

    def test_single_task_class_perfect_calibration(self):
        from bob.calibration import compute_ece_by_bucket

        # 10 samples: predicted=0.8, all pass → empirical=1.0, ECE=|0.8-1.0|=0.2
        samples = [
            {"task_class": "refactor", "predicted_conf": 0.8, "passed": True}
            for _ in range(10)
        ]
        result = compute_ece_by_bucket(samples)
        assert "refactor" in result
        ece = result["refactor"]
        assert isinstance(ece, float)
        assert ece >= 0.0

    def test_ece_is_mean_abs_error_per_bucket(self):
        from bob.calibration import compute_ece_by_bucket

        # Two samples in same task class, both with predicted=0.8
        # One passes, one fails → empirical=0.5 → ECE = |0.8 - 0.5| = 0.3
        samples = [
            {"task_class": "integration", "predicted_conf": 0.8, "passed": True},
            {"task_class": "integration", "predicted_conf": 0.8, "passed": False},
        ]
        result = compute_ece_by_bucket(samples)
        assert "integration" in result
        # ECE = mean(|predicted - empirical|) = |0.8 - 0.5| = 0.3
        assert abs(result["integration"] - 0.3) < 1e-9

    def test_multiple_task_classes(self):
        from bob.calibration import compute_ece_by_bucket

        samples = [
            {"task_class": "refactor", "predicted_conf": 0.9, "passed": True},
            {"task_class": "refactor", "predicted_conf": 0.9, "passed": True},
            {"task_class": "integration", "predicted_conf": 0.5, "passed": False},
            {"task_class": "integration", "predicted_conf": 0.5, "passed": False},
        ]
        result = compute_ece_by_bucket(samples)
        assert "refactor" in result
        assert "integration" in result
        # refactor: predicted=0.9, all pass → ECE = |0.9-1.0| = 0.1
        assert abs(result["refactor"] - 0.1) < 1e-9
        # integration: predicted=0.5, all fail → ECE = |0.5-0.0| = 0.5
        assert abs(result["integration"] - 0.5) < 1e-9

    def test_ece_across_multiple_confidence_levels(self):
        from bob.calibration import compute_ece_by_bucket

        # 4 samples in one bucket at different confidence levels
        # conf=0.2 pass=True, conf=0.8 pass=True, conf=0.2 pass=False, conf=0.8 pass=False
        # empirical: for bucket 0.1-0.3 → 1/2=0.5, for bucket 0.7-0.9 → 1/2=0.5
        # ECE = mean(|0.2-0.5|, |0.8-0.5|) = mean(0.3, 0.3) = 0.3
        samples = [
            {"task_class": "algorithm_implementation", "predicted_conf": 0.2, "passed": True},
            {"task_class": "algorithm_implementation", "predicted_conf": 0.8, "passed": True},
            {"task_class": "algorithm_implementation", "predicted_conf": 0.2, "passed": False},
            {"task_class": "algorithm_implementation", "predicted_conf": 0.8, "passed": False},
        ]
        result = compute_ece_by_bucket(samples)
        assert "algorithm_implementation" in result
        assert abs(result["algorithm_implementation"] - 0.3) < 1e-9

    def test_ece_bounded_zero_to_one(self):
        from bob.calibration import compute_ece_by_bucket

        samples = [
            {"task_class": "file_manipulation", "predicted_conf": 1.0, "passed": False},
            {"task_class": "file_manipulation", "predicted_conf": 0.0, "passed": True},
        ]
        result = compute_ece_by_bucket(samples)
        ece = result["file_manipulation"]
        assert 0.0 <= ece <= 1.0

    def test_all_five_task_classes_can_appear(self):
        from bob.calibration import TASK_CLASSES, compute_ece_by_bucket

        samples = [
            {"task_class": tc, "predicted_conf": 0.7, "passed": True}
            for tc in TASK_CLASSES
        ]
        result = compute_ece_by_bucket(samples)
        for tc in TASK_CLASSES:
            assert tc in result

    def test_invalid_task_class_included_in_output(self):
        from bob.calibration import compute_ece_by_bucket

        samples = [
            {"task_class": "unknown_class", "predicted_conf": 0.5, "passed": True},
        ]
        result = compute_ece_by_bucket(samples)
        assert "unknown_class" in result


# ---------------------------------------------------------------------------
# TASK_CLASSES constant tests
# ---------------------------------------------------------------------------


class TestTaskClassesConstant:
    """Tests for the TASK_CLASSES constant."""

    def test_task_classes_has_five_entries(self):
        from bob.calibration import TASK_CLASSES

        assert len(TASK_CLASSES) == 5

    def test_task_classes_contains_expected_values(self):
        from bob.calibration import TASK_CLASSES

        expected = {
            "file_manipulation",
            "algorithm_implementation",
            "integration",
            "refactor",
            "research_synthesis",
        }
        assert set(TASK_CLASSES) == expected


# ---------------------------------------------------------------------------
# CLI calibration-report command tests (smoke test via Click test runner)
# ---------------------------------------------------------------------------


class TestCalibrationReportCLI:
    """Tests for the 'bob calibration-report' CLI command."""

    def test_command_exists(self):
        from bob.cli import main

        # Verify the command is registered
        assert "calibration-report" in main.commands

    def test_command_runs_without_project(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from bob.cli import main

        monkeypatch.setenv("BOB_DATABASE_PATH", str(tmp_path / "test.db"))
        from bob.db import init_database

        init_database()

        runner = CliRunner()
        result = runner.invoke(main, ["calibration-report"])
        # Should not crash; may show "no data" or "no project" message
        assert result.exit_code == 0

    def test_command_shows_ece_data_when_available(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from bob.cli import main
        from bob.db import create_or_update_calibration, create_project, init_database

        monkeypatch.setenv("BOB_DATABASE_PATH", str(tmp_path / "test.db"))
        init_database()

        project = create_project(name="Test Project", workspace_path=str(tmp_path))
        monkeypatch.setenv("BOB_PROJECT_ID", project.id)

        # Add some calibration data
        for _ in range(5):
            create_or_update_calibration(
                project_id=project.id,
                task_class="refactor",
                confidence_bucket="0.8-0.9",
                passed=True,
                expected_pass_rate=0.85,
            )

        runner = CliRunner()
        result = runner.invoke(main, ["calibration-report"])
        assert result.exit_code == 0
        # Should show "refactor" in the output
        assert "refactor" in result.output
