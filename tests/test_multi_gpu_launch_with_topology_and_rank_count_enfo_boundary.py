"""Boundary tests for bob.multi_gpu_launch.

AC: pytest: tests/test_multi_gpu_launch_with_topology_and_rank_count_enfo_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than
    raising (boundary case).

Feature f1f607ff-cabf-41e9-8f5a-79eed056330a
"""

from __future__ import annotations

from bob.multi_gpu_launch import (
    Topology,
    build_mpirun_command,
    discover_topology,
    verify_rank_count,
)


# ---------------------------------------------------------------------------
# discover_topology: no devices / empty probe output → device_count 0, no raise
# ---------------------------------------------------------------------------

def test_discover_topology_empty_output_is_well_defined():
    topo = discover_topology(runner=lambda cmd: "")
    assert isinstance(topo, Topology)
    assert topo.device_count == 0
    assert topo.device_ids == ()
    assert topo.available is False


# ---------------------------------------------------------------------------
# build_mpirun_command: minimum ngpu == 1 is valid, returns a defined command
# ---------------------------------------------------------------------------

def test_build_mpirun_command_min_single_gpu():
    cmd = build_mpirun_command("./bin", 1, launcher="mpirun")
    assert cmd.np == 1
    assert cmd.env["ROCR_VISIBLE_DEVICES"] == "0"
    assert cmd.argv[cmd.argv.index("-np") + 1] == "1"


def test_build_mpirun_command_no_binary_args_is_defined():
    cmd = build_mpirun_command("./bin", 2, launcher="mpirun")
    assert cmd.argv[-1] == "./bin"


# ---------------------------------------------------------------------------
# verify_rank_count: empty output → ok False, observed 0 (defined, no raise)
# ---------------------------------------------------------------------------

def test_verify_rank_count_empty_output_defined():
    v = verify_rank_count("", 8)
    assert v.ok is False
    assert v.observed == 0
    assert v.ranks_seen == ()


def test_verify_rank_count_minimum_single_rank():
    v = verify_rank_count("NCCL INFO Rank 0 up", 1)
    assert v.ok is True
    assert v.observed == 1
