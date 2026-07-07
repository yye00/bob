"""949b76df: Compile-cost build budgeting — ccache + local-GPU-arch scoping.

Problem
-------
BF-8's context-budget hook throttles the *LLM*, but on a C++/RCCL repo the
dominant cost of a verification pass is the C++/HIP **compile**, not the model.
A naive ``cmake`` configure links every default GPU arch (a fat binary) and can
take tens of minutes per verification; bob's whole-repo globbing then triggers
unnecessary cold rebuilds. Nothing in bob previously modelled compile
wall-clock, ccache, ninja target selection, or GPU-arch scoping.

Solution
--------
This module provides the canonical build-budget layer with three entry points:

* :func:`configure_ccache_ninja` — force a Ninja generator with
  ``CMAKE_CXX_COMPILER_LAUNCHER=ccache`` / ``CMAKE_HIP_COMPILER_LAUNCHER=ccache``
  and a warm, persistent ccache dir shared across features.
* :func:`scope_gpu_targets` — scope GPU codegen to the box's arch during
  iteration (``-DGPU_TARGETS=gfx942`` / ``gfx950`` or
  ``-DBUILD_LOCAL_GPU_TARGET_ONLY=ON``) instead of all-arch fat binaries.
* :func:`enforce_compile_budget` — record per-feature wall-clock and ccache
  hit-rate and enforce a real compile-time ceiling so one feature's
  verification cannot blow the generation's time budget on cold recompiles.

Integration
-----------
The orchestrator run-loop (:mod:`bob.orchestrator.run_loop`) calls these before
and after a CMake verification build.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

__all__ = [
    "CcacheNinjaConfig",
    "CompileBudgetResult",
    "CompileBudgetExceeded",
    "KNOWN_GPU_ARCHS",
    "DEFAULT_COMPILE_CEILING_S",
    "configure_ccache_ninja",
    "scope_gpu_targets",
    "enforce_compile_budget",
]

# AMD CDNA/GFX architectures we allow scoping to during local iteration.
KNOWN_GPU_ARCHS: frozenset[str] = frozenset(
    {"gfx906", "gfx908", "gfx90a", "gfx940", "gfx941", "gfx942", "gfx950"}
)

# Default per-feature compile wall-clock ceiling in seconds (20 min). Override
# via ``BOB_COMPILE_BUDGET_CEILING_S`` (clamped to [30, 7200]).
DEFAULT_COMPILE_CEILING_S: float = 1200.0

# Default persistent, cross-feature ccache directory. Shared so a warm cache
# built by one feature's verification speeds up the next feature's build.
_DEFAULT_CCACHE_DIR = "~/.cache/bob/ccache"
_DEFAULT_CCACHE_MAXSIZE = "20G"


@dataclass(frozen=True)
class CcacheNinjaConfig:
    """The CMake flags + environment needed for a ccache-warmed Ninja build."""

    cmake_flags: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    ccache_dir: str = ""


@dataclass(frozen=True)
class CompileBudgetResult:
    """Outcome of a per-feature compile-budget check."""

    within_budget: bool
    wall_clock_s: float
    ceiling_s: float
    overage_s: float
    ccache_hit_rate: float | None = None


class CompileBudgetExceeded(RuntimeError):
    """Raised by :func:`enforce_compile_budget` when ``raise_on_exceed`` is set
    and the recorded wall-clock exceeds the ceiling."""


def configure_ccache_ninja(
    ccache_dir: str | os.PathLike[str] | None = None,
    cmake_args: list[str] | None = None,
    *,
    max_size: str | None = None,
) -> CcacheNinjaConfig:
    """Build the CMake flags + env for a Ninja generator warmed by ccache.

    Forces ``-GNinja`` and wires ``CMAKE_CXX_COMPILER_LAUNCHER=ccache`` and
    ``CMAKE_HIP_COMPILER_LAUNCHER=ccache`` so both host-C++ and HIP device
    compiles hit the persistent cache. The ccache dir defaults to a shared,
    cross-feature location so a warm cache carries between verifications.

    Parameters
    ----------
    ccache_dir:
        Persistent ccache directory. ``None`` → shared default. A relative or
        ``~``-prefixed path is expanded to an absolute path.
    cmake_args:
        Existing CMake args to extend. ``None`` → start from an empty list.
        Any generator/launcher flags already present are not duplicated.
    max_size:
        ``CCACHE_MAXSIZE`` value (e.g. ``"20G"``). ``None`` → default.

    Returns
    -------
    CcacheNinjaConfig
        Frozen config with ``cmake_flags``, ``env`` and the resolved
        ``ccache_dir``.

    Raises
    ------
    ValueError
        If ``ccache_dir`` is not a str/PathLike (when provided), ``cmake_args``
        is not a list of str, or ``max_size`` is an empty/whitespace string.
    """
    if cmake_args is None:
        base_args: list[str] = []
    elif isinstance(cmake_args, list) and all(isinstance(a, str) for a in cmake_args):
        base_args = list(cmake_args)
    else:
        raise ValueError("cmake_args must be a list of str or None")

    if ccache_dir is None:
        resolved_dir = _DEFAULT_CCACHE_DIR
    elif isinstance(ccache_dir, (str, os.PathLike)):
        resolved_dir = os.fspath(ccache_dir)
        if not str(resolved_dir).strip():
            raise ValueError("ccache_dir must not be empty or whitespace")
    else:
        raise ValueError("ccache_dir must be a str, PathLike, or None")

    if max_size is None:
        resolved_max = _DEFAULT_CCACHE_MAXSIZE
    elif isinstance(max_size, str) and max_size.strip():
        resolved_max = max_size.strip()
    else:
        raise ValueError("max_size must be a non-empty str or None")

    abs_ccache_dir = str(pathlib.Path(resolved_dir).expanduser())

    launcher_flags = [
        "-GNinja",
        "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache",
        "-DCMAKE_HIP_COMPILER_LAUNCHER=ccache",
    ]
    cmake_flags = list(base_args)
    for flag in launcher_flags:
        if flag not in cmake_flags:
            cmake_flags.append(flag)

    env = {
        "CCACHE_DIR": abs_ccache_dir,
        "CCACHE_MAXSIZE": resolved_max,
        # A verification build never mutates sources between configure and build,
        # so content hashing is safe and lets the cache survive checkout churn.
        "CCACHE_COMPILERCHECK": "content",
    }
    return CcacheNinjaConfig(cmake_flags=cmake_flags, env=env, ccache_dir=abs_ccache_dir)


def scope_gpu_targets(
    arch: str | list[str] | None = None,
    *,
    local_only: bool = False,
) -> list[str]:
    """Scope GPU codegen to the local box's arch instead of an all-arch build.

    Parameters
    ----------
    arch:
        A single arch (``"gfx942"``), a list of archs, or ``None``. ``None``
        defaults to ``"gfx942"`` (unless ``local_only`` is set).
    local_only:
        When ``True``, emit ``-DBUILD_LOCAL_GPU_TARGET_ONLY=ON`` and let CMake
        auto-detect the installed device's arch; ``arch`` is ignored.

    Returns
    -------
    list[str]
        CMake flags scoping GPU codegen. Never empty.

    Raises
    ------
    ValueError
        If ``arch`` (or any element) is not a recognised gfx arch, is empty,
        or is not a str/list of str.
    """
    if local_only:
        return ["-DBUILD_LOCAL_GPU_TARGET_ONLY=ON"]

    if arch is None:
        archs = ["gfx942"]
    elif isinstance(arch, str):
        archs = [arch]
    elif isinstance(arch, list) and arch and all(isinstance(a, str) for a in arch):
        archs = list(arch)
    else:
        raise ValueError("arch must be a non-empty str, list of str, or None")

    normalized: list[str] = []
    for a in archs:
        token = a.strip()
        if not token:
            raise ValueError("arch entries must not be empty or whitespace")
        if token not in KNOWN_GPU_ARCHS:
            raise ValueError(
                f"unknown GPU arch {token!r}; known: {sorted(KNOWN_GPU_ARCHS)}"
            )
        normalized.append(token)

    return [f"-DGPU_TARGETS={';'.join(normalized)}"]


def _resolve_ceiling(ceiling_s: float | None) -> float:
    if ceiling_s is None:
        raw = os.environ.get("BOB_COMPILE_BUDGET_CEILING_S")
        if raw is not None and raw.strip():
            try:
                ceiling_s = float(raw)
            except ValueError:
                ceiling_s = DEFAULT_COMPILE_CEILING_S
        else:
            ceiling_s = DEFAULT_COMPILE_CEILING_S
    if isinstance(ceiling_s, bool) or not isinstance(ceiling_s, (int, float)):
        raise ValueError("ceiling_s must be a number or None")
    if ceiling_s <= 0:
        raise ValueError("ceiling_s must be positive")
    # Clamp to a sane range regardless of source.
    return float(max(30.0, min(7200.0, ceiling_s)))


def enforce_compile_budget(
    wall_clock_s: float,
    ceiling_s: float | None = None,
    *,
    ccache_hit_rate: float | None = None,
    raise_on_exceed: bool = False,
) -> CompileBudgetResult:
    """Record per-feature compile wall-clock and enforce a compile-time ceiling.

    Parameters
    ----------
    wall_clock_s:
        Measured compile wall-clock, in seconds. Must be a non-negative number.
    ceiling_s:
        The compile-time ceiling in seconds. ``None`` → resolve from
        ``BOB_COMPILE_BUDGET_CEILING_S`` or :data:`DEFAULT_COMPILE_CEILING_S`.
    ccache_hit_rate:
        Optional cache hit-rate in ``[0.0, 1.0]`` for telemetry.
    raise_on_exceed:
        When ``True`` and the wall-clock exceeds the ceiling, raise
        :class:`CompileBudgetExceeded` instead of returning a result with
        ``within_budget=False``.

    Returns
    -------
    CompileBudgetResult
        Result carrying ``within_budget``, the measured/ceiling wall-clock, the
        ``overage_s`` (0.0 when within budget), and the hit-rate.

    Raises
    ------
    ValueError
        If ``wall_clock_s`` is not a non-negative number, ``ceiling_s`` is
        non-positive, or ``ccache_hit_rate`` is outside ``[0.0, 1.0]``.
    CompileBudgetExceeded
        If over budget and ``raise_on_exceed`` is set.
    """
    if isinstance(wall_clock_s, bool) or not isinstance(wall_clock_s, (int, float)):
        raise ValueError("wall_clock_s must be a number")
    if wall_clock_s < 0:
        raise ValueError("wall_clock_s must be non-negative")

    resolved_ceiling = _resolve_ceiling(ceiling_s)

    if ccache_hit_rate is not None:
        if isinstance(ccache_hit_rate, bool) or not isinstance(
            ccache_hit_rate, (int, float)
        ):
            raise ValueError("ccache_hit_rate must be a number in [0.0, 1.0] or None")
        if not (0.0 <= ccache_hit_rate <= 1.0):
            raise ValueError("ccache_hit_rate must be within [0.0, 1.0]")
        ccache_hit_rate = float(ccache_hit_rate)

    wall = float(wall_clock_s)
    within = wall <= resolved_ceiling
    overage = 0.0 if within else wall - resolved_ceiling

    if not within and raise_on_exceed:
        raise CompileBudgetExceeded(
            f"compile wall-clock {wall:.1f}s exceeds ceiling "
            f"{resolved_ceiling:.1f}s by {overage:.1f}s"
        )

    return CompileBudgetResult(
        within_budget=within,
        wall_clock_s=wall,
        ceiling_s=resolved_ceiling,
        overage_s=overage,
        ccache_hit_rate=ccache_hit_rate,
    )
