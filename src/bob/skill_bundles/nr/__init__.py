"""Numerical Relativity skill bundle: BSSN, slicing, GW extraction, AMR for binary BH.

Activated when the feature spec sets ``domain=nr``.  Skill markdown files are
injected into sub-agent context only when activated.

Public API:
    NR_SKILL_FILES    - Ordered list of markdown skill filenames.
    is_nr_spec(spec) -> bool
    load_nr_skills() -> dict[str, str]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent

#: Ordered list of numerical relativity skill markdown filenames.
NR_SKILL_FILES: list[str] = [
    "bssn.md",
    "gauge_conditions.md",
    "initial_data.md",
    "gw_extraction.md",
    "amr.md",
]


def is_nr_spec(spec: dict[str, Any] | None) -> bool:
    """Return True when *spec* should activate the numerical relativity skill bundle.

    Activation rules (any one sufficient):
    - ``spec["domain"] == "nr"``
    - ``spec["metadata"]["domain"] == "nr"``

    Args:
        spec: Parsed feature spec dict, or None.

    Returns:
        True when the NR bundle should be activated, False otherwise.
    """
    if not spec:
        return False

    raw_domain: Any = spec.get("domain")
    if raw_domain is None:
        metadata = spec.get("metadata")
        if isinstance(metadata, dict):
            raw_domain = metadata.get("domain")

    return isinstance(raw_domain, str) and raw_domain.strip().lower() == "nr"


def load_nr_skills() -> dict[str, str]:
    """Load all NR skill markdown files and return filename → content mapping.

    Returns:
        Dict mapping each filename in :data:`NR_SKILL_FILES` to its text content.

    Raises:
        FileNotFoundError: If any expected skill file is missing from the package.
    """
    result: dict[str, str] = {}
    for filename in NR_SKILL_FILES:
        path = _HERE / filename
        result[filename] = path.read_text(encoding="utf-8")
    return result
