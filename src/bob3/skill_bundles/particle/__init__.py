"""Particle physics skill bundle: Geant4 user actions, custom physics lists.

Activated when the feature spec sets ``domain=particle``.  Skill markdown files
are injected into sub-agent context only when activated.

Public API:
    PARTICLE_SKILL_FILES    - Ordered list of markdown skill filenames.
    is_particle_spec(spec) -> bool
    load_particle_skills() -> dict[str, str]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent

#: Ordered list of particle physics skill markdown filenames.
PARTICLE_SKILL_FILES: list[str] = [
    "geant4_user_actions.md",
    "custom_physics_lists.md",
]


def is_particle_spec(spec: dict[str, Any] | None) -> bool:
    """Return True when *spec* should activate the particle skill bundle.

    Activation rules (any one sufficient):
    - ``spec["domain"] == "particle"``
    - ``spec["metadata"]["domain"] == "particle"``

    Args:
        spec: Parsed feature spec dict, or None.

    Returns:
        True when the particle bundle should be activated, False otherwise.
    """
    if not spec:
        return False

    raw_domain: Any = spec.get("domain")
    if raw_domain is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, dict):
            raw_domain = metadata.get("domain")

    return isinstance(raw_domain, str) and raw_domain.strip().lower() == "particle"


def load_particle_skills() -> dict[str, str]:
    """Load all particle skill markdown files and return filename → content mapping.

    Returns:
        Dict mapping each filename in :data:`PARTICLE_SKILL_FILES` to its text content.

    Raises:
        FileNotFoundError: If any expected skill file is missing from the package.
    """
    result: dict[str, str] = {}
    for filename in PARTICLE_SKILL_FILES:
        path = _HERE / filename
        result[filename] = path.read_text(encoding="utf-8")
    return result
