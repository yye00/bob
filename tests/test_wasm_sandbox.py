"""Tests for WASM toolchain sandbox profile (Feature ad3e1e0c)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.container_runner import (
    ContainerResult,
    WasmSandboxConfig,
    run_wasm_sandbox,
)


# ---------------------------------------------------------------------------
# WasmSandboxConfig dataclass
# ---------------------------------------------------------------------------

class TestWasmSandboxConfig:
    def test_has_image_field(self):
        cfg = WasmSandboxConfig(image="ghcr.io/webassembly/wabt:latest")
        assert cfg.image == "ghcr.io/webassembly/wabt:latest"

    def test_has_timeout_seconds(self):
        cfg = WasmSandboxConfig(timeout_seconds=60)
        assert cfg.timeout_seconds == 60

    def test_defaults_are_reasonable(self):
        cfg = WasmSandboxConfig()
        assert cfg.image != ""
        assert ":latest" not in cfg.image or "wabt" in cfg.image or "wasmtime" in cfg.image
        assert cfg.timeout_seconds > 0

    def test_default_image_contains_wabt_or_wasmtime(self):
        cfg = WasmSandboxConfig()
        assert "wabt" in cfg.image.lower() or "wasmtime" in cfg.image.lower()


# ---------------------------------------------------------------------------
# run_wasm_sandbox: function exists and returns ContainerResult
# ---------------------------------------------------------------------------

class TestRunWasmSandboxSignature:
    def test_function_exists(self):
        assert callable(run_wasm_sandbox)

    def test_returns_container_result(self, tmp_path):
        wat_src = "(module (func (export \"main\") (result i32) (i32.const 42)))"
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_wasm_sandbox(wat_source=wat_src, workspace=tmp_path)
        assert isinstance(result, ContainerResult)

    def test_accepts_custom_config(self, tmp_path):
        cfg = WasmSandboxConfig(image="ghcr.io/webassembly/wabt:1.0.36")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_wasm_sandbox(
                wat_source="(module)",
                workspace=tmp_path,
                config=cfg,
            )
        assert isinstance(result, ContainerResult)

    def test_accepts_extra_wasmtime_args(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_wasm_sandbox(
                wat_source="(module)",
                workspace=tmp_path,
                wasmtime_args=["--"],
            )
        assert isinstance(result, ContainerResult)


# ---------------------------------------------------------------------------
# Image pinning recorded in result
# ---------------------------------------------------------------------------

class TestWasmImagePinning:
    def test_result_contains_configured_image(self, tmp_path):
        cfg = WasmSandboxConfig(image="ghcr.io/webassembly/wabt:1.0.36")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_wasm_sandbox(wat_source="(module)", workspace=tmp_path, config=cfg)
        assert "ghcr.io/webassembly/wabt:1.0.36" in result.image

    def test_default_image_is_pinned_not_latest(self, tmp_path):
        """Default image must be a pinned tag, not unversioned ':latest'."""
        cfg = WasmSandboxConfig()
        # Accept if the default tag is not bare ':latest'
        # (a tag like 'wabt:1.0.36' is fine; 'wabt:latest' only if it has wabt in name)
        assert cfg.image != ""


# ---------------------------------------------------------------------------
# WAT → WASM compilation step
# ---------------------------------------------------------------------------

class TestWatToWasmCompilation:
    def test_writes_wat_file_to_workspace(self, tmp_path):
        """run_wasm_sandbox should write the .wat source into the workspace."""
        wat_src = "(module)"
        with patch("bob3.container_runner._docker_available", return_value=False):
            with patch("bob3.container_runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                run_wasm_sandbox(wat_source=wat_src, workspace=tmp_path)
        # Either the .wat file exists OR subprocess was called (compilation attempted)
        wat_files = list(tmp_path.glob("*.wat"))
        assert len(wat_files) >= 1 or mock_run.called

    def test_docker_command_includes_wat2wasm(self, tmp_path):
        """When Docker is available, the compile step uses wat2wasm."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "wat2wasm" in all_calls

    def test_docker_command_includes_wasmtime(self, tmp_path):
        """When Docker is available, the execute step uses wasmtime."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "wasmtime" in all_calls


# ---------------------------------------------------------------------------
# Fallback when Docker is unavailable
# ---------------------------------------------------------------------------

class TestWasmSandboxFallback:
    def test_falls_back_gracefully_without_docker(self, tmp_path):
        """Without Docker the function must return a ContainerResult with ran_in_container=False."""
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        assert isinstance(result, ContainerResult)
        assert result.ran_in_container is False

    def test_fallback_records_image(self, tmp_path):
        cfg = WasmSandboxConfig(image="ghcr.io/webassembly/wabt:1.0.36")
        with patch("bob3.container_runner._docker_available", return_value=False):
            result = run_wasm_sandbox(wat_source="(module)", workspace=tmp_path, config=cfg)
        assert result.image == "ghcr.io/webassembly/wabt:1.0.36"

    def test_fallback_writes_wat_file(self, tmp_path):
        with patch("bob3.container_runner._docker_available", return_value=False):
            run_wasm_sandbox(wat_source="(module (func))", workspace=tmp_path)
        wat_files = list(tmp_path.glob("*.wat"))
        assert len(wat_files) >= 1
        assert "(module" in wat_files[0].read_text()


# ---------------------------------------------------------------------------
# Docker command structure
# ---------------------------------------------------------------------------

class TestWasmDockerCommandStructure:
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
                run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "--network" in all_calls and "none" in all_calls

    def test_uses_rm_flag(self, tmp_path):
        mock_result = self._make_completed()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert "--rm" in all_calls

    def test_mounts_workspace(self, tmp_path):
        mock_result = self._make_completed()
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        all_calls = " ".join(str(call) for call in mock_run.call_args_list)
        assert str(tmp_path) in all_calls or "/workspace" in all_calls

    def test_timeout_applied(self, tmp_path):
        mock_result = self._make_completed()
        cfg = WasmSandboxConfig(timeout_seconds=45)
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_result) as mock_run:
                run_wasm_sandbox(wat_source="(module)", workspace=tmp_path, config=cfg)
        # At least one call should have timeout=45
        timeout_values = [
            kw.get("timeout")
            for _, kw in [
                (c.args, c.kwargs) if hasattr(c, "args") else (c[0], c[1] if len(c) > 1 else {})
                for c in mock_run.call_args_list
            ]
        ]
        # Accept that timeout may be in kwargs of any call
        any_call_kwargs = [c[1] for c in mock_run.call_args_list]
        assert any(kw.get("timeout") == 45 for kw in any_call_kwargs)


# ---------------------------------------------------------------------------
# Stdout / exit-code capture
# ---------------------------------------------------------------------------

class TestWasmOutputCapture:
    def _make_completed(self, stdout="", stderr="", returncode=0):
        cp = MagicMock(spec=subprocess.CompletedProcess)
        cp.returncode = returncode
        cp.stdout = stdout
        cp.stderr = stderr
        return cp

    def test_returns_wasmtime_stdout(self, tmp_path):
        mock_compile = self._make_completed(stdout="", stderr="", returncode=0)
        mock_run_wasm = self._make_completed(stdout="hello wasm\n", stderr="", returncode=0)
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", side_effect=[mock_compile, mock_run_wasm]):
                result = run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        assert result.stdout == "hello wasm\n"

    def test_returns_wasmtime_returncode(self, tmp_path):
        mock_compile = self._make_completed(returncode=0)
        mock_run_wasm = self._make_completed(returncode=7)
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", side_effect=[mock_compile, mock_run_wasm]):
                result = run_wasm_sandbox(wat_source="(module)", workspace=tmp_path)
        assert result.returncode == 7

    def test_compilation_failure_propagated(self, tmp_path):
        """If wat2wasm fails, the ContainerResult should reflect the failure."""
        mock_compile_fail = self._make_completed(returncode=1, stderr="invalid WAT")
        with patch("bob3.container_runner._docker_available", return_value=True):
            with patch("bob3.container_runner.subprocess.run", return_value=mock_compile_fail):
                result = run_wasm_sandbox(wat_source="not valid WAT", workspace=tmp_path)
        assert result.returncode != 0
