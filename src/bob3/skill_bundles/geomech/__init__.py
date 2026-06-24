"""Geomechanics skill bundle: poroelasticity, frictional contact, fault slip, plasticity.

Activated when the feature spec sets ``domain=geomech``.  Skill markdown files
are injected into sub-agent context only when activated.

Public API:
    GEOMECH_SKILL_FILES   - Ordered list of markdown skill filenames.
    is_geomech_spec(spec) -> bool
    load_geomech_skills() -> dict[str, str]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent

#: Ordered list of geomechanics skill markdown filenames.
GEOMECH_SKILL_FILES: list[str] = [
    "poroelasticity.md",
    "frictional_contact.md",
    "fault_slip.md",
    "plasticity.md",
]


def is_geomech_spec(spec: dict[str, Any] | None) -> bool:
    """Return True when *spec* should activate the geomechanics skill bundle.

    Activation rules (any one sufficient):
    - ``spec["domain"] == "geomech"``
    - ``spec["metadata"]["domain"] == "geomech"``

    Args:
        spec: Parsed feature spec dict, or None.

    Returns:
        True when the geomech bundle should be activated, False otherwise.
    """
    if not spec:
        return False

    raw_domain: Any = spec.get("domain")
    if raw_domain is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, dict):
            raw_domain = metadata.get("domain")

    return isinstance(raw_domain, str) and raw_domain.strip().lower() == "geomech"


def load_geomech_skills() -> dict[str, str]:
    """Load all geomechanics skill markdown files and return filename → content mapping.

    Returns:
        Dict mapping each filename in :data:`GEOMECH_SKILL_FILES` to its text content.

    Raises:
        FileNotFoundError: If any expected skill file is missing from the package.
    """
    result: dict[str, str] = {}
    for filename in GEOMECH_SKILL_FILES:
        path = _HERE / filename
        result[filename] = path.read_text(encoding="utf-8")
    return result
