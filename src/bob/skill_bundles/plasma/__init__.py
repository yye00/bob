"""Plasma physics skill bundle: PIC, Boris pusher, field gather/scatter, MHD, Vlasov-Poisson.

Activated when the feature spec sets ``domain=plasma``.  Skill markdown files
are injected into sub-agent context only when activated.

Public API:
    PLASMA_SKILL_FILES    - Ordered list of markdown skill filenames.
    is_plasma_spec(spec) -> bool
    load_plasma_skills() -> dict[str, str]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent

#: Ordered list of plasma physics skill markdown filenames.
PLASMA_SKILL_FILES: list[str] = [
    "pic.md",
    "boris_pusher.md",
    "field_gather_scatter.md",
    "mhd.md",
    "vlasov_poisson.md",
]


def is_plasma_spec(spec: dict[str, Any] | None) -> bool:
    """Return True when *spec* should activate the plasma skill bundle.

    Activation rules (any one sufficient):
    - ``spec["domain"] == "plasma"``
    - ``spec["metadata"]["domain"] == "plasma"``

    Args:
        spec: Parsed feature spec dict, or None.

    Returns:
        True when the plasma bundle should be activated, False otherwise.
    """
    if not spec:
        return False

    raw_domain: Any = spec.get("domain")
    if raw_domain is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, dict):
            raw_domain = metadata.get("domain")

    return isinstance(raw_domain, str) and raw_domain.strip().lower() == "plasma"


def load_plasma_skills() -> dict[str, str]:
    """Load all plasma skill markdown files and return filename → content mapping.

    Returns:
        Dict mapping each filename in :data:`PLASMA_SKILL_FILES` to its text content.

    Raises:
        FileNotFoundError: If any expected skill file is missing from the package.
    """
    result: dict[str, str] = {}
    for filename in PLASMA_SKILL_FILES:
        path = _HERE / filename
        result[filename] = path.read_text(encoding="utf-8")
    return result
