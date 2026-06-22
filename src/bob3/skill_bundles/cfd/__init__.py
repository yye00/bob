"""CFD skill bundle: FVM/FEM, SIMPLE/PISO, turbulence models, boundary conditions.

Activated when the feature spec sets ``domain=cfd``.  Skill markdown files are
injected into sub-agent context only when activated.

Public API:
    CFD_SKILL_FILES     - Ordered list of markdown skill filenames.
    is_cfd_spec(spec) -> bool
    load_cfd_skills() -> dict[str, str]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent

#: Ordered list of CFD skill markdown filenames.
CFD_SKILL_FILES: list[str] = [
    "fvm_fem.md",
    "simple_piso.md",
    "turbulence.md",
    "boundary_conditions.md",
]


def is_cfd_spec(spec: dict[str, Any] | None) -> bool:
    """Return True when *spec* should activate the CFD skill bundle.

    Activation rules (any one sufficient):
    - ``spec["domain"] == "cfd"``
    - ``spec["metadata"]["domain"] == "cfd"``

    Args:
        spec: Parsed feature spec dict, or None.

    Returns:
        True when the CFD bundle should be activated, False otherwise.
    """
    if not spec:
        return False

    raw_domain: Any = spec.get("domain")
    if raw_domain is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, dict):
            raw_domain = metadata.get("domain")

    return isinstance(raw_domain, str) and raw_domain.strip().lower() == "cfd"


def load_cfd_skills() -> dict[str, str]:
    """Load all CFD skill markdown files and return filename → content mapping.

    Returns:
        Dict mapping each filename in :data:`CFD_SKILL_FILES` to its text content.

    Raises:
        FileNotFoundError: If any expected skill file is missing from the package.
    """
    result: dict[str, str] = {}
    for filename in CFD_SKILL_FILES:
        path = _HERE / filename
        result[filename] = path.read_text(encoding="utf-8")
    return result
