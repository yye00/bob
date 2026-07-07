"""Error-path tests for bob.rccl_selection_proof (feature a2b5524f).

Invalid input raises ValueError and the function does not silently succeed.
"""
from __future__ import annotations

import pytest

from bob.rccl_selection_proof import (
    freeze_rccl_env,
    parse_selection_log,
    verify_rocprof_kernel_trace,
)


# ------------------------------------------------------------------ parse_selection_log


def test_parse_non_str_log_raises():
    with pytest.raises(ValueError):
        parse_selection_log(12345)  # type: ignore[arg-type]


def test_parse_unrecognised_algo_raises():
    with pytest.raises(ValueError):
        parse_selection_log("", expected_algo="Bogus")


def test_parse_unrecognised_proto_raises():
    with pytest.raises(ValueError):
        parse_selection_log("", expected_proto="Bogus")


def test_parse_empty_expected_algo_raises():
    with pytest.raises(ValueError):
        parse_selection_log("", expected_algo="   ")


def test_parse_negative_target_size_raises():
    with pytest.raises(ValueError):
        parse_selection_log("", target_sizes=[-1])


def test_parse_bool_target_size_raises():
    with pytest.raises(ValueError):
        parse_selection_log("", target_sizes=[True])


# -------------------------------------------------------------------- freeze_rccl_env


def test_freeze_non_mapping_env_raises():
    with pytest.raises(ValueError):
        freeze_rccl_env(["NCCL_ALGO=Ring"])  # type: ignore[arg-type]


def test_freeze_non_str_value_raises():
    with pytest.raises(ValueError):
        freeze_rccl_env({"NCCL_ALGO": 5})  # type: ignore[dict-item]


def test_freeze_empty_gate_knob_raises():
    with pytest.raises(ValueError):
        freeze_rccl_env({"NCCL_ALGO": "Ring"}, gate_knob="  ")


# --------------------------------------------------------- verify_rocprof_kernel_trace


def test_rocprof_negative_benchmarked_bytes_raises():
    with pytest.raises(ValueError):
        verify_rocprof_kernel_trace([{"name": "k", "bytes": 8}], [], benchmarked_bytes=-1)


def test_rocprof_non_int_benchmarked_bytes_raises():
    with pytest.raises(ValueError):
        verify_rocprof_kernel_trace(
            [{"name": "k", "bytes": 8}], [], benchmarked_bytes="8"  # type: ignore[arg-type]
        )


def test_rocprof_record_missing_name_raises():
    with pytest.raises(ValueError):
        verify_rocprof_kernel_trace([{"bytes": 8}], [], benchmarked_bytes=8)


def test_rocprof_record_empty_name_raises():
    with pytest.raises(ValueError):
        verify_rocprof_kernel_trace([{"name": "", "bytes": 8}], [], benchmarked_bytes=8)


def test_rocprof_record_negative_bytes_raises():
    with pytest.raises(ValueError):
        verify_rocprof_kernel_trace(
            [{"name": "k", "bytes": -8}], [], benchmarked_bytes=8
        )


def test_rocprof_record_not_mapping_raises():
    with pytest.raises(ValueError):
        verify_rocprof_kernel_trace(["not-a-dict"], [], benchmarked_bytes=8)
