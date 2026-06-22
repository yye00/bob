"""Tests for src/bob3/coverage_based_hack_detector.py (feature 8c495c04).

Verifies the coverage-based hack detector:
- Rejects implementations whose passing tests cover less than BOB3_MIN_COVERAGE
  percent of source lines (default 70%).
- Uses coverage.py data (JSON report format) as input.
- Returns clean when coverage meets or exceeds the threshold.
- Reads BOB3_MIN_COVERAGE from the environment with a default of 70.
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.coverage_based_hack_detector import (
    CoverageResult,
    FileCoverageInfo,
    check_coverage,
    load_coverage_report,
    measure_coverage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coverage_json(
    *,
    covered_lines: list[int],
    missing_lines: list[int],
    filename: str = "src/bob3/example.py",
) -> dict:
    """Build a minimal coverage.py JSON report structure."""
    num_executed = len(covered_lines)
    num_missing = len(missing_lines)
    num_statements = num_executed + num_missing
    percent_covered = (num_executed / num_statements * 100) if num_statements > 0 else 100.0
    return {
        "meta": {"version": "7.0.0"},
        "totals": {
            "covered_lines": num_executed,
            "num_statements": num_statements,
            "missing_lines": num_missing,
            "percent_covered": percent_covered,
        },
        "files": {
            filename: {
                "executed_lines": covered_lines,
                "missing_lines": missing_lines,
                "summary": {
                    "covered_lines": num_executed,
                    "num_statements": num_statements,
                    "missing_lines": num_missing,
                    "percent_covered": percent_covered,
                },
            }
        },
    }


# ---------------------------------------------------------------------------
# load_coverage_report
# ---------------------------------------------------------------------------


class TestLoadCoverageReport:
    def test_loads_valid_json_file(self, tmp_path: Path):
        report = _make_coverage_json(covered_lines=[1, 2, 3], missing_lines=[4])
        coverage_file = tmp_path / "coverage.json"
        coverage_file.write_text(json.dumps(report))

        result = load_coverage_report(coverage_file)
        assert result is not None
        assert "files" in result

    def test_returns_none_for_missing_file(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.json"
        result = load_coverage_report(missing)
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{")
        result = load_coverage_report(bad_file)
        assert result is None

    def test_returns_dict_for_valid_report(self, tmp_path: Path):
        report = _make_coverage_json(covered_lines=[1], missing_lines=[])
        coverage_file = tmp_path / "coverage.json"
        coverage_file.write_text(json.dumps(report))
        result = load_coverage_report(coverage_file)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# FileCoverageInfo
# ---------------------------------------------------------------------------


class TestFileCoverageInfo:
    def test_line_coverage_percent_full(self):
        info = FileCoverageInfo(
            filename="example.py",
            covered_lines=10,
            total_lines=10,
        )
        assert info.line_coverage_percent == 100.0

    def test_line_coverage_percent_partial(self):
        info = FileCoverageInfo(
            filename="example.py",
            covered_lines=7,
            total_lines=10,
        )
        assert info.line_coverage_percent == pytest.approx(70.0)

    def test_line_coverage_percent_zero(self):
        info = FileCoverageInfo(
            filename="example.py",
            covered_lines=0,
            total_lines=10,
        )
        assert info.line_coverage_percent == 0.0

    def test_line_coverage_percent_empty_file(self):
        info = FileCoverageInfo(
            filename="example.py",
            covered_lines=0,
            total_lines=0,
        )
        assert info.line_coverage_percent == 100.0


# ---------------------------------------------------------------------------
# check_coverage
# ---------------------------------------------------------------------------


class TestCheckCoverage:
    def test_passes_when_above_threshold(self):
        report = _make_coverage_json(covered_lines=list(range(1, 76)), missing_lines=list(range(76, 101)))
        result = check_coverage(report, threshold=70.0)
        assert result.is_flagged is False
        assert result.coverage_percent >= 70.0

    def test_fails_when_below_threshold(self):
        report = _make_coverage_json(covered_lines=list(range(1, 50)), missing_lines=list(range(50, 101)))
        result = check_coverage(report, threshold=70.0)
        assert result.is_flagged is True
        assert result.coverage_percent < 70.0

    def test_passes_when_exactly_at_threshold(self):
        # 70 out of 100 lines = exactly 70%
        report = _make_coverage_json(covered_lines=list(range(1, 71)), missing_lines=list(range(71, 101)))
        result = check_coverage(report, threshold=70.0)
        assert result.is_flagged is False

    def test_result_has_coverage_percent(self):
        report = _make_coverage_json(covered_lines=[1, 2, 3], missing_lines=[4])
        result = check_coverage(report, threshold=70.0)
        assert 0.0 <= result.coverage_percent <= 100.0

    def test_result_has_threshold(self):
        report = _make_coverage_json(covered_lines=[1], missing_lines=[])
        result = check_coverage(report, threshold=80.0)
        assert result.threshold == 80.0

    def test_result_has_summary(self):
        report = _make_coverage_json(covered_lines=[1, 2], missing_lines=[3])
        result = check_coverage(report, threshold=70.0)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_no_files_returns_clean(self):
        report = {"meta": {}, "totals": {}, "files": {}}
        result = check_coverage(report, threshold=70.0)
        assert result.is_flagged is False

    def test_custom_threshold_respected(self):
        report = _make_coverage_json(covered_lines=list(range(1, 91)), missing_lines=list(range(91, 101)))
        # 90% covered: passes 70% threshold but fails 95% threshold
        result_70 = check_coverage(report, threshold=70.0)
        result_95 = check_coverage(report, threshold=95.0)
        assert result_70.is_flagged is False
        assert result_95.is_flagged is True

    def test_result_includes_file_details(self):
        report = _make_coverage_json(
            covered_lines=[1, 2, 3],
            missing_lines=[4, 5],
            filename="src/bob3/mymodule.py",
        )
        result = check_coverage(report, threshold=70.0)
        assert isinstance(result.files, list)

    def test_flagged_result_has_reasoning(self):
        report = _make_coverage_json(covered_lines=[1], missing_lines=[2, 3, 4, 5])
        result = check_coverage(report, threshold=70.0)
        assert result.is_flagged is True
        assert "coverage" in result.summary.lower() or "%" in result.summary


# ---------------------------------------------------------------------------
# CoverageResult data model
# ---------------------------------------------------------------------------


class TestCoverageResult:
    def test_clean_result(self):
        result = CoverageResult(
            is_flagged=False,
            coverage_percent=85.0,
            threshold=70.0,
            summary="Coverage OK: 85.0% >= 70.0%",
            files=[],
        )
        assert result.is_flagged is False
        assert result.coverage_percent == 85.0

    def test_flagged_result(self):
        result = CoverageResult(
            is_flagged=True,
            coverage_percent=50.0,
            threshold=70.0,
            summary="Coverage too low: 50.0% < 70.0%",
            files=[],
        )
        assert result.is_flagged is True
        assert result.coverage_percent < result.threshold


# ---------------------------------------------------------------------------
# measure_coverage
# ---------------------------------------------------------------------------


class TestMeasureCoverage:
    def test_runs_and_returns_result(self, tmp_path: Path):
        # Create a minimal workspace with a trivial passing test
        src_dir = tmp_path / "src" / "mypackage"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        (src_dir / "calc.py").write_text("def add(a, b):\n    return a + b\n")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_calc.py").write_text(
            "from mypackage.calc import add\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        )

        result = measure_coverage(workspace=tmp_path, threshold=70.0)
        assert isinstance(result, CoverageResult)
        assert result.coverage_percent >= 0.0

    def test_returns_clean_when_no_tests_dir(self, tmp_path: Path):
        result = measure_coverage(workspace=tmp_path, threshold=70.0)
        assert isinstance(result, CoverageResult)
        # No tests directory → treat as clean (nothing to measure)
        assert result.is_flagged is False

    def test_uses_env_threshold_by_default(self, tmp_path: Path):
        with patch.dict(os.environ, {"BOB3_MIN_COVERAGE": "90"}):
            result = measure_coverage(workspace=tmp_path)
        assert result.threshold == 90.0

    def test_default_threshold_is_70(self, tmp_path: Path):
        env_without_coverage = {k: v for k, v in os.environ.items() if k != "BOB3_MIN_COVERAGE"}
        with patch.dict(os.environ, env_without_coverage, clear=True):
            result = measure_coverage(workspace=tmp_path)
        assert result.threshold == 70.0

    def test_explicit_threshold_overrides_env(self, tmp_path: Path):
        with patch.dict(os.environ, {"BOB3_MIN_COVERAGE": "90"}):
            result = measure_coverage(workspace=tmp_path, threshold=50.0)
        assert result.threshold == 50.0
