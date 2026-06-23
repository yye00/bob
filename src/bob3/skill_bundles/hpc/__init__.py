"""HPC skill bundle: OpenMP, MPI, CUDA, ROCm/HIP, and SIMD skill files.

Activated when the feature spec sets ``domain=hpc`` or when the compile
target includes any of ``{nvcc, hipcc, mpicc}``.  Skill markdown files are
injected into sub-agent context only when activated.

Public API:
    HPC_SKILL_FILES   - Ordered list of markdown skill filenames.
    HPC_COMPILE_TRIGGERS - Compile-target strings that activate HPC.
    is_hpc_spec(spec) -> bool
    load_hpc_skills() -> dict[str, str]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent

#: Ordered list of HPC skill markdown filenames.
HPC_SKILL_FILES: list[str] = [
    "openmp.md",
    "mpi.md",
    "cuda.md",
    "rocm.md",
    "simd.md",
]

#: Compile-target strings that trigger HPC bundle activation.
HPC_COMPILE_TRIGGERS: frozenset[str] = frozenset({"nvcc", "hipcc", "mpicc"})


def is_hpc_spec(spec: dict[str, Any] | None) -> bool:
    """Return True when *spec* should activate the HPC skill bundle.

    Activation rules (any one sufficient):
    - ``spec["domain"] == "hpc"``
    - ``spec["metadata"]["domain"] == "hpc"``
    - ``spec["compile_target"]`` is a string or list that contains one of
      ``nvcc``, ``hipcc``, or ``mpicc``.

    Args:
        spec: Parsed feature spec dict, or None.

    Returns:
        True when the HPC bundle should be activated, False otherwise.
    """
    if not spec:
        return False

    # Check top-level domain key.
    raw_domain: Any = spec.get("domain")
    if raw_domain is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, dict):
            raw_domain = metadata.get("domain")

    if isinstance(raw_domain, str) and raw_domain.strip().lower() == "hpc":
        return True

    # Check compile_target for HPC compiler names.
    compile_target: Any = spec.get("compile_target")
    if compile_target is None:
        return False

    if isinstance(compile_target, str):
        targets: list[str] = [compile_target]
    elif isinstance(compile_target, (list, tuple)):
        targets = list(compile_target)
    else:
        return False

    return any(str(t).strip().lower() in HPC_COMPILE_TRIGGERS for t in targets)


def load_hpc_skills() -> dict[str, str]:
    """Load all HPC skill markdown files and return filename → content mapping.

    Returns:
        Dict mapping each filename in :data:`HPC_SKILL_FILES` to its text content.

    Raises:
        FileNotFoundError: If any expected skill file is missing from the package.
    """
    result: dict[str, str] = {}
    for filename in HPC_SKILL_FILES:
        path = _HERE / filename
        result[filename] = path.read_text(encoding="utf-8")
    return result
