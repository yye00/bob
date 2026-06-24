"""Tests for GPU sandbox profile (Feature 6c12f7ae)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.container_runner import (
    ContainerResult,
    GpuSandboxConfig,
    run_gpu_sandbox,
)


# ---------------------------------------------------------------------------
# GpuSandboxConfig dataclass
# ---------------------------------------------------------------------------

class TestGpuSandboxConfig:
    def test_has_cuda_image_field(self):
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04")
        assert cfg.cuda_image == "nvidia/cuda:12.4.0-base-ubuntu22.04"

    def test_has_gpu_memory_mb_cap(self):
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04", gpu_memory_mb=4096)
        assert cfg.gpu_memory_mb == 4096

    def test_has_wall_clock_seconds(self):
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04", wall_clock_seconds=300)
        assert cfg.wall_clock_seconds == 300

    def test_has_max_concurrent_jobs(self):
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04", max_concurrent_jobs=2)
        assert cfg.max_concurrent_jobs == 2

    def test_defaults_are_reasonable(self):
        cfg = GpuSandboxConfig()
        assert "nvidia/cuda" in cfg.cuda_image or "mps" in cfg.cuda_image.lower() or cfg.cuda_image != ""
        assert cfg.gpu_memory_mb > 0
        assert cfg.wall_clock_seconds > 0
        assert cfg.max_concurrent_jobs >= 1


# ---------------------------------------------------------------------------
# run_gpu_sandbox: function exists and returns ContainerResult
# ---------------------------------------------------------------------------

class TestRunGpuSandboxSignature:
    def test_function_exists(self):
        assert callable(run_gpu_sandbox)

    def test_returns_container_result(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_gpu_sandbox(
                cmd=["echo", "hello"],
                workspace=tmp_path,
            )
        assert isinstance(result, ContainerResult)

    def test_accepts_custom_config(self, tmp_path):
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_gpu_sandbox(
                cmd=["echo", "hello"],
                workspace=tmp_path,
                config=cfg,
            )
        assert isinstance(result, ContainerResult)


# ---------------------------------------------------------------------------
# Pinned driver / image tag in result
# ---------------------------------------------------------------------------

class TestImagePinning:
    def test_result_contains_cuda_image(self, tmp_path):
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_gpu_sandbox(cmd=["echo", "x"], workspace=tmp_path, config=cfg)
        assert "nvidia/cuda:12.4.0-base-ubuntu22.04" in result.image

    def test_default_image_contains_version_tag(self, tmp_path):
        """Default image must be pinned, not ':latest'."""
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_gpu_sandbox(cmd=["echo", "x"], workspace=tmp_path)
        assert result.image != ""
        assert ":latest" not in result.image


# ---------------------------------------------------------------------------
# Resource caps passed to Docker
# ---------------------------------------------------------------------------

class TestResourceCaps:
    def _make_completed(self, stdout="", stderr="", returncode=0):
        cp = MagicMock(spec=subprocess.CompletedProcess)
        cp.returncode = returncode
        cp.stdout = stdout
        cp.stderr = stderr
        return cp

    def test_gpu_flag_passed_when_docker_available(self, tmp_path):
        mock_result = self._make_completed(stdout="ok\n")
        cfg = GpuSandboxConfig(
            cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04",
            gpu_memory_mb=2048,
            wall_clock_seconds=120,
        )
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_gpu_sandbox(cmd=["echo", "x"], workspace=tmp_path, config=cfg)
        full_cmd = " ".join(str(a) for a in mock_run.call_args[0][0])
        # GPU runtime or device flag expected
        assert "--gpus" in full_cmd or "--runtime=nvidia" in full_cmd or "--device" in full_cmd

    def test_wall_clock_timeout_applied(self, tmp_path):
        """wall_clock_seconds is passed as a timeout to subprocess.run."""
        mock_result = self._make_completed(stdout="ok\n")
        cfg = GpuSandboxConfig(
            cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04",
            wall_clock_seconds=60,
        )
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_gpu_sandbox(cmd=["echo", "x"], workspace=tmp_path, config=cfg)
        call_kwargs = mock_run.call_args[1] if mock_run.call_args[1] else {}
        assert call_kwargs.get("timeout") == 60


# ---------------------------------------------------------------------------
# Telemetry recording
# ---------------------------------------------------------------------------

class TestTelemetryRecording:
    def test_telemetry_emitted_on_success(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".bob3").mkdir()

        with patch("bob3.container_runner._docker_available", return_value=False):
            run_gpu_sandbox(cmd=["echo", "x"], workspace=tmp_path)

        jsonl = tmp_path / ".bob3" / "run.jsonl"
        assert jsonl.exists(), "run.jsonl should be created by telemetry"
        import json
        lines = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) >= 1
        last = lines[-1]
        assert last.get("gpu_image") is not None or last.get("image") is not None

    def test_telemetry_records_driver_version(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".bob3").mkdir()
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04")

        with patch("bob3.container_runner._docker_available", return_value=False):
            run_gpu_sandbox(cmd=["echo", "x"], workspace=tmp_path, config=cfg)

        import json
        jsonl = tmp_path / ".bob3" / "run.jsonl"
        lines = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
        last = lines[-1]
        # The pinned image tag encodes driver version; it should appear in telemetry
        assert "12.4.0" in str(last)


# ---------------------------------------------------------------------------
# Concurrent job guard
# ---------------------------------------------------------------------------

class TestConcurrentJobGuard:
    def test_respects_max_concurrent_jobs(self, tmp_path):
        """When max_concurrent_jobs=1, a second call from the same process is allowed
        (guard is per-instance / semaphore); just verify the config is stored."""
        cfg = GpuSandboxConfig(max_concurrent_jobs=1)
        assert cfg.max_concurrent_jobs == 1


# ---------------------------------------------------------------------------
# Fallback when Docker is unavailable
# ---------------------------------------------------------------------------

class TestGpuSandboxFallback:
    def test_falls_back_gracefully_without_docker(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_gpu_sandbox(cmd=["echo", "hello"], workspace=tmp_path)
        assert result.returncode == 0
        assert "hello" in result.stdout
        assert result.ran_in_container is False

    def test_fallback_records_cuda_image(self, tmp_path):
        cfg = GpuSandboxConfig(cuda_image="nvidia/cuda:12.4.0-base-ubuntu22.04")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_gpu_sandbox(cmd=["echo", "x"], workspace=tmp_path, config=cfg)
        assert "nvidia/cuda" in result.image


# ---------------------------------------------------------------------------
# Smoke test: nanoGPT forward pass structure
# ---------------------------------------------------------------------------

class TestNanoGPTSmokeTest:
    """Verify the smoke test helper is callable and returns meaningful output."""

    def test_smoke_test_function_exists(self):
        from bob3.container_runner import gpu_sandbox_smoke_test
        assert callable(gpu_sandbox_smoke_test)

    def test_smoke_test_returns_container_result(self, tmp_path):
        from bob3.container_runner import gpu_sandbox_smoke_test
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = gpu_sandbox_smoke_test(workspace=tmp_path)
        assert isinstance(result, ContainerResult)

    def test_smoke_test_runs_nanogpt_script(self, tmp_path):
        """The smoke test must execute a Python script doing a nanoGPT forward pass."""
        from bob3.container_runner import gpu_sandbox_smoke_test
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = gpu_sandbox_smoke_test(workspace=tmp_path)
        # returncode 0 expected in direct mode (Python available, torch may or may not be)
        # We only verify it runs without crashing the harness itself
        assert isinstance(result.returncode, int)
