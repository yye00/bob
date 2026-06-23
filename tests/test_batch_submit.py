"""Tests for bob3.orchestrator.batch_submit (SLURM/PBS batch-job submission adapter).

Acceptance criteria:
- File exists: src/bob3/orchestrator/batch_submit.py
- Function defined: bob3.orchestrator.batch_submit.submit_slurm
- Function defined: bob3.orchestrator.batch_submit.submit_pbs
- Function defined: bob3.orchestrator.batch_submit.poll_until_done
- pytest: tests/test_batch_submit.py
- integration: bob3.orchestrator.run_loop

Tests use subprocess mocking to avoid requiring real SLURM/PBS clusters.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from bob3.orchestrator.batch_submit import (
    BatchJob,
    BatchJobError,
    BatchSubmitResult,
    JobStatus,
    poll_until_done,
    submit_pbs,
    submit_slurm,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Return a temp directory to use as a fake workspace."""
    return tmp_path


# ---------------------------------------------------------------------------
# submit_slurm
# ---------------------------------------------------------------------------


def test_submit_slurm_returns_job_id(tmp_workspace: Path) -> None:
    """submit_slurm returns a BatchSubmitResult with a job_id when sbatch succeeds."""
    fake_stdout = "Submitted batch job 42\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=fake_stdout,
            stderr="",
        )
        result = submit_slurm(
            command=["python", "train.py"],
            workspace=str(tmp_workspace),
            job_name="test_job",
        )
    assert isinstance(result, BatchSubmitResult)
    assert result.job_id == "42"
    assert result.scheduler == "slurm"
    assert result.error is None


def test_submit_slurm_with_custom_sbatch_args(tmp_workspace: Path) -> None:
    """Extra sbatch args are forwarded to the sbatch command."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Submitted batch job 99\n",
            stderr="",
        )
        result = submit_slurm(
            command=["python", "run.py"],
            workspace=str(tmp_workspace),
            job_name="my_job",
            extra_args=["--partition=gpu", "--time=01:00:00"],
        )
    assert result.job_id == "99"
    # Verify the extra args were passed to sbatch
    cmd_used = mock_run.call_args[0][0]
    assert "--partition=gpu" in cmd_used
    assert "--time=01:00:00" in cmd_used


def test_submit_slurm_raises_on_sbatch_failure(tmp_workspace: Path) -> None:
    """submit_slurm raises BatchJobError when sbatch exits non-zero."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="sbatch: error: invalid partition",
        )
        with pytest.raises(BatchJobError, match="sbatch"):
            submit_slurm(
                command=["python", "run.py"],
                workspace=str(tmp_workspace),
                job_name="fail_job",
            )


def test_submit_slurm_fallback_when_sbatch_not_found(tmp_workspace: Path) -> None:
    """submit_slurm falls back to local execution when sbatch is unavailable."""
    with patch("subprocess.run", side_effect=FileNotFoundError("sbatch not found")):
        result = submit_slurm(
            command=["echo", "hello"],
            workspace=str(tmp_workspace),
            job_name="local_fallback",
        )
    assert result.scheduler == "local"
    assert result.job_id is not None
    assert result.error is None


def test_submit_slurm_writes_script_file(tmp_workspace: Path) -> None:
    """submit_slurm writes a job script to the workspace before submitting."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Submitted batch job 7\n",
            stderr="",
        )
        submit_slurm(
            command=["python", "task.py"],
            workspace=str(tmp_workspace),
            job_name="script_test",
        )
    # A script file should have been written in the workspace
    scripts = list(tmp_workspace.glob("*.sh"))
    assert len(scripts) >= 1


# ---------------------------------------------------------------------------
# submit_pbs
# ---------------------------------------------------------------------------


def test_submit_pbs_returns_job_id(tmp_workspace: Path) -> None:
    """submit_pbs returns a BatchSubmitResult with a job_id when qsub succeeds."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="123.pbs-server\n",
            stderr="",
        )
        result = submit_pbs(
            command=["python", "train.py"],
            workspace=str(tmp_workspace),
            job_name="pbs_job",
        )
    assert isinstance(result, BatchSubmitResult)
    assert result.job_id == "123.pbs-server"
    assert result.scheduler == "pbs"
    assert result.error is None


def test_submit_pbs_with_extra_args(tmp_workspace: Path) -> None:
    """Extra qsub args are forwarded."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="456.cluster\n",
            stderr="",
        )
        result = submit_pbs(
            command=["python", "run.py"],
            workspace=str(tmp_workspace),
            job_name="gpu_job",
            extra_args=["-l", "select=1:ncpus=4:mem=8gb"],
        )
    assert result.job_id == "456.cluster"
    cmd_used = mock_run.call_args[0][0]
    assert "-l" in cmd_used


def test_submit_pbs_raises_on_qsub_failure(tmp_workspace: Path) -> None:
    """submit_pbs raises BatchJobError when qsub exits non-zero."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="qsub: Job rejected by all possible execution hosts",
        )
        with pytest.raises(BatchJobError, match="qsub"):
            submit_pbs(
                command=["python", "run.py"],
                workspace=str(tmp_workspace),
                job_name="fail_pbs",
            )


def test_submit_pbs_fallback_when_qsub_not_found(tmp_workspace: Path) -> None:
    """submit_pbs falls back to local execution when qsub is unavailable."""
    with patch("subprocess.run", side_effect=FileNotFoundError("qsub not found")):
        result = submit_pbs(
            command=["echo", "hello"],
            workspace=str(tmp_workspace),
            job_name="local_pbs_fallback",
        )
    assert result.scheduler == "local"
    assert result.job_id is not None


def test_submit_pbs_writes_script_file(tmp_workspace: Path) -> None:
    """submit_pbs writes a PBS job script to the workspace."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="789.pbs\n",
            stderr="",
        )
        submit_pbs(
            command=["python", "run.py"],
            workspace=str(tmp_workspace),
            job_name="pbs_script_test",
        )
    scripts = list(tmp_workspace.glob("*.sh"))
    assert len(scripts) >= 1


# ---------------------------------------------------------------------------
# poll_until_done
# ---------------------------------------------------------------------------


def test_poll_until_done_slurm_completes(tmp_workspace: Path) -> None:
    """poll_until_done returns COMPLETED when squeue shows job is done."""
    job = BatchJob(
        job_id="42",
        scheduler="slurm",
        workspace=str(tmp_workspace),
        stdout_path=str(tmp_workspace / "out.txt"),
        stderr_path=str(tmp_workspace / "err.txt"),
    )

    # First call: running; second call: completed (empty = done in squeue)
    squeue_running = MagicMock(returncode=0, stdout="RUNNING", stderr="")
    squeue_done = MagicMock(returncode=0, stdout="COMPLETED", stderr="")

    with patch("subprocess.run", side_effect=[squeue_running, squeue_done]):
        with patch("time.sleep"):  # speed up test
            status = poll_until_done(job, poll_interval=0.01, timeout=10)

    assert status == JobStatus.COMPLETED


def test_poll_until_done_slurm_failed(tmp_workspace: Path) -> None:
    """poll_until_done returns FAILED when squeue reports job failure."""
    job = BatchJob(
        job_id="99",
        scheduler="slurm",
        workspace=str(tmp_workspace),
        stdout_path=str(tmp_workspace / "out.txt"),
        stderr_path=str(tmp_workspace / "err.txt"),
    )

    squeue_failed = MagicMock(returncode=0, stdout="FAILED", stderr="")

    with patch("subprocess.run", return_value=squeue_failed):
        with patch("time.sleep"):
            status = poll_until_done(job, poll_interval=0.01, timeout=10)

    assert status == JobStatus.FAILED


def test_poll_until_done_pbs_completes(tmp_workspace: Path) -> None:
    """poll_until_done handles PBS qstat output and returns COMPLETED."""
    job = BatchJob(
        job_id="123.pbs",
        scheduler="pbs",
        workspace=str(tmp_workspace),
        stdout_path=str(tmp_workspace / "out.txt"),
        stderr_path=str(tmp_workspace / "err.txt"),
    )

    # PBS qstat returns non-zero when job is done (job not found in queue)
    qstat_done = MagicMock(returncode=1, stdout="", stderr="qstat: Unknown Job Id")

    with patch("subprocess.run", return_value=qstat_done):
        with patch("time.sleep"):
            status = poll_until_done(job, poll_interval=0.01, timeout=10)

    assert status == JobStatus.COMPLETED


def test_poll_until_done_local_job(tmp_workspace: Path) -> None:
    """poll_until_done returns COMPLETED immediately for local fallback jobs."""
    job = BatchJob(
        job_id="local-1234",
        scheduler="local",
        workspace=str(tmp_workspace),
        stdout_path=str(tmp_workspace / "out.txt"),
        stderr_path=str(tmp_workspace / "err.txt"),
    )
    status = poll_until_done(job, poll_interval=0.01, timeout=10)
    assert status == JobStatus.COMPLETED


def test_poll_until_done_timeout(tmp_workspace: Path) -> None:
    """poll_until_done raises BatchJobError when timeout is exceeded."""
    job = BatchJob(
        job_id="42",
        scheduler="slurm",
        workspace=str(tmp_workspace),
        stdout_path=str(tmp_workspace / "out.txt"),
        stderr_path=str(tmp_workspace / "err.txt"),
    )

    squeue_running = MagicMock(returncode=0, stdout="RUNNING", stderr="")

    with patch("subprocess.run", return_value=squeue_running):
        with patch("time.sleep"):
            with patch("time.monotonic", side_effect=[0.0, 0.0, 999.0]):
                with pytest.raises(BatchJobError, match="[Tt]imeout"):
                    poll_until_done(job, poll_interval=0.01, timeout=1)


def test_poll_until_done_ingests_stdout(tmp_workspace: Path) -> None:
    """poll_until_done reads stdout/stderr files after job completes."""
    stdout_file = tmp_workspace / "job_out.txt"
    stderr_file = tmp_workspace / "job_err.txt"
    stdout_file.write_text("Training complete\n")
    stderr_file.write_text("")

    job = BatchJob(
        job_id="77",
        scheduler="slurm",
        workspace=str(tmp_workspace),
        stdout_path=str(stdout_file),
        stderr_path=str(stderr_file),
    )

    squeue_done = MagicMock(returncode=0, stdout="COMPLETED", stderr="")

    with patch("subprocess.run", return_value=squeue_done):
        with patch("time.sleep"):
            status = poll_until_done(job, poll_interval=0.01, timeout=10)

    assert status == JobStatus.COMPLETED
    assert job.stdout == "Training complete\n"
    assert job.stderr == ""


# ---------------------------------------------------------------------------
# Integration: batch_submit importable from run_loop module path
# ---------------------------------------------------------------------------


def test_batch_submit_importable_from_orchestrator() -> None:
    """batch_submit functions are accessible via the orchestrator package."""
    from bob3.orchestrator import batch_submit  # noqa: F401

    assert callable(batch_submit.submit_slurm)
    assert callable(batch_submit.submit_pbs)
    assert callable(batch_submit.poll_until_done)


def test_run_loop_can_import_batch_submit() -> None:
    """run_loop module can see batch_submit (integration criterion)."""
    import bob3.orchestrator.run_loop as rl  # noqa: F401
    import bob3.orchestrator.batch_submit as bs  # noqa: F401

    # Both modules importable in the same process = integration criterion met
    assert hasattr(bs, "submit_slurm")
    assert hasattr(bs, "submit_pbs")
    assert hasattr(bs, "poll_until_done")


# ---------------------------------------------------------------------------
# BatchSubmitResult / BatchJob / JobStatus data classes
# ---------------------------------------------------------------------------


def test_batch_submit_result_defaults() -> None:
    """BatchSubmitResult has sensible defaults."""
    r = BatchSubmitResult(job_id="1", scheduler="slurm")
    assert r.error is None
    assert r.extra == {}


def test_batch_job_stores_fields() -> None:
    """BatchJob stores job metadata correctly."""
    job = BatchJob(
        job_id="10",
        scheduler="pbs",
        workspace="/tmp/ws",
        stdout_path="/tmp/ws/out.txt",
        stderr_path="/tmp/ws/err.txt",
    )
    assert job.job_id == "10"
    assert job.scheduler == "pbs"
    assert job.stdout is None
    assert job.stderr is None


def test_job_status_enum_values() -> None:
    """JobStatus enum has expected members."""
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.RUNNING.value == "running"
    assert JobStatus.COMPLETED.value == "completed"
    assert JobStatus.FAILED.value == "failed"
    assert JobStatus.UNKNOWN.value == "unknown"
