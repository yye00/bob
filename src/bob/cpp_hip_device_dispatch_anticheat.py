"""C++/HIP device-dispatch anti-cheat — source + compiled-binary evidence.

Feature 2449179e-2def-4769-ad3d-53912854b478.

bob's existing GPU anti-cheat suite (``no_simulation_in_source`` /
``hip_backend_required`` / ``gpu_execution_proven``) lives inside a
``if _gpu_backend_required and is_python_project:`` block in
:mod:`bob.superpowers` and only scans ``.py`` text with Python regexes.  The
C++ branch has NO dispatch check at all, so the "host-not-GPU" cheat already
observed in the Python (hippy) path is fully reproducible in C++ — a host-side
``std::accumulate`` loop dressed up as a collective, a CPU-only binary that
merely ``#include``\\s ``rccl.h``, etc.

This module ports the Python ``_sim_markers`` / ``_real_call_re`` design to a
C++/HIP token grammar and adds compiled-binary inspection:

1. :func:`scan_cpp_device_dispatch` — scans a feature's own ``.cpp`` / ``.hip``
   / ``.cu`` / ``.cc`` / ``.cxx`` sources for GENUINE device dispatch:
   ``__global__`` kernel definitions plus real launch sites
   (``hipLaunchKernelGGL(``, ``<<<...>>>``, ``hipModuleLaunchKernel(``) or
   genuine RCCL collective calls (``ncclAllReduce(``, ``ncclCommInitRank(``,
   ...) — not just ``#include``\\s or comments — and flags host-simulation
   markers (``// simulate on host``, ``CPU fallback``, host reductions where a
   collective is claimed).

2. :func:`verify_compiled_device_evidence` — verifies the COMPILED artifact
   actually contains device code / RCCL symbols by inspecting the output of a
   binary-inspection tool (``roc-obj`` / ``llvm-objdump -d`` / ``readelf`` /
   ``nm -D … | grep …``) or an embedded ``.hip`` fatbin section, so a CPU-only
   binary that merely links against or ``#include``\\s ``rccl.h`` is rejected.

Both functions return well-defined dataclass results for empty / minimal input
(never raise on the empty case) and raise :class:`ValueError` on structurally
invalid input (wrong types, negative counts, ...) so a caller cannot silently
succeed with garbage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

__all__ = [
    "scan_cpp_device_dispatch",
    "verify_compiled_device_evidence",
    "DispatchScanResult",
    "CompiledEvidenceResult",
    "CPP_SOURCE_SUFFIXES",
    "SIM_MARKERS",
]

# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

#: Source suffixes that hold C++/HIP/CUDA device code for a feature.
CPP_SOURCE_SUFFIXES: tuple[str, ...] = (
    ".cpp", ".cc", ".cxx", ".c++", ".hip", ".cu", ".cuh", ".hpp", ".h", ".hh",
)

#: Lower-cased substrings that betray a host-side simulation masquerading as
#: real device work — the C++ analog of the Python ``_sim_markers`` set.
SIM_MARKERS: tuple[str, ...] = (
    "simulate on host", "simulate on cpu", "simulated on host",
    "host simulation", "host-side simulation", "cpu simulation",
    "cpu fallback", "fall back to cpu", "fallback to cpu",
    "host fallback", "no gpu", "no real device", "no actual device",
    "pretend", "fake gpu", "fake device", "mock gpu", "mock device",
    "emulate the collective", "emulate collective", "emulation of",
    "std::accumulate", "host reduction", "host-side reduction",
    "on a real gpu", "on a live gpu", "in a real implementation",
    "would launch a kernel", "would dispatch", "not actually on the gpu",
    "cpu-only", "cpu only implementation", "single-process fake",
    "simulated collective", "simulate the collective",
)

# A genuine device dispatch: a ``__global__`` kernel DEFINITION.
_KERNEL_DEF_RE = re.compile(r"\b__global__\b")

# Real launch sites — actually invoking a kernel / device entry point.
_LAUNCH_SITE_RE = re.compile(
    r"hipLaunchKernelGGL\s*\(|"
    r"hipModuleLaunchKernel\s*\(|"
    r"cudaLaunchKernel\s*\(|"
    r"<<<[^>]*>>>"  # triple-chevron launch syntax
)

# Genuine RCCL / NCCL collective + communicator calls (not just includes).
_RCCL_CALL_RE = re.compile(
    r"nccl(AllReduce|Broadcast|Reduce|AllGather|ReduceScatter|Send|Recv|"
    r"CommInitRank|CommInitAll|CommDestroy|GroupStart|GroupEnd)\s*\("
)

# Comment stripper — device tokens inside comments must NOT count as dispatch.
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(text: str) -> str:
    """Remove C/C++ line and block comments so tokens inside them don't count."""
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    text = _LINE_COMMENT_RE.sub(" ", text)
    return text


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class DispatchScanResult:
    """Outcome of scanning C++/HIP sources for genuine device dispatch."""

    has_device_dispatch: bool = False
    has_kernel_def: bool = False
    has_launch_site: bool = False
    has_rccl_call: bool = False
    sim_marker: str | None = None
    files_scanned: int = 0
    evidence: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when real dispatch is present AND no simulation marker was hit."""
        return self.has_device_dispatch and self.sim_marker is None

    @property
    def details(self) -> str:
        if self.files_scanned == 0:
            return "No C++/HIP source files to scan"
        if self.sim_marker is not None:
            return (
                f"Host SIMULATION marker detected ({self.sim_marker}). A CPU "
                "loop dressed as a collective/kernel is not acceptable — "
                "implement real device dispatch (__global__ kernel + launch "
                "site, or a genuine ncclAllReduce()/ncclCommInitRank() call)."
            )
        if self.has_device_dispatch:
            return "Genuine C++/HIP device dispatch detected: " + ", ".join(
                self.evidence
            )
        return (
            f"Scanned {self.files_scanned} C++/HIP source file(s) but found NO "
            "device dispatch. A __global__ kernel plus a launch site "
            "(hipLaunchKernelGGL(), <<<>>>, hipModuleLaunchKernel()) or a real "
            "RCCL collective call (ncclAllReduce(), ncclCommInitRank()) is "
            "required — an #include of rccl.h/hip_runtime.h is NOT enough."
        )


@dataclass
class CompiledEvidenceResult:
    """Outcome of inspecting a compiled artifact for device / RCCL evidence."""

    has_device_code: bool = False
    has_rccl_symbol: bool = False
    matched_symbols: list[str] = field(default_factory=list)
    inspected: bool = False

    @property
    def passed(self) -> bool:
        return self.inspected and (self.has_device_code or self.has_rccl_symbol)

    @property
    def details(self) -> str:
        if not self.inspected:
            return "No binary-inspection output supplied — nothing verified"
        if self.passed:
            return "Compiled artifact contains device/RCCL evidence: " + ", ".join(
                self.matched_symbols
            )
        return (
            "Compiled artifact contains NO device code or RCCL symbols. A "
            "CPU-only binary that merely #includes/links rccl.h is rejected — "
            "the binary must carry AMDGPU device code (__amdgpu_ / .hip_fatbin) "
            "or defined RCCL symbols (ncclAllReduce, ...)."
        )


# Tokens that prove device code / RCCL symbols in binary-inspection output.
_DEVICE_CODE_TOKENS: tuple[str, ...] = (
    "__amdgpu_", "amdgpu", ".hip_fatbin", "__hip_fatbin", "__CLANG_OFFLOAD_BUNDLE",
    "clang_offload_bundle", "__cuda_fatbin", ".nv_fatbin", "kernel_metadata",
    "amdhsa.kernels", "gfx",
)
_RCCL_SYMBOL_TOKENS: tuple[str, ...] = (
    "ncclallreduce", "ncclbroadcast", "ncclreduce", "ncclallgather",
    "ncclreducescatter", "ncclcomminitrank", "ncclcomminitall", "ncclsend",
    "ncclrecv", "ncclgroupstart", "ncclgroupend", "rccl",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_cpp_device_dispatch(
    sources: Mapping[str, str] | Iterable[tuple[str, str]],
) -> DispatchScanResult:
    """Scan C++/HIP/CUDA source text for genuine device dispatch.

    Parameters
    ----------
    sources:
        Either a mapping of ``{path: source_text}`` or an iterable of
        ``(path, source_text)`` pairs.  Only files whose suffix is in
        :data:`CPP_SOURCE_SUFFIXES` are scanned; other paths are ignored.

    Returns
    -------
    DispatchScanResult
        For empty input, a result with ``files_scanned == 0`` and
        ``passed is False`` (well-defined, does not raise).

    Raises
    ------
    ValueError
        If *sources* is None, not a mapping/iterable of pairs, or if any key is
        not a string or any value is not a string.
    """
    if sources is None:
        raise ValueError("scan_cpp_device_dispatch: sources must not be None")
    if isinstance(sources, (str, bytes)):
        raise ValueError(
            "scan_cpp_device_dispatch: sources must be a mapping or iterable of "
            f"(path, text) pairs, not {type(sources).__name__}"
        )

    if isinstance(sources, Mapping):
        items = list(sources.items())
    else:
        try:
            items = [tuple(pair) for pair in sources]
        except TypeError as exc:
            raise ValueError(
                "scan_cpp_device_dispatch: sources must be a mapping or iterable "
                "of (path, text) pairs"
            ) from exc

    result = DispatchScanResult()
    for pair in items:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(
                "scan_cpp_device_dispatch: each source entry must be a "
                "(path, text) pair"
            )
        path, text = pair
        if not isinstance(path, str):
            raise ValueError(
                f"scan_cpp_device_dispatch: source path must be a str, got "
                f"{type(path).__name__}"
            )
        if not isinstance(text, str):
            raise ValueError(
                f"scan_cpp_device_dispatch: source text for {path!r} must be a "
                f"str, got {type(text).__name__}"
            )

        if not any(path.lower().endswith(sfx) for sfx in CPP_SOURCE_SUFFIXES):
            continue

        result.files_scanned += 1

        # Simulation markers are scanned on the RAW text (including comments):
        # a "// simulate on host" admission is a tell regardless of location.
        low = text.lower()
        if result.sim_marker is None:
            for marker in SIM_MARKERS:
                if marker in low:
                    result.sim_marker = f"{path}: {marker!r}"
                    break

        # Dispatch tokens must appear in CODE, not comments.
        code = _strip_comments(text)
        if _KERNEL_DEF_RE.search(code):
            result.has_kernel_def = True
        if _LAUNCH_SITE_RE.search(code):
            result.has_launch_site = True
        if _RCCL_CALL_RE.search(code):
            result.has_rccl_call = True

    # Genuine dispatch = a real launch site (which implies a kernel somewhere),
    # OR a genuine RCCL collective/communicator call.  A __global__ definition
    # WITHOUT any launch site is not dispatch (it is a defined-but-never-run
    # kernel), so it does not by itself satisfy the check.
    if result.has_launch_site:
        result.evidence.append("kernel launch site")
    if result.has_kernel_def:
        result.evidence.append("__global__ kernel definition")
    if result.has_rccl_call:
        result.evidence.append("RCCL collective/communicator call")

    result.has_device_dispatch = result.has_launch_site or result.has_rccl_call
    return result


def verify_compiled_device_evidence(
    inspection_output: str,
    *,
    tool: str = "nm",
) -> CompiledEvidenceResult:
    """Verify a compiled artifact contains device code / RCCL symbols.

    The caller runs a binary-inspection tool (``roc-obj``, ``llvm-objdump -d``,
    ``readelf -a``, ``nm -D build/…``) and passes its captured stdout here.
    This function looks for device-code section/symbol tells
    (``__amdgpu_``, ``.hip_fatbin``, offload-bundle markers, ``gfx…``) and
    defined RCCL symbols (``ncclAllReduce``, ...).

    A CPU-only binary that merely ``#include``\\s / links ``rccl.h`` produces
    output with no such tokens and is rejected.

    Parameters
    ----------
    inspection_output:
        Captured stdout of the binary-inspection tool.  An empty string is a
        well-defined "nothing to verify" case (``passed is False``), not an
        error.
    tool:
        Name of the inspection tool used (recorded for diagnostics).

    Raises
    ------
    ValueError
        If *inspection_output* is not a string, or *tool* is not a non-empty
        string.
    """
    if not isinstance(inspection_output, str):
        raise ValueError(
            "verify_compiled_device_evidence: inspection_output must be a str, "
            f"got {type(inspection_output).__name__}"
        )
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError(
            "verify_compiled_device_evidence: tool must be a non-empty str"
        )

    result = CompiledEvidenceResult()
    if inspection_output.strip() == "":
        # Empty output: inspected nothing — well-defined non-pass, no raise.
        return result

    result.inspected = True
    low = inspection_output.lower()

    for token in _DEVICE_CODE_TOKENS:
        if token.lower() in low:
            result.has_device_code = True
            result.matched_symbols.append(token)
    for token in _RCCL_SYMBOL_TOKENS:
        if token in low:
            result.has_rccl_symbol = True
            result.matched_symbols.append(token)

    return result
