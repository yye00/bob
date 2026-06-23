"""Tests for scientific-compute sandbox profile (Feature cab88a4e)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.container_runner import (
    ContainerResult,
    SciSandboxConfig,
    run_sci_sandbox,
)


# ---------------------------------------------------------------------------
# SciSandboxConfig dataclass
# ---------------------------------------------------------------------------

class TestSciSandboxConfig:
    def test_has_image_field(self):
        cfg = SciSandboxConfig(image="ghcr.io/scipy/scipy-dev:numpy1.26-scipy1.13-jax0.4-py311")
        assert "scipy" in cfg.image or "numpy" in cfg.image or "jax" in cfg.image

    def test_has_timeout_seconds(self):
        cfg = SciSandboxConfig(timeout_seconds=120)
        assert cfg.timeout_seconds == 120

    def test_defaults_have_nonempty_image(self):
        cfg = SciSandboxConfig()
        assert cfg.image != ""

    def test_default_image_is_pinned_not_latest(self):
        cfg = SciSandboxConfig()
        assert ":latest" not in cfg.image

    def test_defaults_have_positive_timeout(self):
        cfg = SciSandboxConfig()
        assert cfg.timeout_seconds > 0

    def test_has_blas_env_vars(self):
        """Config must expose deterministic BLAS env vars."""
        cfg = SciSandboxConfig()
        assert hasattr(cfg, "omp_num_threads")
        assert hasattr(cfg, "openblas_num_threads")
        assert hasattr(cfg, "mkl_num_threads")
        assert hasattr(cfg, "jax_platform_name")

    def test_blas_defaults_are_deterministic(self):
        """BLAS thread counts must default to 1 for reproducibility."""
        cfg = SciSandboxConfig()
        assert cfg.omp_num_threads == 1
        assert cfg.openblas_num_threads == 1
        assert cfg.mkl_num_threads == 1
        assert cfg.jax_platform_name == "cpu"


# ---------------------------------------------------------------------------
# run_sci_sandbox: function exists and returns ContainerResult
# ---------------------------------------------------------------------------

class TestRunSciSandboxSignature:
    def test_function_exists(self):
        assert callable(run_sci_sandbox)

    def test_returns_container_result(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_sci_sandbox(
                cmd=["python3", "-c", "print('ok')"],
                workspace=tmp_path,
            )
        assert isinstance(result, ContainerResult)

    def test_accepts_custom_config(self, tmp_path):
        cfg = SciSandboxConfig(image="ghcr.io/scipy/scipy-dev:numpy1.26-scipy1.13-jax0.4-py311")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_sci_sandbox(
                cmd=["python3", "-c", "print('ok')"],
                workspace=tmp_path,
                config=cfg,
            )
        assert isinstance(result, ContainerResult)


# ---------------------------------------------------------------------------
# Pinned image tag recorded in result
# ---------------------------------------------------------------------------

class TestSciImagePinning:
    def test_result_contains_configured_image(self, tmp_path):
        cfg = SciSandboxConfig(image="ghcr.io/scipy/scipy-dev:numpy1.26-scipy1.13-jax0.4-py311")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path, config=cfg)
        assert cfg.image in result.image

    def test_default_image_contains_version_tag(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path)
        assert result.image != ""
        assert ":latest" not in result.image


# ---------------------------------------------------------------------------
# BLAS env vars injected into Docker command
# ---------------------------------------------------------------------------

class TestBlasEnvVarsInjected:
    def _make_completed(self, stdout="", stderr="", returncode=0):
        cp = MagicMock(spec=subprocess.CompletedProcess)
        cp.returncode = returncode
        cp.stdout = stdout
        cp.stderr = stderr
        return cp

    def test_omp_num_threads_passed_to_docker(self, tmp_path):
        mock_result = self._make_completed(stdout="ok\n")
        cfg = SciSandboxConfig()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path, config=cfg)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "OMP_NUM_THREADS=1" in all_calls

    def test_openblas_num_threads_passed_to_docker(self, tmp_path):
        mock_result = self._make_completed(stdout="ok\n")
        cfg = SciSandboxConfig()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path, config=cfg)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "OPENBLAS_NUM_THREADS=1" in all_calls

    def test_mkl_num_threads_passed_to_docker(self, tmp_path):
        mock_result = self._make_completed(stdout="ok\n")
        cfg = SciSandboxConfig()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path, config=cfg)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "MKL_NUM_THREADS=1" in all_calls

    def test_jax_platform_name_passed_to_docker(self, tmp_path):
        mock_result = self._make_completed(stdout="ok\n")
        cfg = SciSandboxConfig()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path, config=cfg)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "JAX_PLATFORM_NAME=cpu" in all_calls

    def test_custom_blas_threads_respected(self, tmp_path):
        mock_result = self._make_completed(stdout="ok\n")
        cfg = SciSandboxConfig(omp_num_threads=2, openblas_num_threads=2, mkl_num_threads=2)
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path, config=cfg)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "OMP_NUM_THREADS=2" in all_calls


# ---------------------------------------------------------------------------
# Docker command structure
# ---------------------------------------------------------------------------

class TestSciDockerCommandStructure:
    def _make_completed(self, stdout="", stderr="", returncode=0):
        cp = MagicMock(spec=subprocess.CompletedProcess)
        cp.returncode = returncode
        cp.stdout = stdout
        cp.stderr = stderr
        return cp

    def test_uses_no_network_flag(self, tmp_path):
        mock_result = self._make_completed()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "--network" in all_calls and "none" in all_calls

    def test_uses_rm_flag(self, tmp_path):
        mock_result = self._make_completed()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "--rm" in all_calls

    def test_mounts_workspace(self, tmp_path):
        mock_result = self._make_completed()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert str(tmp_path) in all_calls or "/workspace" in all_calls

    def test_timeout_applied(self, tmp_path):
        mock_result = self._make_completed()
        cfg = SciSandboxConfig(timeout_seconds=90)
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_sci_sandbox(cmd=["python3", "-c", "pass"], workspace=tmp_path, config=cfg)
        any_call_kwargs = [c[1] for c in mock_run.call_args_list]
        assert any(kw.get("timeout") == 90 for kw in any_call_kwargs)


# ---------------------------------------------------------------------------
# Fallback when Docker is unavailable
# ---------------------------------------------------------------------------

class TestSciSandboxFallback:
    def test_falls_back_gracefully_without_docker(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_sci_sandbox(
                cmd=["python3", "-c", "print('hello')"],
                workspace=tmp_path,
            )
        assert isinstance(result, ContainerResult)
        assert result.ran_in_container is False

    def test_fallback_result_contains_image(self, tmp_path):
        cfg = SciSandboxConfig(image="ghcr.io/scipy/scipy-dev:numpy1.26-scipy1.13-jax0.4-py311")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_sci_sandbox(
                cmd=["python3", "-c", "pass"],
                workspace=tmp_path,
                config=cfg,
            )
        assert cfg.image in result.image

    def test_fallback_runs_command_directly(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_sci_sandbox(
                cmd=["python3", "-c", "print('direct')"],
                workspace=tmp_path,
            )
        assert result.returncode == 0
        assert "direct" in result.stdout


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------

class TestSciSandboxTimeout:
    def _make_completed(self, stdout="", stderr="", returncode=0):
        cp = MagicMock(spec=subprocess.CompletedProcess)
        cp.returncode = returncode
        cp.stdout = stdout
        cp.stderr = stderr
        return cp

    def test_timeout_returns_returncode_124(self, tmp_path):
        cfg = SciSandboxConfig(timeout_seconds=1)
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch(
                "bob3.container_runner.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["python3"], timeout=1),
            ):
                result = run_sci_sandbox(
                    cmd=["python3", "-c", "import time; time.sleep(999)"],
                    workspace=tmp_path,
                    config=cfg,
                )
        assert result.returncode == 124


# ---------------------------------------------------------------------------
# Navier-Stokes cavity smoke test helper
# ---------------------------------------------------------------------------

class TestNavierStokesSmokeTest:
    def test_smoke_test_function_exists(self):
        from bob3.container_runner import sci_sandbox_smoke_test
        assert callable(sci_sandbox_smoke_test)

    def test_smoke_test_returns_container_result(self, tmp_path):
        from bob3.container_runner import sci_sandbox_smoke_test
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = sci_sandbox_smoke_test(workspace=tmp_path)
        assert isinstance(result, ContainerResult)

    def test_smoke_test_returncode_is_int(self, tmp_path):
        from bob3.container_runner import sci_sandbox_smoke_test
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = sci_sandbox_smoke_test(workspace=tmp_path)
        assert isinstance(result.returncode, int)
