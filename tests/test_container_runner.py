"""Tests for hermetic per-run containerisation (Feature b80e8f9c)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob.container_runner import ContainerResult, run_in_container


class TestContainerResult:
    """Verify ContainerResult dataclass structure."""

    def test_has_returncode(self):
        r = ContainerResult(returncode=0, stdout="", stderr="", image="img:latest")
        assert r.returncode == 0

    def test_has_stdout(self):
        r = ContainerResult(returncode=0, stdout="hello", stderr="", image="img:latest")
        assert r.stdout == "hello"

    def test_has_stderr(self):
        r = ContainerResult(returncode=0, stdout="", stderr="err", image="img:latest")
        assert r.stderr == "err"

    def test_has_image(self):
        r = ContainerResult(returncode=0, stdout="", stderr="", image="python:3.11-slim")
        assert r.image == "python:3.11-slim"

    def test_has_ran_in_container_flag(self):
        r = ContainerResult(returncode=0, stdout="", stderr="", image="img:latest", ran_in_container=True)
        assert r.ran_in_container is True

    def test_ran_in_container_defaults_false(self):
        r = ContainerResult(returncode=0, stdout="", stderr="", image="img:latest")
        assert r.ran_in_container is False


class TestRunInContainerSignature:
    """Verify the function has the correct signature."""

    def test_function_exists(self):
        from bob.container_runner import run_in_container
        assert callable(run_in_container)

    def test_returns_container_result(self, tmp_path):
        with patch("bob.container_runner._docker_available", return_value=False):
            result = run_in_container(["echo", "hello"], image="python:3.11-slim", workspace=tmp_path)
        assert isinstance(result, ContainerResult)


class TestDockerUnavailableFallback:
    """When Docker is not available, fall back to direct execution with a warning."""

    def test_fallback_executes_command(self, tmp_path):
        with patch("bob.container_runner._docker_available", return_value=False):
            result = run_in_container(["echo", "hello"], image="python:3.11-slim", workspace=tmp_path)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_fallback_sets_ran_in_container_false(self, tmp_path):
        with patch("bob.container_runner._docker_available", return_value=False):
            result = run_in_container(["echo", "hi"], image="python:3.11-slim", workspace=tmp_path)
        assert result.ran_in_container is False

    def test_fallback_records_image(self, tmp_path):
        img = "myrepo/myimage:v1.2.3"
        with patch("bob.container_runner._docker_available", return_value=False):
            result = run_in_container(["echo", "x"], image=img, workspace=tmp_path)
        assert result.image == img

    def test_fallback_logs_warning(self, tmp_path, caplog):
        import logging
        with patch("bob.container_runner._docker_available", return_value=False):
            with caplog.at_level(logging.WARNING, logger="bob.container_runner"):
                run_in_container(["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        assert any("docker" in msg.lower() or "unavailable" in msg.lower() or "degrading" in msg.lower() or "fallback" in msg.lower() for msg in caplog.messages)

    def test_fallback_captures_stderr(self, tmp_path):
        with patch("bob.container_runner._docker_available", return_value=False):
            result = run_in_container(
                ["python3", "-c", "import sys; sys.stderr.write('err_msg')"],
                image="python:3.11-slim",
                workspace=tmp_path,
            )
        assert "err_msg" in result.stderr

    def test_fallback_nonzero_exit_code(self, tmp_path):
        with patch("bob.container_runner._docker_available", return_value=False):
            result = run_in_container(["false"], image="python:3.11-slim", workspace=tmp_path)
        assert result.returncode != 0


class TestDockerAvailableExecution:
    """When Docker is available, run the command inside a container."""

    def _make_completed(self, stdout="", stderr="", returncode=0):
        cp = MagicMock(spec=subprocess.CompletedProcess)
        cp.returncode = returncode
        cp.stdout = stdout
        cp.stderr = stderr
        return cp

    def test_runs_in_container_sets_flag(self, tmp_path):
        mock_result = self._make_completed(stdout="hi\n")
        with patch("bob.container_runner._docker_available", return_value=True):
            with patch("bob.container_runner._run_docker", return_value=mock_result):
                result = run_in_container(["echo", "hi"], image="python:3.11-slim", workspace=tmp_path)
        assert result.ran_in_container is True

    def test_passes_image_to_docker(self, tmp_path):
        mock_result = self._make_completed()
        with patch("bob.container_runner._docker_available", return_value=True):
            with patch("bob.container_runner._run_docker", return_value=mock_result) as mock_docker:
                run_in_container(["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        call_args = mock_docker.call_args
        assert "python:3.11-slim" in str(call_args)

    def test_workspace_mounted(self, tmp_path):
        mock_result = self._make_completed()
        with patch("bob.container_runner._docker_available", return_value=True):
            with patch("bob.container_runner._run_docker", return_value=mock_result) as mock_docker:
                run_in_container(["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        call_args = mock_docker.call_args
        assert str(tmp_path) in str(call_args)

    def test_returns_docker_stdout(self, tmp_path):
        mock_result = self._make_completed(stdout="from_docker\n")
        with patch("bob.container_runner._docker_available", return_value=True):
            with patch("bob.container_runner._run_docker", return_value=mock_result):
                result = run_in_container(["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        assert result.stdout == "from_docker\n"

    def test_returns_docker_returncode(self, tmp_path):
        mock_result = self._make_completed(returncode=42)
        with patch("bob.container_runner._docker_available", return_value=True):
            with patch("bob.container_runner._run_docker", return_value=mock_result):
                result = run_in_container(["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        assert result.returncode == 42

    def test_records_image_in_result(self, tmp_path):
        mock_result = self._make_completed()
        img = "myrepo/img:sha256"
        with patch("bob.container_runner._docker_available", return_value=True):
            with patch("bob.container_runner._run_docker", return_value=mock_result):
                result = run_in_container(["true"], image=img, workspace=tmp_path)
        assert result.image == img


class TestDockerAvailableCheck:
    """Verify _docker_available() detects Docker correctly."""

    def test_docker_available_returns_bool(self):
        from bob.container_runner import _docker_available
        result = _docker_available()
        assert isinstance(result, bool)

    def test_docker_unavailable_when_not_found(self):
        from bob.container_runner import _docker_available
        with patch("bob.container_runner.shutil.which", return_value=None):
            assert _docker_available() is False

    def test_docker_available_when_found(self):
        from bob.container_runner import _docker_available
        with patch("bob.container_runner.shutil.which", return_value="/usr/bin/docker"):
            with patch("bob.container_runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                assert _docker_available() is True


class TestRunDockerInternal:
    """Verify _run_docker builds the correct Docker command."""

    def test_uses_docker_run(self, tmp_path):
        from bob.container_runner import _run_docker
        with patch("bob.container_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _run_docker(cmd=["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        docker_cmd = mock_run.call_args[0][0]
        assert docker_cmd[0] == "docker"
        assert "run" in docker_cmd

    def test_mounts_workspace_as_volume(self, tmp_path):
        from bob.container_runner import _run_docker
        with patch("bob.container_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _run_docker(cmd=["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        docker_cmd = " ".join(mock_run.call_args[0][0])
        assert "/workspace" in docker_cmd or str(tmp_path) in docker_cmd

    def test_no_network_flag(self, tmp_path):
        from bob.container_runner import _run_docker
        with patch("bob.container_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _run_docker(cmd=["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        docker_cmd = " ".join(mock_run.call_args[0][0])
        assert "--network" in docker_cmd and "none" in docker_cmd

    def test_rm_flag_for_ephemeral_container(self, tmp_path):
        from bob.container_runner import _run_docker
        with patch("bob.container_runner.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _run_docker(cmd=["echo", "x"], image="python:3.11-slim", workspace=tmp_path)
        docker_cmd = " ".join(mock_run.call_args[0][0])
        assert "--rm" in docker_cmd
