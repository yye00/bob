"""Multi-GPU launch with topology discovery and rank-count enforcement.

RCCL correctness/perf tests are inherently multi-process/multi-GPU (one MPI
rank per GPU). This module is the collective-launch analog of the single-GPU
dispatch anti-cheat: it (1) discovers device count/topology, (2) builds an
``mpirun -np <ngpu>`` command wired with the env RCCL needs, and (3) GATES on
the launch actually using the expected number of ranks/devices so a feature
cannot quietly run on 1 GPU and claim 8.

Public functions:

- :func:`discover_topology`: probe ``rocminfo`` / ``rocm-smi --showtopo`` /
  ``hipGetDeviceCount`` for the device count and topology. Returns a
  :class:`Topology` even when no GPU/tool is present (device_count == 0).
- :func:`build_mpirun_command`: build the ``mpirun -np <ngpu>`` argv and the
  environment overlay (``ROCR_VISIBLE_DEVICES``, ``HSA_NO_SCRATCH_RECLAIM``,
  ``NCCL_DEBUG``).
- :func:`verify_rank_count`: parse ``NCCL_DEBUG`` rank-init lines or the
  rccl-tests ``# Using devices`` header from a launch's stdout/stderr and
  confirm the observed rank/device count matches the expected count.

Integration: bob.orchestrator — when a feature's AC mentions a multi-GPU /
RCCL collective launch, the orchestrator sizes the launch via
:func:`discover_topology`, builds the command with :func:`build_mpirun_command`,
runs it, and gates the result with :func:`verify_rank_count`.

The module is fully testable without hardware: topology probing accepts an
injectable command runner, and rank verification operates on captured text.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

__all__ = [
    "Topology",
    "MpirunCommand",
    "RankVerification",
    "discover_topology",
    "build_mpirun_command",
    "verify_rank_count",
]


# Default env every RCCL collective launch needs.
_DEFAULT_ENV: dict[str, str] = {
    "HSA_NO_SCRATCH_RECLAIM": "1",
    "NCCL_DEBUG": "VERSION",
}

# ``rccl-tests`` prints e.g. ``# Using devices`` followed by ``# Rank 0 ...``
# lines, and NCCL prints ``... NCCL INFO Rank 3 ...`` / ``nRanks 8`` lines.
_RANK_LINE_RE = re.compile(r"\bRank\s+(\d+)\b")
_NRANKS_RE = re.compile(r"\bnRanks\s+(\d+)\b")
_USING_DEVICES_RE = re.compile(r"#\s*Using\s+devices", re.IGNORECASE)


@dataclass(frozen=True)
class Topology:
    """Discovered GPU topology."""

    device_count: int
    device_ids: tuple[int, ...] = ()
    source: str = "none"

    @property
    def available(self) -> bool:
        return self.device_count > 0


@dataclass(frozen=True)
class MpirunCommand:
    """A built multi-GPU launch command."""

    argv: tuple[str, ...]
    env: Mapping[str, str]
    np: int

    @property
    def command(self) -> str:
        return " ".join(self.argv)


@dataclass(frozen=True)
class RankVerification:
    """Outcome of :func:`verify_rank_count`."""

    expected: int
    observed: int
    ok: bool
    ranks_seen: tuple[int, ...] = field(default_factory=tuple)
    detail: str = ""


def _default_runner(cmd: Sequence[str]) -> str:
    """Run ``cmd`` and return combined stdout; empty string on any failure."""
    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout or ""


def discover_topology(
    *,
    runner: Callable[[Sequence[str]], str] | None = None,
) -> Topology:
    """Discover GPU device count and topology.

    Probes, in order, ``rocminfo`` (counts ``Device Type: GPU`` agents),
    ``rocm-smi --showtopo`` (counts ``GPU<n>`` columns), then falls back to a
    ``hipGetDeviceCount`` probe. Returns a :class:`Topology` with
    ``device_count == 0`` when nothing is available — a well-defined result,
    never a raise.

    ``runner`` is an injectable callable taking an argv sequence and returning
    the command's stdout; defaults to a subprocess runner. It is used to make
    the function testable without hardware.
    """
    run = runner or _default_runner

    if runner is not None or shutil.which("rocminfo"):
        out = run(["rocminfo"])
        gpu_count = _count_rocminfo_gpus(out)
        if gpu_count > 0:
            return Topology(
                device_count=gpu_count,
                device_ids=tuple(range(gpu_count)),
                source="rocminfo",
            )

    if runner is not None or shutil.which("rocm-smi"):
        out = run(["rocm-smi", "--showtopo"])
        gpu_count = _count_rocm_smi_gpus(out)
        if gpu_count > 0:
            return Topology(
                device_count=gpu_count,
                device_ids=tuple(range(gpu_count)),
                source="rocm-smi",
            )

    hip_count = _hip_device_count()
    if hip_count > 0:
        return Topology(
            device_count=hip_count,
            device_ids=tuple(range(hip_count)),
            source="hipGetDeviceCount",
        )

    return Topology(device_count=0, device_ids=(), source="none")


def _count_rocminfo_gpus(text: str) -> int:
    """Count GPU agents in ``rocminfo`` output.

    ``rocminfo`` lists one ``Agent`` block per device with a ``Device Type:``
    field; GPUs report ``Device Type:  GPU`` (CPUs report ``CPU``).
    """
    if not text:
        return 0
    return len(re.findall(r"Device\s+Type:\s*GPU", text))


def _count_rocm_smi_gpus(text: str) -> int:
    """Count distinct ``GPU<n>`` labels in ``rocm-smi --showtopo`` output."""
    if not text:
        return 0
    ids = set(re.findall(r"\bGPU(\d+)\b", text))
    return len(ids)


def _hip_device_count() -> int:
    """Best-effort ``hipGetDeviceCount`` via env or a torch/HIP probe."""
    env_val = os.environ.get("HIP_VISIBLE_DEVICES") or os.environ.get(
        "ROCR_VISIBLE_DEVICES"
    )
    if env_val:
        ids = [tok for tok in env_val.split(",") if tok.strip() != ""]
        if ids:
            return len(ids)
    try:  # pragma: no cover - hardware dependent
        import torch  # type: ignore

        if torch.cuda.is_available():
            return int(torch.cuda.device_count())
    except Exception:  # pragma: no cover - torch optional/absent
        pass
    return 0


def _detect_mpirun() -> str | None:
    """Return the mpirun launcher name if present in PATH, else None."""
    for name in ("mpirun", "mpirun.mpich"):
        if shutil.which(name):
            return name
    return None


def build_mpirun_command(
    binary: str,
    ngpu: int,
    *,
    binary_args: Sequence[str] | None = None,
    launcher: str | None = None,
    bind_to: str = "numa",
    extra_env: Mapping[str, str] | None = None,
) -> MpirunCommand:
    """Build an ``mpirun -np <ngpu>`` command for a multi-rank binary.

    Produces argv like::

        mpirun -np 8 --bind-to numa ./build/all_reduce_perf -b 8 -e 1G -f 2 -g 1

    and an env overlay setting ``ROCR_VISIBLE_DEVICES=0,1,...,ngpu-1`` plus the
    RCCL defaults (``HSA_NO_SCRATCH_RECLAIM=1``, ``NCCL_DEBUG=VERSION``).

    ``launcher`` overrides the launcher name; when omitted it is auto-detected
    from PATH (``mpirun`` / ``mpirun.mpich``), defaulting to ``mpirun``.

    Raises :class:`ValueError` for a non-str/empty ``binary`` or a
    non-positive / non-int ``ngpu`` — the launch is never silently sized to 0.
    """
    if not isinstance(binary, str) or not binary.strip():
        raise ValueError("binary must be a non-empty string")
    if isinstance(ngpu, bool) or not isinstance(ngpu, int):
        raise ValueError("ngpu must be an integer")
    if ngpu < 1:
        raise ValueError("ngpu must be >= 1")

    resolved_launcher = launcher or _detect_mpirun() or "mpirun"

    argv: list[str] = [resolved_launcher, "-np", str(ngpu)]
    if bind_to:
        argv += ["--bind-to", bind_to]
    argv.append(binary)
    if binary_args:
        argv += [str(a) for a in binary_args]

    env: dict[str, str] = dict(_DEFAULT_ENV)
    env["ROCR_VISIBLE_DEVICES"] = ",".join(str(i) for i in range(ngpu))
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items()})

    return MpirunCommand(argv=tuple(argv), env=env, np=ngpu)


def verify_rank_count(output: str, expected: int) -> RankVerification:
    """Verify a launch actually used ``expected`` ranks/devices.

    Parses ``output`` (combined stdout/stderr of the launch) for:

    - an explicit ``nRanks <n>`` line emitted by NCCL/RCCL init, and/or
    - distinct ``Rank <n>`` init lines, and/or
    - the rccl-tests ``# Using devices`` header followed by per-device lines.

    Returns a :class:`RankVerification` whose ``ok`` is True only when the
    observed count equals ``expected``. This is the gate: a run that only spun
    up 1 rank cannot claim 8.

    Raises :class:`ValueError` for a non-str ``output`` or a non-positive /
    non-int ``expected``.
    """
    if not isinstance(output, str):
        raise ValueError("output must be a string")
    if isinstance(expected, bool) or not isinstance(expected, int):
        raise ValueError("expected must be an integer")
    if expected < 1:
        raise ValueError("expected must be >= 1")

    ranks_seen = sorted({int(m) for m in _RANK_LINE_RE.findall(output)})

    nranks_matches = [int(m) for m in _NRANKS_RE.findall(output)]
    nranks = max(nranks_matches) if nranks_matches else 0

    # Prefer an explicit nRanks declaration; else use the count of distinct
    # rank-init lines observed.
    observed = nranks if nranks > 0 else len(ranks_seen)

    ok = observed == expected

    if observed == 0:
        detail = "no rank-init or nRanks lines found in output"
    elif ok:
        detail = f"observed {observed} ranks == expected {expected}"
    else:
        detail = f"observed {observed} ranks != expected {expected}"

    return RankVerification(
        expected=expected,
        observed=observed,
        ok=ok,
        ranks_seen=tuple(ranks_seen),
        detail=detail,
    )
