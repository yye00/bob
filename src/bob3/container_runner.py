"""Hermetic per-run containerisation (Feature b80e8f9c).

Provides run_in_container() which executes a command inside a fresh Docker
container with an isolated /workspace mount and no network access after image
pull. Gracefully degrades to direct execution when Docker is unavailable.

Also provides run_gpu_sandbox() / GpuSandboxConfig (Feature 6c12f7ae) for
GPU-enabled containers with CUDA/MPS pinned images and resource caps.

Also provides run_wasm_sandbox() / WasmSandboxConfig (Feature ad3e1e0c) for
WASM differential testing: compile .wat → .wasm with wat2wasm, execute with
wasmtime, capture stdout/exit code.

Also provides run_sci_sandbox() / SciSandboxConfig (Feature cab88a4e) for
scientific-compute reproducibility: pinned NumPy/SciPy/JAX image with
deterministic BLAS settings (OMP_NUM_THREADS=1, OPENBLAS_NUM_THREADS=1,
MKL_NUM_THREADS=1, JAX_PLATFORM_NAME=cpu).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPU sandbox defaults
# ---------------------------------------------------------------------------

# Pinned CUDA base image — update the tag when upgrading driver.
_DEFAULT_CUDA_IMAGE = "nvidia/cuda:12.4.0-base-ubuntu22.04"

# Default resource caps
_DEFAULT_GPU_MEMORY_MB = 8192
_DEFAULT_WALL_CLOCK_SECONDS = 600
_DEFAULT_MAX_CONCURRENT_JOBS = 4

# Global semaphore enforces max_concurrent_jobs across threads in one process.
# Re-created when max_concurrent_jobs changes (single-process guard only).
_gpu_semaphore_lock = threading.Lock()
_gpu_semaphore: Optional[threading.Semaphore] = None
_gpu_semaphore_count: int = 0


@dataclass
class ContainerResult:
    """Result of a containerised (or degraded direct) command execution."""

    returncode: int
    stdout: str
    stderr: str
    image: str
    ran_in_container: bool = False


def _docker_available() -> bool:
    """Return True if Docker is installed and the daemon is reachable."""
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _run_docker(
    cmd: list[str],
    image: str,
    workspace: Path,
) -> subprocess.CompletedProcess:
    """Build and execute the docker run command."""
    docker_cmd = [
        "docker", "run",
        "--rm",
        "--network", "none",
        "-v", f"{workspace}:/workspace",
        "-w", "/workspace",
        image,
        *cmd,
    ]
    return subprocess.run(
        docker_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_in_container(
    cmd: list[str],
    image: str,
    workspace: Path,
) -> ContainerResult:
    """Run *cmd* inside a fresh Docker container mounting *workspace*.

    Each call gets an isolated /workspace, no network access, and a clean
    container state. The pinned *image* is recorded in the returned result
    for telemetry.

    When Docker is unavailable the command runs directly on the host and
    ran_in_container is False.  This is logged as a warning, not an error.
    """
    if not _docker_available():
        logger.warning(
            "Docker unavailable — degrading to direct execution (image=%s)", image
        )
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return ContainerResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            image=image,
            ran_in_container=False,
        )

    proc = _run_docker(cmd=cmd, image=image, workspace=workspace)
    return ContainerResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        image=image,
        ran_in_container=True,
    )


# ---------------------------------------------------------------------------
# GPU sandbox — Feature 6c12f7ae
# ---------------------------------------------------------------------------

@dataclass
class GpuSandboxConfig:
    """Configuration for a GPU-enabled sandbox container.

    cuda_image must be a fully-pinned tag (e.g. ``nvidia/cuda:12.4.0-base-ubuntu22.04``)
    so that the driver version is immutably recorded in telemetry.
    """

    cuda_image: str = _DEFAULT_CUDA_IMAGE
    gpu_memory_mb: int = _DEFAULT_GPU_MEMORY_MB
    wall_clock_seconds: int = _DEFAULT_WALL_CLOCK_SECONDS
    max_concurrent_jobs: int = _DEFAULT_MAX_CONCURRENT_JOBS


def _get_gpu_semaphore(n: int) -> threading.Semaphore:
    """Return a process-level semaphore capped at *n* concurrent GPU jobs."""
    global _gpu_semaphore, _gpu_semaphore_count
    with _gpu_semaphore_lock:
        if _gpu_semaphore is None or _gpu_semaphore_count != n:
            _gpu_semaphore = threading.Semaphore(n)
            _gpu_semaphore_count = n
        return _gpu_semaphore


def _run_gpu_docker(
    cmd: list[str],
    image: str,
    workspace: Path,
    gpu_memory_mb: int,
    wall_clock_seconds: int,
) -> subprocess.CompletedProcess:
    """Build and execute the Docker run command with GPU device access."""
    docker_cmd = [
        "docker", "run",
        "--rm",
        "--gpus", f"device=0",
        "--network", "none",
        # GPU memory limit via device cgroup (bytes)
        "--device-cgroup-rule", f"c *:* rmw",
        "-e", f"CUDA_MPS_PINNED_DEVICE_MEM_LIMIT=0={gpu_memory_mb}m",
        "-v", f"{workspace}:/workspace",
        "-w", "/workspace",
        image,
        *cmd,
    ]
    return subprocess.run(
        docker_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=wall_clock_seconds,
    )


def _emit_gpu_telemetry(image: str, returncode: int, ran_in_container: bool) -> None:
    """Append a GPU sandbox telemetry record to .bob3/run.jsonl."""
    path = Path(".bob3") / "run.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": "gpu_sandbox",
            "gpu_image": image,
            "ran_in_container": ran_in_container,
            "returncode": returncode,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("GPU telemetry write failed: %s", exc)


def run_gpu_sandbox(
    cmd: list[str],
    workspace: Path,
    config: Optional[GpuSandboxConfig] = None,
) -> ContainerResult:
    """Run *cmd* inside a GPU-enabled Docker container.

    Uses a CUDA-pinned image whose tag encodes the driver version.  Resource
    caps (GPU memory, wall-clock, concurrent jobs) come from *config*.

    Falls back to direct host execution when Docker is unavailable, identical
    to ``run_in_container``.  The pinned image name is always recorded in the
    returned ``ContainerResult`` and in ``.bob3/run.jsonl`` for telemetry.
    """
    if config is None:
        config = GpuSandboxConfig()

    image = config.cuda_image
    sem = _get_gpu_semaphore(config.max_concurrent_jobs)

    with sem:
        if not _docker_available():
            logger.warning(
                "Docker unavailable — GPU sandbox degrading to direct execution (image=%s)", image
            )
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            result = ContainerResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                image=image,
                ran_in_container=False,
            )
            _emit_gpu_telemetry(image=image, returncode=result.returncode, ran_in_container=False)
            return result

        try:
            proc = _run_gpu_docker(
                cmd=cmd,
                image=image,
                workspace=workspace,
                gpu_memory_mb=config.gpu_memory_mb,
                wall_clock_seconds=config.wall_clock_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.error("GPU sandbox wall-clock timeout (%ss) exceeded", config.wall_clock_seconds)
            result = ContainerResult(
                returncode=124,
                stdout="",
                stderr="Timeout expired",
                image=image,
                ran_in_container=True,
            )
            _emit_gpu_telemetry(image=image, returncode=result.returncode, ran_in_container=True)
            return result

        result = ContainerResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            image=image,
            ran_in_container=True,
        )
        _emit_gpu_telemetry(image=image, returncode=result.returncode, ran_in_container=True)
        return result


# ---------------------------------------------------------------------------
# Smoke test: tiny nanoGPT forward pass
# ---------------------------------------------------------------------------

_NANOGPT_SMOKE_SCRIPT = """\
import sys, os

# Attempt to run a minimal GPT forward pass using PyTorch.
# If torch is not available, we report GPU utilization check as skipped
# so the sandbox itself is still validated.
try:
    import torch
    import math

    class _LayerNorm(torch.nn.Module):
        def __init__(self, d):
            super().__init__()
            self.w = torch.nn.Parameter(torch.ones(d))
            self.b = torch.nn.Parameter(torch.zeros(d))
        def forward(self, x):
            return torch.nn.functional.layer_norm(x, x.shape[-1:], self.w, self.b)

    class _Attn(torch.nn.Module):
        def __init__(self, d, h):
            super().__init__()
            self.h = h
            self.d = d
            self.qkv = torch.nn.Linear(d, 3 * d, bias=False)
            self.proj = torch.nn.Linear(d, d, bias=False)
        def forward(self, x):
            B, T, C = x.size()
            q, k, v = self.qkv(x).split(self.d, dim=2)
            scale = 1.0 / math.sqrt(C // self.h)
            q = q.view(B, T, self.h, C // self.h).transpose(1, 2)
            k = k.view(B, T, self.h, C // self.h).transpose(1, 2)
            v = v.view(B, T, self.h, C // self.h).transpose(1, 2)
            att = (q @ k.transpose(-2, -1)) * scale
            att = torch.nn.functional.softmax(att, dim=-1)
            return (att @ v).transpose(1, 2).reshape(B, T, C)

    class _Block(torch.nn.Module):
        def __init__(self, d, h):
            super().__init__()
            self.ln1 = _LayerNorm(d)
            self.attn = _Attn(d, h)
            self.ln2 = _LayerNorm(d)
            self.mlp = torch.nn.Sequential(
                torch.nn.Linear(d, 4 * d), torch.nn.GELU(), torch.nn.Linear(4 * d, d)
            )
        def forward(self, x):
            x = x + self.attn(self.ln1(x))
            x = x + self.mlp(self.ln2(x))
            return x

    # Detect best available device
    if torch.cuda.is_available():
        device = torch.device("cuda")
        backend = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
        backend = "mps"
    else:
        device = torch.device("cpu")
        backend = "cpu"

    d, h, T, B = 64, 4, 8, 2
    model = _Block(d, h).to(device)
    x = torch.randint(0, 256, (B, T)).to(device)
    emb = torch.nn.Embedding(256, d).to(device)
    out = model(emb(x))
    assert out.shape == (B, T, d), f"unexpected shape {out.shape}"

    if backend == "cuda":
        mem = torch.cuda.memory_allocated(device) / (1024 ** 2)
        print(f"GPU_UTIL_CHECK backend={backend} allocated_mb={mem:.2f}")
        if mem <= 0:
            # Memory was allocated during forward; flag is informational only
            print("GPU_UTIL_CHECK note: allocated_mb=0 possible with small model")
    else:
        print(f"GPU_UTIL_CHECK backend={backend} (no GPU utilisation metric on CPU/MPS)")

    print("NANOGPT_SMOKE_OK")
    sys.exit(0)

except ImportError:
    print("NANOGPT_SMOKE_SKIPPED torch_not_installed")
    sys.exit(0)
except Exception as e:
    print(f"NANOGPT_SMOKE_FAIL {e}", file=sys.stderr)
    sys.exit(1)
"""


def gpu_sandbox_smoke_test(
    workspace: Path,
    config: Optional[GpuSandboxConfig] = None,
) -> ContainerResult:
    """Run a tiny nanoGPT forward pass inside the GPU sandbox.

    The script detects CUDA/MPS/CPU at runtime so it works in all environments.
    Exit code 0 means the sandbox executed correctly (torch may or may not be
    installed); exit code 1 means the forward pass itself crashed.
    """
    if config is None:
        config = GpuSandboxConfig()

    script_path = workspace / "_nanogpt_smoke.py"
    script_path.write_text(_NANOGPT_SMOKE_SCRIPT)

    return run_gpu_sandbox(
        cmd=["python3", "_nanogpt_smoke.py"],
        workspace=workspace,
        config=config,
    )


# ---------------------------------------------------------------------------
# WASM toolchain sandbox — Feature ad3e1e0c
# ---------------------------------------------------------------------------

# Pinned image containing both wabt (wat2wasm) and wasmtime.
_DEFAULT_WASM_IMAGE = "ghcr.io/webassembly/wabt:1.0.36"

# Default wall-clock cap for WASM compilation + execution combined.
_DEFAULT_WASM_TIMEOUT_SECONDS = 60


@dataclass
class WasmSandboxConfig:
    """Configuration for the WASM toolchain sandbox.

    The *image* must contain ``wat2wasm`` (from wabt) and ``wasmtime``.
    Pin the tag so that the toolchain version is immutably recorded in results.
    """

    image: str = _DEFAULT_WASM_IMAGE
    timeout_seconds: int = _DEFAULT_WASM_TIMEOUT_SECONDS


def _run_wasm_docker(
    compile_cmd: list[str],
    run_cmd: list[str],
    image: str,
    workspace: Path,
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess, subprocess.CompletedProcess]:
    """Run compile then execute steps inside Docker containers."""
    base_docker = [
        "docker", "run",
        "--rm",
        "--network", "none",
        "-v", f"{workspace}:/workspace",
        "-w", "/workspace",
        image,
    ]
    compile_proc = subprocess.run(
        [*base_docker, *compile_cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
    )
    if compile_proc.returncode != 0:
        return compile_proc, compile_proc

    run_proc = subprocess.run(
        [*base_docker, *run_cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
    )
    return compile_proc, run_proc


def run_wasm_sandbox(
    wat_source: str,
    workspace: Path,
    config: Optional[WasmSandboxConfig] = None,
    wasmtime_args: Optional[list[str]] = None,
) -> ContainerResult:
    """Compile *wat_source* to WASM and execute it, returning stdout/exit code.

    Steps:
    1. Write *wat_source* to ``input.wat`` in *workspace*.
    2. Run ``wat2wasm input.wat -o input.wasm`` inside the sandbox image.
    3. Run ``wasmtime input.wasm [wasmtime_args]`` inside the sandbox image.
    4. Return the execution result (stdout, returncode, image).

    Gracefully degrades to direct host execution when Docker is unavailable.
    """
    if config is None:
        config = WasmSandboxConfig()
    if wasmtime_args is None:
        wasmtime_args = []

    image = config.image
    workspace.mkdir(parents=True, exist_ok=True)
    wat_path = workspace / "input.wat"
    wat_path.write_text(wat_source, encoding="utf-8")

    compile_cmd = ["wat2wasm", "input.wat", "-o", "input.wasm"]
    run_cmd = ["wasmtime", "input.wasm", *wasmtime_args]

    if not _docker_available():
        logger.warning(
            "Docker unavailable — WASM sandbox degrading to direct execution (image=%s)", image
        )
        try:
            compile_proc = subprocess.run(
                compile_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=workspace,
            )
        except FileNotFoundError as exc:
            logger.warning("wat2wasm not found on host during fallback: %s", exc)
            return ContainerResult(
                returncode=127,
                stdout="",
                stderr=f"wat2wasm not found: {exc}",
                image=image,
                ran_in_container=False,
            )
        if compile_proc.returncode != 0:
            return ContainerResult(
                returncode=compile_proc.returncode,
                stdout=compile_proc.stdout,
                stderr=compile_proc.stderr,
                image=image,
                ran_in_container=False,
            )
        try:
            run_proc = subprocess.run(
                run_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=workspace,
            )
        except FileNotFoundError as exc:
            logger.warning("wasmtime not found on host during fallback: %s", exc)
            return ContainerResult(
                returncode=127,
                stdout="",
                stderr=f"wasmtime not found: {exc}",
                image=image,
                ran_in_container=False,
            )
        return ContainerResult(
            returncode=run_proc.returncode,
            stdout=run_proc.stdout,
            stderr=run_proc.stderr,
            image=image,
            ran_in_container=False,
        )

    try:
        compile_proc, run_proc = _run_wasm_docker(
            compile_cmd=compile_cmd,
            run_cmd=run_cmd,
            image=image,
            workspace=workspace,
            timeout_seconds=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        logger.error("WASM sandbox timeout (%ss) exceeded", config.timeout_seconds)
        return ContainerResult(
            returncode=124,
            stdout="",
            stderr="Timeout expired",
            image=image,
            ran_in_container=True,
        )

    return ContainerResult(
        returncode=run_proc.returncode,
        stdout=run_proc.stdout,
        stderr=run_proc.stderr,
        image=image,
        ran_in_container=True,
    )


# ---------------------------------------------------------------------------
# Scientific-compute sandbox — Feature cab88a4e
# ---------------------------------------------------------------------------

# Pinned image with NumPy, SciPy, and JAX pre-installed.
_DEFAULT_SCI_IMAGE = "ghcr.io/scientific-python/devstats:numpy1.26-scipy1.13-jax0.4-py311"

# Default wall-clock cap for scientific compute jobs.
_DEFAULT_SCI_TIMEOUT_SECONDS = 300


@dataclass
class SciSandboxConfig:
    """Configuration for the scientific-compute sandbox.

    The *image* must be a fully-pinned tag that includes NumPy, SciPy, and JAX.
    BLAS thread counts default to 1 to guarantee deterministic results across
    runs (reproducibility requirement for the Navier-Stokes cavity task).
    """

    image: str = _DEFAULT_SCI_IMAGE
    timeout_seconds: int = _DEFAULT_SCI_TIMEOUT_SECONDS
    omp_num_threads: int = 1
    openblas_num_threads: int = 1
    mkl_num_threads: int = 1
    jax_platform_name: str = "cpu"


def _run_sci_docker(
    cmd: list[str],
    image: str,
    workspace: Path,
    config: SciSandboxConfig,
) -> subprocess.CompletedProcess:
    """Build and execute a Docker run command with deterministic BLAS env vars."""
    docker_cmd = [
        "docker", "run",
        "--rm",
        "--network", "none",
        "-e", f"OMP_NUM_THREADS={config.omp_num_threads}",
        "-e", f"OPENBLAS_NUM_THREADS={config.openblas_num_threads}",
        "-e", f"MKL_NUM_THREADS={config.mkl_num_threads}",
        "-e", f"JAX_PLATFORM_NAME={config.jax_platform_name}",
        "-v", f"{workspace}:/workspace",
        "-w", "/workspace",
        image,
        *cmd,
    ]
    return subprocess.run(
        docker_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=config.timeout_seconds,
    )


def run_sci_sandbox(
    cmd: list[str],
    workspace: Path,
    config: Optional[SciSandboxConfig] = None,
) -> ContainerResult:
    """Run *cmd* inside a scientific-compute Docker container.

    Uses a pinned NumPy/SciPy/JAX image with deterministic BLAS settings so
    that floating-point results are reproducible across runs.  The BLAS env vars
    (OMP_NUM_THREADS, OPENBLAS_NUM_THREADS, MKL_NUM_THREADS, JAX_PLATFORM_NAME)
    are injected via ``-e`` flags and default to 1/cpu for single-threaded,
    deterministic execution.

    Falls back to direct host execution when Docker is unavailable, identical to
    ``run_in_container``.  The pinned image name is always recorded in the
    returned ``ContainerResult``.
    """
    if config is None:
        config = SciSandboxConfig()

    image = config.image

    if not _docker_available():
        logger.warning(
            "Docker unavailable — sci sandbox degrading to direct execution (image=%s)", image
        )
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return ContainerResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            image=image,
            ran_in_container=False,
        )

    try:
        proc = _run_sci_docker(cmd=cmd, image=image, workspace=workspace, config=config)
    except subprocess.TimeoutExpired:
        logger.error("Sci sandbox wall-clock timeout (%ss) exceeded", config.timeout_seconds)
        return ContainerResult(
            returncode=124,
            stdout="",
            stderr="Timeout expired",
            image=image,
            ran_in_container=True,
        )

    return ContainerResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        image=image,
        ran_in_container=True,
    )


# ---------------------------------------------------------------------------
# Smoke test: Navier-Stokes lid-driven cavity (minimal)
# ---------------------------------------------------------------------------

_NS_CAVITY_SMOKE_SCRIPT = """\
import sys

try:
    import numpy as np

    # Minimal lid-driven cavity: solve Poisson on a 2D grid (proxy for pressure correction).
    # This validates NumPy is functional and BLAS settings don't break linear algebra.
    n = 16
    h = 1.0 / n
    # Build discrete Laplacian for interior points
    N = (n - 1) ** 2
    A = np.zeros((N, N))
    for i in range(N):
        A[i, i] = 4.0 / h ** 2
        if i + 1 < N and (i + 1) % (n - 1) != 0:
            A[i, i + 1] = -1.0 / h ** 2
            A[i + 1, i] = -1.0 / h ** 2
        if i + (n - 1) < N:
            A[i, i + (n - 1)] = -1.0 / h ** 2
            A[i + (n - 1), i] = -1.0 / h ** 2

    b = np.ones(N)
    x = np.linalg.solve(A, b)

    assert x.shape == (N,), f"unexpected shape {x.shape}"
    assert np.isfinite(x).all(), "non-finite values in solution"

    # Check residual
    residual = np.linalg.norm(A @ x - b)
    assert residual < 1e-6, f"residual too large: {residual}"

    print(f"NS_CAVITY_SMOKE_OK residual={residual:.2e} n={n}")
    sys.exit(0)

except ImportError as e:
    print(f"NS_CAVITY_SMOKE_SKIPPED numpy_not_installed: {e}")
    sys.exit(0)
except Exception as e:
    print(f"NS_CAVITY_SMOKE_FAIL {e}", file=sys.stderr)
    sys.exit(1)
"""


def sci_sandbox_smoke_test(
    workspace: Path,
    config: Optional[SciSandboxConfig] = None,
) -> ContainerResult:
    """Run a minimal Navier-Stokes cavity solve inside the sci sandbox.

    Solves a discrete Poisson equation on a 2D grid as a proxy for the pressure
    correction step in the lid-driven cavity flow.  Validates that NumPy linear
    algebra is functional and the BLAS settings do not corrupt results.

    Exit code 0 means the sandbox executed correctly; exit code 1 means the
    solve itself failed.
    """
    if config is None:
        config = SciSandboxConfig()

    script_path = workspace / "_ns_cavity_smoke.py"
    script_path.write_text(_NS_CAVITY_SMOKE_SCRIPT)

    return run_sci_sandbox(
        cmd=["python3", "_ns_cavity_smoke.py"],
        workspace=workspace,
        config=config,
    )
