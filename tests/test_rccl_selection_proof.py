"""Tests for bob.rccl_selection_proof (feature a2b5524f).

RCCL selection-log + rocprof execution proof: selection != execution.
"""
from __future__ import annotations

import pytest

from bob.rccl_selection_proof import (
    LL128_CAVEAT,
    RCCL_ENV_PREFIXES,
    FrozenEnv,
    RocprofVerdict,
    SelectionRecord,
    SelectionReport,
    freeze_rccl_env,
    parse_selection_log,
    verify_rocprof_kernel_trace,
)


# ---------------------------------------------------------------- parse_selection_log

_LOG = """
[0] NCCL INFO Bootstrap : Using eth0
[0] NCCL INFO TUNER: Initializing tuner plugin from libnccl-tuner.so
[0] NCCL INFO comm 0x1 nBytes=1048576 algo=Ring proto=Simple
[0] NCCL INFO comm 0x1 nBytes=4194304 algo=Tree proto=LL128
"""


def test_parses_tuner_loaded_and_records():
    rep = parse_selection_log(_LOG)
    assert rep.tuner_loaded is True
    assert len(rep.records) == 2
    assert rep.records[0].algo == "Ring"
    assert rep.records[0].proto == "Simple"
    assert rep.records[0].size == 1048576


def test_selection_confirmed_when_expected_matches_at_target_size():
    rep = parse_selection_log(
        _LOG, expected_algo="Ring", expected_proto="Simple", target_sizes=[1048576]
    )
    assert rep.selection_confirmed is True
    assert rep.matched_sizes == (1048576,)
    assert rep.missing_sizes == ()


def test_selection_not_confirmed_when_size_missing():
    rep = parse_selection_log(
        _LOG, expected_algo="Ring", expected_proto="Simple", target_sizes=[999999]
    )
    assert rep.selection_confirmed is False
    assert 999999 in rep.missing_sizes


def test_ll128_caveat_emitted():
    rep = parse_selection_log(_LOG)
    assert any("LL128" in w for w in rep.warnings)
    assert LL128_CAVEAT in rep.warnings


def test_no_tuner_marker_means_not_loaded():
    rep = parse_selection_log("[0] NCCL INFO comm nBytes=8 algo=Ring proto=Simple")
    assert rep.tuner_loaded is False


def test_alt_selection_line_without_size():
    rep = parse_selection_log("NCCL INFO Selected algorithm Tree protocol LL")
    assert len(rep.records) == 1
    assert rep.records[0].algo == "Tree"
    assert rep.records[0].proto == "LL"
    assert rep.records[0].size is None


def test_report_as_dict_shape():
    d = parse_selection_log(_LOG).as_dict()
    assert set(
        ["tuner_loaded", "selection_confirmed", "records", "warnings"]
    ).issubset(d)


def test_selection_record_matches():
    r = SelectionRecord(algo="Ring", proto="Simple", size=8)
    assert r.matches("ring", "simple")
    assert not r.matches("Tree", None)


# ------------------------------------------------------------------- freeze_rccl_env


def test_freeze_extracts_only_rccl_nccl():
    env = {"NCCL_ALGO": "Ring", "RCCL_MSCCL_ENABLE": "1", "PATH": "/bin", "HOME": "/root"}
    fe = freeze_rccl_env(env)
    assert isinstance(fe, FrozenEnv)
    assert set(fe.frozen) == {"NCCL_ALGO", "RCCL_MSCCL_ENABLE"}
    assert "PATH" not in fe.frozen


def test_freeze_signature_is_order_independent():
    a = freeze_rccl_env({"NCCL_ALGO": "Ring", "NCCL_PROTO": "Simple"})
    b = freeze_rccl_env({"NCCL_PROTO": "Simple", "NCCL_ALGO": "Ring"})
    assert a.signature == b.signature


def test_freeze_excludes_gate_knob():
    env = {"NCCL_ALGO": "Ring", "NCCL_PROTO": "Simple"}
    fe = freeze_rccl_env(env, gate_knob="NCCL_PROTO")
    assert "NCCL_PROTO" not in fe.frozen
    assert "NCCL_ALGO" in fe.frozen


def test_old_new_frozen_signatures_match_except_gate_knob():
    old = {"NCCL_ALGO": "Ring", "NCCL_PROTO": "Simple"}
    new = {"NCCL_ALGO": "Ring", "NCCL_PROTO": "LL128"}
    assert freeze_rccl_env(old, gate_knob="NCCL_PROTO").signature == freeze_rccl_env(
        new, gate_knob="NCCL_PROTO"
    ).signature


def test_rccl_env_prefixes_constant():
    assert "NCCL_" in RCCL_ENV_PREFIXES
    assert "RCCL_" in RCCL_ENV_PREFIXES


# --------------------------------------------------------- verify_rocprof_kernel_trace


def test_distinct_kernel_with_gate_on_passes():
    on = [{"name": "new_allreduce_ll128", "bytes": 4194304}]
    off = [{"name": "old_allreduce_simple", "bytes": 4194304}]
    v = verify_rocprof_kernel_trace(on, off, benchmarked_bytes=4194304)
    assert isinstance(v, RocprofVerdict)
    assert v.passed is True
    assert v.distinct_kernel == "new_allreduce_ll128"
    assert v.bytes_serviced == 4194304


def test_win_present_with_gate_off_fails():
    on = [{"name": "same_kernel", "bytes": 4194304}]
    off = [{"name": "same_kernel", "bytes": 4194304}]
    v = verify_rocprof_kernel_trace(on, off, benchmarked_bytes=4194304)
    assert v.passed is False
    assert "not caused by this feature" in v.reason


def test_distinct_kernel_but_insufficient_bytes_fails():
    on = [{"name": "new_kernel", "bytes": 1024}]
    v = verify_rocprof_kernel_trace(on, [], benchmarked_bytes=4194304)
    assert v.passed is False
    assert "below the benchmarked" in v.reason


def test_baseline_kernels_argument_marks_preexisting():
    on = [{"name": "prebuilt", "bytes": 4096}]
    v = verify_rocprof_kernel_trace(
        on, benchmarked_bytes=4096, baseline_kernels=["prebuilt"]
    )
    assert v.passed is False


def test_verdict_as_dict_shape():
    on = [{"name": "k", "bytes": 8}]
    d = verify_rocprof_kernel_trace(on, [], benchmarked_bytes=8).as_dict()
    assert "passed" in d and "distinct_kernel" in d and "bytes_serviced" in d
