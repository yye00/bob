"""Boundary tests for bob.rccl_selection_proof (feature a2b5524f).

Empty, zero, or minimum input must return a well-defined result rather than raising.
"""
from __future__ import annotations

from bob.rccl_selection_proof import (
    FrozenEnv,
    RocprofVerdict,
    SelectionReport,
    freeze_rccl_env,
    parse_selection_log,
    verify_rocprof_kernel_trace,
)


def test_parse_empty_log_returns_report():
    rep = parse_selection_log("")
    assert isinstance(rep, SelectionReport)
    assert rep.records == []
    assert rep.tuner_loaded is False
    assert rep.selection_confirmed is False


def test_parse_whitespace_only_log():
    rep = parse_selection_log("   \n  \n")
    assert isinstance(rep, SelectionReport)
    assert rep.records == []


def test_parse_empty_target_sizes():
    rep = parse_selection_log("", target_sizes=[])
    assert isinstance(rep, SelectionReport)
    assert rep.target_sizes == ()


def test_parse_zero_target_size():
    log = "NCCL INFO comm nBytes=0 algo=Ring proto=Simple"
    rep = parse_selection_log(
        log, expected_algo="Ring", expected_proto="Simple", target_sizes=[0]
    )
    assert rep.selection_confirmed is True
    assert rep.matched_sizes == (0,)


def test_freeze_empty_env_returns_empty_frozen():
    fe = freeze_rccl_env({})
    assert isinstance(fe, FrozenEnv)
    assert fe.frozen == {}
    assert fe.signature == ""


def test_freeze_env_with_no_rccl_keys():
    fe = freeze_rccl_env({"PATH": "/bin", "HOME": "/root"})
    assert fe.frozen == {}
    assert fe.signature == ""


def test_rocprof_empty_gate_on_trace_returns_fail_verdict():
    v = verify_rocprof_kernel_trace([], [], benchmarked_bytes=0)
    assert isinstance(v, RocprofVerdict)
    assert v.passed is False
    assert "empty" in v.reason


def test_rocprof_zero_benchmarked_bytes():
    on = [{"name": "k", "bytes": 0}]
    v = verify_rocprof_kernel_trace(on, [], benchmarked_bytes=0)
    assert isinstance(v, RocprofVerdict)
    assert v.passed is True


def test_rocprof_none_gate_off_trace_defaults_to_baseline():
    on = [{"name": "k", "bytes": 8}]
    v = verify_rocprof_kernel_trace(on, None, benchmarked_bytes=8)
    assert isinstance(v, RocprofVerdict)
    assert v.passed is True
