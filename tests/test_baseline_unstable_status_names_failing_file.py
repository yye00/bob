"""Tests for bob.verifier.baseline_capture — write_baseline_unstable_status.

Verifies that write_baseline_unstable_status writes a baseline.yaml with
status=baseline_unstable and the correct failing_test_file field.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

from bob.verifier.baseline_capture import write_baseline_unstable_status


class TestWriteBaselineUnstableStatus:
    """write_baseline_unstable_status writes baseline.yaml with correct fields."""

    def test_creates_baseline_yaml(self, tmp_path):
        run_dir = tmp_path / "runs" / "round1"
        write_baseline_unstable_status(run_dir, failing_test_file="tests/test_bad.py")
        assert (run_dir / "baseline.yaml").exists()

    def test_status_field_is_baseline_unstable(self, tmp_path):
        run_dir = tmp_path / "runs" / "round1"
        write_baseline_unstable_status(run_dir, failing_test_file="tests/test_bad.py")
        data = yaml.safe_load((run_dir / "baseline.yaml").read_text())
        assert data["status"] == "baseline_unstable"

    def test_failing_test_file_field_present(self, tmp_path):
        run_dir = tmp_path / "runs" / "round1"
        write_baseline_unstable_status(run_dir, failing_test_file="tests/test_bad.py")
        data = yaml.safe_load((run_dir / "baseline.yaml").read_text())
        assert "failing_test_file" in data

    def test_failing_test_file_names_the_file(self, tmp_path):
        run_dir = tmp_path / "runs" / "round2"
        write_baseline_unstable_status(
            run_dir,
            failing_test_file="tests/test_property_based_test_generator_hypothesis_ears.py",
        )
        data = yaml.safe_load((run_dir / "baseline.yaml").read_text())
        assert data["failing_test_file"] == (
            "tests/test_property_based_test_generator_hypothesis_ears.py"
        )

    def test_failing_test_file_none_when_not_provided(self, tmp_path):
        run_dir = tmp_path / "runs" / "round3"
        write_baseline_unstable_status(run_dir)
        data = yaml.safe_load((run_dir / "baseline.yaml").read_text())
        assert data["failing_test_file"] is None

    def test_creates_parent_dirs(self, tmp_path):
        run_dir = tmp_path / "deeply" / "nested" / "runs" / "r1"
        write_baseline_unstable_status(run_dir, failing_test_file="tests/test_x.py")
        assert (run_dir / "baseline.yaml").exists()

    def test_second_failing_file_name_preserved(self, tmp_path):
        run_dir = tmp_path / "runs" / "round4"
        write_baseline_unstable_status(
            run_dir,
            failing_test_file="tests/test_spec_linter_pre_spawn_quality_gate.py",
        )
        data = yaml.safe_load((run_dir / "baseline.yaml").read_text())
        assert data["failing_test_file"] == (
            "tests/test_spec_linter_pre_spawn_quality_gate.py"
        )

    def test_yaml_is_valid(self, tmp_path):
        run_dir = tmp_path / "runs" / "r5"
        write_baseline_unstable_status(run_dir, failing_test_file="tests/test_foo.py")
        content = (run_dir / "baseline.yaml").read_text()
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict)
