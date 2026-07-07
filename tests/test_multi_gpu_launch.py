"""Tests for bob.multi_gpu_launch.

Feature f1f607ff-cabf-41e9-8f5a-79eed056330a — Multi-GPU launch with topology
and rank-count enforcement.
"""

from __future__ import annotations

import pytest

from bob.multi_gpu_launch import (
    MpirunCommand,
    RankVerification,
    Topology,
    build_mpirun_command,
    discover_topology,
    verify_rank_count,
)


# ---------------------------------------------------------------------------
# discover_topology
# ---------------------------------------------------------------------------

_ROCMINFO_8 = "\n".join(
    ["*** Agent ***\n  Device Type:  CPU"]
    + ["*** Agent ***\n  Device Type:  GPU"] * 8
)


def test_discover_topology_rocminfo_counts_gpus():
    topo = discover_topology(runner=lambda cmd: _ROCMINFO_8 if cmd[0] == "rocminfo" else "")
    assert isinstance(topo, Topology)
    assert topo.device_count == 8
    assert topo.source == "rocminfo"
    assert topo.device_ids == tuple(range(8))
    assert topo.available is True


def test_discover_topology_falls_back_to_rocm_smi():
    smi = "GPU0 GPU1 GPU2 GPU3"

    def runner(cmd):
        if cmd[0] == "rocm-smi":
            return smi
        return ""

    topo = discover_topology(runner=runner)
    assert topo.device_count == 4
    assert topo.source == "rocm-smi"


def test_discover_topology_no_devices_returns_zero():
    topo = discover_topology(runner=lambda cmd: "")
    assert topo.device_count == 0
    assert topo.available is False
    assert topo.source == "none"


# ---------------------------------------------------------------------------
# build_mpirun_command
# ---------------------------------------------------------------------------

def test_build_mpirun_command_shape():
    cmd = build_mpirun_command(
        "./build/all_reduce_perf",
        8,
        binary_args=["-b", "8", "-e", "1G", "-f", "2", "-g", "1"],
        launcher="mpirun",
    )
    assert isinstance(cmd, MpirunCommand)
    assert cmd.np == 8
    assert cmd.argv[0] == "mpirun"
    assert "-np" in cmd.argv
    assert cmd.argv[cmd.argv.index("-np") + 1] == "8"
    assert "--bind-to" in cmd.argv
    assert "./build/all_reduce_perf" in cmd.argv
    assert cmd.argv[-1] == "1"


def test_build_mpirun_command_sets_env():
    cmd = build_mpirun_command("./bin", 8, launcher="mpirun")
    assert cmd.env["ROCR_VISIBLE_DEVICES"] == "0,1,2,3,4,5,6,7"
    assert cmd.env["HSA_NO_SCRATCH_RECLAIM"] == "1"
    assert cmd.env["NCCL_DEBUG"] == "VERSION"


def test_build_mpirun_command_extra_env_overrides():
    cmd = build_mpirun_command(
        "./bin", 2, launcher="mpirun", extra_env={"NCCL_DEBUG": "INFO"}
    )
    assert cmd.env["NCCL_DEBUG"] == "INFO"
    assert cmd.env["ROCR_VISIBLE_DEVICES"] == "0,1"


# ---------------------------------------------------------------------------
# verify_rank_count — the anti-cheat gate
# ---------------------------------------------------------------------------

def test_verify_rank_count_nranks_line_matches():
    out = "rccl init: nRanks 8 on hostA"
    v = verify_rank_count(out, 8)
    assert isinstance(v, RankVerification)
    assert v.ok is True
    assert v.observed == 8


def test_verify_rank_count_rank_init_lines():
    out = "\n".join(f"NCCL INFO Rank {i} bootstrap done" for i in range(8))
    v = verify_rank_count(out, 8)
    assert v.ok is True
    assert v.observed == 8
    assert v.ranks_seen == tuple(range(8))


def test_verify_rank_count_gate_catches_single_gpu_claiming_eight():
    # Only 1 rank actually launched but feature claims 8 — must NOT pass.
    out = "NCCL INFO Rank 0 bootstrap done"
    v = verify_rank_count(out, 8)
    assert v.ok is False
    assert v.observed == 1


def test_verify_rank_count_using_devices_header_with_ranks():
    out = "# Using devices\n# Rank 0 dev 0\n# Rank 1 dev 1"
    v = verify_rank_count(out, 2)
    assert v.ok is True
    assert v.observed == 2


def test_verify_rank_count_no_launch_evidence():
    v = verify_rank_count("nothing here", 8)
    assert v.ok is False
    assert v.observed == 0
