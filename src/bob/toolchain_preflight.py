"""ROCm/HIP toolchain preflight with version and arch pinning.

The existing env preflight (:mod:`bob.orchestrator.env_preflight`) enumerates
dependencies as bare CLI names probed with ``shutil.which`` and Python modules
probed with ``import X``.  It has *zero* version awareness and no HIP/ROCm
concept.

Building RCCL from the rocm-systems monorepo needs a *specific, compatible*
toolchain: ``hipcc``/``amdclang++``, a minimum ``cmake``, a pinned ROCm release,
``rocminfo``/``rocm_agent_enumerator``, and matching hip/hsa runtime libs.  A
build against the wrong ROCm or a mismatched GPU arch fails cryptically after a
long compile.

This module adds the ROCm analog of the CLI/Python dep enumeration, with the
version/arch dimension HIP builds fundamentally need:

1. :func:`parse_toolchain_pins` extracts version/arch pins from a PEAS CONTEXT
   block (e.g. ``"ROCm 7.2.1"``, ``"gfx942"``, ``"cmake 3.25"``).
2. :func:`check_toolchain_preflight` probes real versions via ``hipcc
   --version``, ``cmake --version``, ``cat /opt/rocm/.info/version`` and
   ``rocminfo``, compares them semver-style against the pin, and HALTS with an
   operator-actionable message on mismatch instead of proceeding to a build
   that fails cryptically or links the wrong ROCm.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "ToolchainPins",
    "ToolProbe",
    "ToolchainPreflightResult",
    "ToolchainPreflightError",
    "parse_toolchain_pins",
    "check_toolchain_preflight",
    "parse_semver",
    "compare_semver",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolchainPreflightError(ValueError):
    """Raised on invalid input to the toolchain-preflight functions.

    Subclasses :class:`ValueError` so callers already catching ``ValueError``
    for malformed specs continue to work.
    """


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ToolchainPins:
    """Version/arch pins parsed from a PEAS CONTEXT block.

    Every field is optional: a spec may pin ROCm but not cmake, or pin an arch
    but no versions at all.  An all-``None`` instance means "no pins declared"
    and preflight should pass trivially.
    """

    rocm: Optional[str] = None  # e.g. "7.2.1"
    cmake: Optional[str] = None  # minimum cmake, e.g. "3.25"
    hip: Optional[str] = None  # e.g. "7.2"
    archs: List[str] = field(default_factory=list)  # e.g. ["gfx942"]

    def is_empty(self) -> bool:
        return not (self.rocm or self.cmake or self.hip or self.archs)


@dataclass
class ToolProbe:
    """Result of probing a single tool for presence and version."""

    name: str
    present: bool
    version: Optional[str] = None  # parsed version string, e.g. "7.2.1"
    raw: Optional[str] = None  # raw probe output (first line)
    path: Optional[str] = None  # resolved CLI path


@dataclass
class ToolchainPreflightResult:
    """Outcome of :func:`check_toolchain_preflight`.

    ``ok`` is True when every declared pin is satisfied.  ``mismatches`` holds
    operator-actionable strings naming exactly what is wrong (missing tool,
    version too low, arch not present).  ``probes`` records what was found for
    each tool so callers can log or persist.
    """

    ok: bool
    pins: ToolchainPins
    probes: List[ToolProbe] = field(default_factory=list)
    mismatches: List[str] = field(default_factory=list)

    def halt_message(self) -> str:
        """Return a single operator-actionable message, or '' when ok."""
        if self.ok:
            return ""
        return "ROCm/HIP toolchain preflight FAILED:\n  - " + "\n  - ".join(
            self.mismatches
        )


# ---------------------------------------------------------------------------
# Semver helpers
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_GFX_RE = re.compile(r"\bgfx[0-9a-fA-F]+\b", re.IGNORECASE)


def parse_semver(text: str) -> Tuple[int, int, int]:
    """Extract the first ``MAJOR[.MINOR[.PATCH]]`` triple from *text*.

    Missing minor/patch components default to 0, so ``"3.25"`` -> ``(3, 25, 0)``
    and ``"7"`` -> ``(7, 0, 0)``.

    Raises:
        ToolchainPreflightError: if *text* is not a string or contains no
            numeric version at all.
    """
    if not isinstance(text, str):
        raise ToolchainPreflightError(
            f"version text must be a string, got {type(text).__name__}"
        )
    match = _SEMVER_RE.search(text)
    if match is None:
        raise ToolchainPreflightError(
            f"no numeric version found in {text!r}"
        )
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) is not None else 0
    patch = int(match.group(3)) if match.group(3) is not None else 0
    return (major, minor, patch)


def compare_semver(found: str, pin: str) -> int:
    """Compare *found* against *pin* semver-style.

    Returns -1 if found < pin, 0 if equal, +1 if found > pin.  Only the
    components present in *pin* are compared, so a pin of ``"3.25"`` treats
    ``"3.25.7"`` as equal (>= satisfied).

    Raises:
        ToolchainPreflightError: if either argument has no numeric version.
    """
    found_t = parse_semver(found)
    pin_match = _SEMVER_RE.search(pin) if isinstance(pin, str) else None
    if pin_match is None:
        raise ToolchainPreflightError(f"no numeric version found in pin {pin!r}")
    # Determine how many components the pin actually specified.
    ncomp = 1 + sum(1 for g in (pin_match.group(2), pin_match.group(3)) if g is not None)
    pin_t = parse_semver(pin)
    for i in range(ncomp):
        if found_t[i] < pin_t[i]:
            return -1
        if found_t[i] > pin_t[i]:
            return 1
    return 0


# ---------------------------------------------------------------------------
# Pin parsing
# ---------------------------------------------------------------------------

_ROCM_RE = re.compile(r"\bROCm[\s:=v]*([0-9]+(?:\.[0-9]+){0,2})", re.IGNORECASE)
_CMAKE_RE = re.compile(r"\bcmake[\s:=>v]*([0-9]+(?:\.[0-9]+){0,2})", re.IGNORECASE)
_HIP_RE = re.compile(r"\bHIP[\s:=v]*([0-9]+(?:\.[0-9]+){0,2})", re.IGNORECASE)


def parse_toolchain_pins(context: Optional[str]) -> ToolchainPins:
    """Parse ROCm/HIP/cmake/arch pins from a PEAS CONTEXT block string.

    Recognises patterns like ``"ROCm 7.2.1"``, ``"ROCm: 7.2"``, ``"cmake
    >=3.25"``, ``"HIP 7.2"`` and any ``gfxNNN`` architecture token.

    A ``None`` or empty/whitespace *context* is a valid boundary case: it
    returns an empty :class:`ToolchainPins` (no pins), NOT an error — a spec
    with no CONTEXT block simply pins nothing.

    Raises:
        ToolchainPreflightError: if *context* is a non-string, non-None value.
    """
    if context is None:
        return ToolchainPins()
    if not isinstance(context, str):
        raise ToolchainPreflightError(
            f"context must be a string or None, got {type(context).__name__}"
        )
    if not context.strip():
        return ToolchainPins()

    pins = ToolchainPins()

    m = _ROCM_RE.search(context)
    if m:
        pins.rocm = m.group(1)
    m = _CMAKE_RE.search(context)
    if m:
        pins.cmake = m.group(1)
    m = _HIP_RE.search(context)
    if m:
        pins.hip = m.group(1)

    seen: set[str] = set()
    for arch in _GFX_RE.findall(context):
        low = arch.lower()
        if low not in seen:
            seen.add(low)
            pins.archs.append(low)

    return pins


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------


def _run(cmd: Sequence[str]) -> Optional[str]:
    """Run *cmd*, return combined stdout+stderr, or None on failure/missing."""
    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = (proc.stdout or "") + (proc.stderr or "")
    return out if out.strip() else (out or "")


def _probe_versioned_cli(name: str, version_arg: str = "--version") -> ToolProbe:
    """Probe a CLI for presence + version via ``<name> <version_arg>``."""
    path = shutil.which(name)
    if path is None:
        return ToolProbe(name=name, present=False)
    out = _run([name, version_arg])
    version = None
    raw = None
    if out:
        raw = out.splitlines()[0] if out.splitlines() else out.strip()
        m = _SEMVER_RE.search(out)
        if m:
            version = m.group(0)
    return ToolProbe(name=name, present=True, version=version, raw=raw, path=path)


def _probe_rocm_version(read_file: Callable[[str], Optional[str]]) -> ToolProbe:
    """Probe the installed ROCm release via /opt/rocm/.info/version."""
    content = read_file("/opt/rocm/.info/version")
    if content is None:
        return ToolProbe(name="rocm", present=False)
    raw = content.strip().splitlines()[0] if content.strip() else content.strip()
    version = None
    m = _SEMVER_RE.search(content)
    if m:
        version = m.group(0)
    return ToolProbe(name="rocm", present=True, version=version, raw=raw)


def _probe_gpu_archs() -> Tuple[bool, List[str]]:
    """Probe available GPU archs via rocminfo. Returns (probed_ok, archs)."""
    out = _run(["rocminfo"])
    if out is None:
        return (False, [])
    archs = sorted({a.lower() for a in _GFX_RE.findall(out)})
    return (True, archs)


def _default_read_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------


def check_toolchain_preflight(
    context: Optional[str] = None,
    *,
    pins: Optional[ToolchainPins] = None,
    halt: bool = False,
    read_file: Optional[Callable[[str], Optional[str]]] = None,
    probe_archs: Optional[Callable[[], Tuple[bool, List[str]]]] = None,
) -> ToolchainPreflightResult:
    """Run the ROCm/HIP toolchain preflight.

    Parses pins from *context* (or takes an explicit *pins*), probes the real
    toolchain, and compares semver-style.  Returns a
    :class:`ToolchainPreflightResult`.

    Boundary case: with no pins declared (``context=None`` / empty, and no
    *pins*), returns ``ok=True`` with no mismatches — a well-defined result,
    never an exception.

    Args:
        context: PEAS CONTEXT block text to parse pins from.
        pins: Pre-parsed pins; overrides *context* when given.
        halt: When True and preflight fails, raise
            :class:`ToolchainPreflightError` with the halt message instead of
            returning a failing result.
        read_file: Injectable file reader (defaults to real filesystem) — used
            to read ``/opt/rocm/.info/version``; makes the function testable.
        probe_archs: Injectable arch prober (defaults to ``rocminfo``).

    Raises:
        ToolchainPreflightError: on invalid *pins* type, or (when ``halt=True``)
            when the preflight fails.
    """
    if pins is None:
        pins = parse_toolchain_pins(context)
    elif not isinstance(pins, ToolchainPins):
        raise ToolchainPreflightError(
            f"pins must be a ToolchainPins or None, got {type(pins).__name__}"
        )

    if read_file is None:
        read_file = _default_read_file
    if probe_archs is None:
        probe_archs = _probe_gpu_archs

    probes: List[ToolProbe] = []
    mismatches: List[str] = []

    # Boundary: nothing pinned -> trivially OK.
    if pins.is_empty():
        return ToolchainPreflightResult(ok=True, pins=pins, probes=probes, mismatches=[])

    # ROCm release pin.
    if pins.rocm:
        rocm_probe = _probe_rocm_version(read_file)
        probes.append(rocm_probe)
        if not rocm_probe.present:
            mismatches.append(
                f"ROCm {pins.rocm} required but no ROCm install found at "
                f"/opt/rocm/.info/version. Install ROCm {pins.rocm} or set "
                f"the correct ROCM_PATH."
            )
        elif rocm_probe.version is None:
            mismatches.append(
                f"ROCm {pins.rocm} required but installed version is "
                f"unparseable (raw: {rocm_probe.raw!r})."
            )
        elif compare_semver(rocm_probe.version, pins.rocm) != 0:
            mismatches.append(
                f"ROCm version mismatch: pin requires {pins.rocm}, found "
                f"{rocm_probe.version}. RCCL must link against the pinned ROCm; "
                f"install ROCm {pins.rocm}."
            )

    # hipcc (HIP compiler) presence + optional HIP version pin.
    if pins.rocm or pins.hip:
        hipcc = _probe_versioned_cli("hipcc")
        probes.append(hipcc)
        if not hipcc.present:
            mismatches.append(
                "hipcc (HIP compiler) not found on PATH. Install the ROCm "
                "HIP toolchain (hipcc/amdclang++) and re-source the ROCm env."
            )
        elif pins.hip and hipcc.version is not None:
            if compare_semver(hipcc.version, pins.hip) < 0:
                mismatches.append(
                    f"HIP compiler too old: pin requires >= {pins.hip}, "
                    f"hipcc reports {hipcc.version}."
                )

    # cmake minimum-version pin.
    if pins.cmake:
        cmake = _probe_versioned_cli("cmake")
        probes.append(cmake)
        if not cmake.present:
            mismatches.append(
                f"cmake >= {pins.cmake} required but cmake not found on PATH."
            )
        elif cmake.version is None:
            mismatches.append(
                f"cmake >= {pins.cmake} required but version unparseable "
                f"(raw: {cmake.raw!r})."
            )
        elif compare_semver(cmake.version, pins.cmake) < 0:
            mismatches.append(
                f"cmake too old: pin requires >= {pins.cmake}, found "
                f"{cmake.version}. Upgrade cmake."
            )

    # GPU arch pin (rocminfo).
    if pins.archs:
        probed_ok, available = probe_archs()
        arch_probe = ToolProbe(
            name="gpu-arch",
            present=probed_ok,
            raw=",".join(available) if available else None,
        )
        probes.append(arch_probe)
        if not probed_ok:
            mismatches.append(
                f"GPU arch pin {pins.archs} declared but rocminfo could not "
                f"enumerate any GPU (rocminfo missing or no device). An "
                f"arch-mismatched build would fail after a long compile."
            )
        else:
            available_set = set(available)
            for want in pins.archs:
                if want not in available_set:
                    mismatches.append(
                        f"Target arch {want} (--offload-arch={want}) not "
                        f"present on this host. rocminfo reports: "
                        f"{sorted(available_set) or 'none'}. Build on a "
                        f"{want} host or adjust GPU_TARGETS."
                    )

    ok = not mismatches
    result = ToolchainPreflightResult(
        ok=ok, pins=pins, probes=probes, mismatches=mismatches
    )

    if halt and not ok:
        raise ToolchainPreflightError(result.halt_message())

    return result
