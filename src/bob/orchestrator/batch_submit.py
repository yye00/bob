"""SLURM / PBS batch-job submission adapter for Bob.

When a feature is tagged ``compute=batch``, this module packages its
command as a SLURM (sbatch) or PBS (qsub) job, submits it, polls for
completion, and ingests stdout/stderr/result files when done.

Falls back to local subprocess execution when neither SLURM nor PBS is
available, so existing features remain unaffected.
"""
from __future__ import annotations

import enum
import logging
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus(enum.Enum):
    """Lifecycle states for a batch-submitted job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class BatchJobError(RuntimeError):
    """Raised when a batch submission or polling step fails unrecoverably."""


@dataclass
class BatchSubmitResult:
    """Returned by :func:`submit_slurm` and :func:`submit_pbs`."""

    job_id: str
    scheduler: str  # "slurm", "pbs", or "local"
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchJob:
    """Mutable record for a submitted batch job; updated by :func:`poll_until_done`."""

    job_id: str
    scheduler: str
    workspace: str
    stdout_path: str
    stderr_path: str
    stdout: str | None = None
    stderr: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _write_slurm_script(
    workspace: Path,
    command: list[str],
    job_name: str,
    stdout_path: str,
    stderr_path: str,
    extra_args: list[str],
) -> Path:
    """Write a minimal SLURM batch script and return its path."""
    script_path = workspace / f"{job_name}_{uuid.uuid4().hex[:8]}.sh"
    extra_directives = "\n".join(f"#SBATCH {a}" for a in extra_args)
    cmd_str = " ".join(command)
    script_text = (
        "#!/bin/bash\n"
        f"#SBATCH --job-name={job_name}\n"
        f"#SBATCH --output={stdout_path}\n"
        f"#SBATCH --error={stderr_path}\n"
        f"{extra_directives}\n"
        f"{cmd_str}\n"
    )
    script_path.write_text(script_text, encoding="utf-8")
    return script_path


def _write_pbs_script(
    workspace: Path,
    command: list[str],
    job_name: str,
    stdout_path: str,
    stderr_path: str,
    extra_args: list[str],
) -> Path:
    """Write a minimal PBS batch script and return its path."""
    script_path = workspace / f"{job_name}_{uuid.uuid4().hex[:8]}.sh"
    cmd_str = " ".join(command)
    # Build qsub resource list from extra_args pairs: ["-l", "select=1", ...]
    extra_directives = ""
    if extra_args:
        # Join pairs like ["-l", "val"] as PBS directives
        i = 0
        pairs = []
        while i < len(extra_args):
            if extra_args[i].startswith("-") and i + 1 < len(extra_args):
                pairs.append(f"#PBS {extra_args[i]} {extra_args[i + 1]}")
                i += 2
            else:
                pairs.append(f"#PBS {extra_args[i]}")
                i += 1
        extra_directives = "\n".join(pairs)
    script_text = (
        "#!/bin/bash\n"
        f"#PBS -N {job_name}\n"
        f"#PBS -o {stdout_path}\n"
        f"#PBS -e {stderr_path}\n"
        f"{extra_directives}\n"
        f"cd $PBS_O_WORKDIR 2>/dev/null || true\n"
        f"{cmd_str}\n"
    )
    script_path.write_text(script_text, encoding="utf-8")
    return script_path


def _run_local(
    command: list[str],
    workspace: str,
    job_name: str,
) -> BatchSubmitResult:
    """Execute ``command`` locally as a subprocess fallback.

    Returns a BatchSubmitResult with ``scheduler='local'`` and a synthetic
    job_id so callers can treat it uniformly with real batch submissions.
    """
    job_id = f"local-{uuid.uuid4().hex[:8]}"
    ws = Path(workspace)
    stdout_path = ws / f"{job_name}_{job_id}.stdout"
    stderr_path = ws / f"{job_name}_{job_id}.stderr"
    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        if proc.returncode != 0:
            logger.warning(
                "Local fallback job %s exited %d: %s",
                job_id,
                proc.returncode,
                (proc.stderr or "")[:200],
            )
    except Exception as exc:
        logger.warning("Local fallback job %s failed: %s", job_id, exc)

    return BatchSubmitResult(job_id=job_id, scheduler="local")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def submit_slurm(
    command: list[str],
    workspace: str,
    job_name: str,
    *,
    extra_args: list[str] | None = None,
) -> BatchSubmitResult:
    """Package ``command`` as a SLURM job and submit it via ``sbatch``.

    Args:
        command: The command (argv list) to run inside the job.
        workspace: Path to the working directory used for script/output files.
        job_name: Human-readable job name passed to ``--job-name``.
        extra_args: Additional ``sbatch`` CLI arguments (e.g.
            ``["--partition=gpu", "--time=01:00:00"]``).

    Returns:
        :class:`BatchSubmitResult` with the assigned job ID and
        ``scheduler='slurm'``.

    Raises:
        BatchJobError: When ``sbatch`` exits non-zero.

    Falls back to local execution when ``sbatch`` is not found on PATH,
    returning a result with ``scheduler='local'`` so the caller does not
    need to special-case its absence.
    """
    extra_args = extra_args or []
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    stdout_path = str(ws / f"{job_name}_%j.out")
    stderr_path = str(ws / f"{job_name}_%j.err")

    script_path = _write_slurm_script(
        ws, command, job_name, stdout_path, stderr_path, extra_args
    )

    sbatch_cmd = ["sbatch", *extra_args, str(script_path)]

    try:
        proc = subprocess.run(
            sbatch_cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        logger.info(
            "sbatch not found; falling back to local execution for job '%s'",
            job_name,
        )
        return _run_local(command, workspace, job_name)

    if proc.returncode != 0:
        raise BatchJobError(
            f"sbatch failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )

    # Parse "Submitted batch job <ID>" from stdout
    raw_out = (proc.stdout or "").strip()
    job_id = raw_out.split()[-1] if raw_out else "unknown"
    logger.info("SLURM job submitted: job_id=%s name=%s", job_id, job_name)
    return BatchSubmitResult(job_id=job_id, scheduler="slurm")


def submit_pbs(
    command: list[str],
    workspace: str,
    job_name: str,
    *,
    extra_args: list[str] | None = None,
) -> BatchSubmitResult:
    """Package ``command`` as a PBS job and submit it via ``qsub``.

    Args:
        command: The command (argv list) to run inside the job.
        workspace: Path to the working directory used for script/output files.
        job_name: Human-readable job name passed to ``-N``.
        extra_args: Additional ``qsub`` CLI arguments (e.g.
            ``["-l", "select=1:ncpus=4:mem=8gb"]``).

    Returns:
        :class:`BatchSubmitResult` with the assigned job ID and
        ``scheduler='pbs'``.

    Raises:
        BatchJobError: When ``qsub`` exits non-zero.

    Falls back to local execution when ``qsub`` is not found on PATH,
    returning a result with ``scheduler='local'``.
    """
    extra_args = extra_args or []
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    stdout_path = str(ws / f"{job_name}.out")
    stderr_path = str(ws / f"{job_name}.err")

    script_path = _write_pbs_script(
        ws, command, job_name, stdout_path, stderr_path, extra_args
    )

    qsub_cmd = ["qsub", *extra_args, str(script_path)]

    try:
        proc = subprocess.run(
            qsub_cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        logger.info(
            "qsub not found; falling back to local execution for job '%s'",
            job_name,
        )
        return _run_local(command, workspace, job_name)

    if proc.returncode != 0:
        raise BatchJobError(
            f"qsub failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )

    job_id = (proc.stdout or "").strip()
    logger.info("PBS job submitted: job_id=%s name=%s", job_id, job_name)
    return BatchSubmitResult(job_id=job_id, scheduler="pbs")


def poll_until_done(
    job: BatchJob,
    *,
    poll_interval: float = 30.0,
    timeout: float = 86400.0,
) -> JobStatus:
    """Block until ``job`` reaches a terminal state, then return its status.

    Polls the scheduler (SLURM via ``squeue``, PBS via ``qstat``) at
    ``poll_interval``-second intervals. Reads stdout/stderr files into
    ``job.stdout`` / ``job.stderr`` after the job terminates.

    Local fallback jobs (``scheduler='local'``) are already complete by
    the time they are submitted, so this function returns immediately.

    Args:
        job: The :class:`BatchJob` to monitor (mutated in place with
            stdout/stderr content on completion).
        poll_interval: Seconds between scheduler status checks.
        timeout: Maximum wall-clock seconds to wait before raising
            :class:`BatchJobError`.

    Returns:
        The terminal :class:`JobStatus` (COMPLETED or FAILED).

    Raises:
        BatchJobError: When the timeout is exceeded.
    """
    if job.scheduler == "local":
        _ingest_outputs(job)
        return JobStatus.COMPLETED

    deadline = time.monotonic() + timeout

    while True:
        if time.monotonic() >= deadline:
            raise BatchJobError(
                f"Timeout after {timeout:.0f}s waiting for {job.scheduler} "
                f"job {job.job_id}"
            )

        status = _query_status(job)
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            _ingest_outputs(job)
            return status

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Internal polling helpers
# ---------------------------------------------------------------------------


def _query_status(job: BatchJob) -> JobStatus:
    """Query the scheduler and return the current :class:`JobStatus`."""
    if job.scheduler == "slurm":
        return _slurm_status(job.job_id)
    if job.scheduler == "pbs":
        return _pbs_status(job.job_id)
    return JobStatus.UNKNOWN


def _slurm_status(job_id: str) -> JobStatus:
    """Check SLURM job status via ``squeue``."""
    try:
        proc = subprocess.run(
            [
                "squeue",
                "--job",
                job_id,
                "--noheader",
                "--format=%T",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return JobStatus.UNKNOWN

    raw = (proc.stdout or "").strip().upper()

    if "COMPLETED" in raw:
        return JobStatus.COMPLETED
    if any(s in raw for s in ("FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OOM")):
        return JobStatus.FAILED
    if any(s in raw for s in ("RUNNING", "COMPLETING")):
        return JobStatus.RUNNING
    if any(s in raw for s in ("PENDING", "CONFIGURING", "RESVING")):
        return JobStatus.PENDING
    # Empty output from squeue means the job is no longer queued — done
    if not raw:
        return JobStatus.COMPLETED

    return JobStatus.UNKNOWN


def _pbs_status(job_id: str) -> JobStatus:
    """Check PBS job status via ``qstat``."""
    try:
        proc = subprocess.run(
            ["qstat", job_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return JobStatus.UNKNOWN

    # PBS qstat returns non-zero when the job no longer exists (completed/failed)
    if proc.returncode != 0:
        return JobStatus.COMPLETED

    raw = (proc.stdout or "").upper()
    if " F " in raw or "FINISHED" in raw:
        return JobStatus.COMPLETED
    if " E " in raw or "EXITING" in raw:
        return JobStatus.COMPLETED
    if " R " in raw or "RUNNING" in raw:
        return JobStatus.RUNNING
    if " Q " in raw or "QUEUED" in raw:
        return JobStatus.PENDING

    return JobStatus.UNKNOWN


def _ingest_outputs(job: BatchJob) -> None:
    """Read stdout/stderr files into ``job.stdout`` / ``job.stderr``."""
    for attr, path in (("stdout", job.stdout_path), ("stderr", job.stderr_path)):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = None
        setattr(job, attr, text)
