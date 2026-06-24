"""Carry-forward matcher for permanent-forward-carry auditing.

Provides match_carry_forward_by_canonical_id — the primary entry point for
carry-forward detection using canonical F-R7-NNN regex matching.  Unlike
exact-string id checks, this function scans id, title, and description
fields so renamed sidecars and shortname aliases are correctly detected.

This fixes the silent-drop defect described in F-R7-554: when a sidecar is
renamed (e.g. bob26 → bob27) or a feature is referenced by shortname only,
exact-string equality silently fails.  Regex matching with word-boundary
anchors ensures F-R7-478 embedded anywhere in a text field is found.

Integration: use auditor.canonical_id_matcher for the compiled module reference.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "match_carry_forward_by_canonical_id",
]

# Pre-compiled helpers for validating the canonical_id argument.
_HAS_LETTER: re.Pattern[str] = re.compile(r"[A-Za-z]")
_HAS_DIGIT: re.Pattern[str] = re.compile(r"\d")


def match_carry_forward_by_canonical_id(
    feature_entry: dict[str, Any],
    canonical_id: str,
) -> bool:
    """Return True if *canonical_id* token appears in any text field of *feature_entry*.

    Scans the id, title, and description fields of a single feature dict for
    the canonical F-R7-NNN token using a word-boundary regex.  This allows
    detection even when the feature's 'id' field holds a sidecar alias or
    shortname (fixes the exact-string defect from F-R7-554).

    Args:
        feature_entry: A single feature dict. Must be a mapping; non-mapping
            input raises ValueError.
        canonical_id: The canonical feature ID to search for, e.g. "F-R7-478".
            Must be a non-empty, non-blank string that contains at least one
            letter and one digit.

    Returns:
        True if canonical_id token is found in any text field of feature_entry,
        False otherwise.

    Raises:
        ValueError: If feature_entry is not a dict, or canonical_id is not a
            non-empty string containing at least one letter and one digit.
    """
    if not isinstance(feature_entry, dict):
        raise ValueError(
            f"feature_entry must be a dict, got {type(feature_entry).__name__!r}"
        )
    if not isinstance(canonical_id, str) or not canonical_id:
        raise ValueError(
            f"canonical_id must be a non-empty string, got {canonical_id!r}"
        )
    stripped = canonical_id.strip()
    if not stripped:
        raise ValueError(
            "canonical_id must not be blank after stripping whitespace"
        )
    if not _HAS_LETTER.search(stripped) or not _HAS_DIGIT.search(stripped):
        raise ValueError(
            f"canonical_id does not look like a canonical feature token: {canonical_id!r}"
        )

    # Word-boundary pattern so F-R7-47 does not match inside F-R7-478
    pattern = re.compile(r"(?<!\w)" + re.escape(stripped) + r"(?!\w)")
    for field in ("id", "title", "description"):
        text = feature_entry.get(field)
        if isinstance(text, str) and pattern.search(text):
            return True
    return False
