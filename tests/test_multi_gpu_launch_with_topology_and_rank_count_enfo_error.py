"""Error-path tests for bob.multi_gpu_launch.

AC: pytest: tests/test_multi_gpu_launch_with_topology_and_rank_count_enfo_error.py
    — invalid input raises ValueError and the function does not silently
    succeed (error path).

Feature f1f607ff-cabf-41e9-8f5a-79eed056330a
"""

from __future__ import annotations

import pytest

from bob.multi_gpu_launch import build_mpirun_command, verify_rank_count


# ---------------------------------------------------------------------------
# build_mpirun_command
# ---------------------------------------------------------------------------

def test_build_empty_binary_raises():
    with pytest.raises(ValueError):
        build_mpirun_command("", 8)


def test_build_whitespace_binary_raises():
    with pytest.raises(ValueError):
        build_mpirun_command("   ", 8)


def test_build_non_string_binary_raises():
    with pytest.raises(ValueError):
        build_mpirun_command(None, 8)


def test_build_zero_ngpu_raises():
    with pytest.raises(ValueError):
        build_mpirun_command("./bin", 0)


def test_build_negative_ngpu_raises():
    with pytest.raises(ValueError):
        build_mpirun_command("./bin", -4)


def test_build_non_int_ngpu_raises():
    with pytest.raises(ValueError):
        build_mpirun_command("./bin", 8.0)


def test_build_bool_ngpu_raises():
    with pytest.raises(ValueError):
        build_mpirun_command("./bin", True)


# ---------------------------------------------------------------------------
# verify_rank_count
# ---------------------------------------------------------------------------

def test_verify_non_string_output_raises():
    with pytest.raises(ValueError):
        verify_rank_count(None, 8)


def test_verify_zero_expected_raises():
    with pytest.raises(ValueError):
        verify_rank_count("Rank 0", 0)


def test_verify_negative_expected_raises():
    with pytest.raises(ValueError):
        verify_rank_count("Rank 0", -1)


def test_verify_non_int_expected_raises():
    with pytest.raises(ValueError):
        verify_rank_count("Rank 0", 8.0)


def test_verify_bool_expected_raises():
    with pytest.raises(ValueError):
        verify_rank_count("Rank 0", True)
