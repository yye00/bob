"""Tests for zero-AC boundary: compute_spec_coverage_pct returns 0.0 on empty list."""

from __future__ import annotations

import pathlib

import pytest


def test_compute_spec_coverage_pct_returns_zero_for_empty_acs(tmp_path):
    """Zero-AC feature: compute_spec_coverage_pct must return 0.0 (not divide by zero)."""
    from tools.spec_coverage import compute_spec_coverage_pct

    result = compute_spec_coverage_pct([], test_files=[], workspace=tmp_path)

    assert result == 0.0


def test_handle_zero_acs_returns_zero_float(tmp_path):
    from tools.spec_coverage import handle_zero_acs

    result = handle_zero_acs([])

    assert result == 0.0
    assert isinstance(result, float)


def test_never_divides_by_zero_on_empty_acs_returns_true():
    from tools.spec_coverage import never_divides_by_zero_on_empty_acs

    assert never_divides_by_zero_on_empty_acs() is True


def test_compute_spec_coverage_pct_no_division_error_on_zero_acs(tmp_path):
    """Calling compute_spec_coverage_pct([]) must not raise ZeroDivisionError."""
    from tools.spec_coverage import compute_spec_coverage_pct

    try:
        result = compute_spec_coverage_pct([], test_files=[], workspace=tmp_path)
    except ZeroDivisionError:
        pytest.fail("compute_spec_coverage_pct raised ZeroDivisionError on empty AC list")

    assert result == 0.0


def test_compute_spec_coverage_pct_nonzero_acs(tmp_path):
    """Normal case: 1 covered of 2 = 0.5."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_example.py"
    test_file.write_text("# AC-01\ndef test_x(): assert True\n")

    acs = [
        {"id": "AC-01", "text": "covered ac"},
        {"id": "AC-02", "text": "orphaned ac without match"},
    ]

    from tools.spec_coverage import compute_spec_coverage_pct

    result = compute_spec_coverage_pct(acs, test_files=[test_file], workspace=tmp_path)

    assert abs(result - 0.5) < 0.01


def test_artifact_path_field_returns_correct_name():
    from tools.spec_coverage import artifact_path_field

    field = artifact_path_field()

    assert field == "rtm_artifact_path"
