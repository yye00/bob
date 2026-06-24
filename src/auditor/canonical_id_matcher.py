"""Canonical ID matcher for permanent-forward-carry auditing.

Fixes the exact-string defect described in F-R7-554: when a sidecar is renamed
(e.g. bob26 → bob27) or a feature is referenced by shortname only, an exact-
string id check silently drops carry-forward detection.  This module provides
a regex-based matcher that scans id, title, and description fields so the
feature is found regardless of sidecar rename or shortname drift.

Integration: bob3.permanent_forward_carry_auditor delegates matching to
match_by_canonical_id so all carry-forward checks use the same regex logic.
"""

from __future__ import annotations

import re
from typing import Any

from bob3.bootstrap.permanent_forward_carry_auditor import (  # noqa: F401
    _COMPILED_CANONICAL_PATTERN,
    extract_canonical_ids,
    required_feature_ids,
)

__all__ = [
    "match_by_canonical_id",
]

# Pre-compiled pattern that validates a canonical ID looks like F-<LETTERS>-<DIGITS>
_CANONICAL_TOKEN_PATTERN: re.Pattern[str] = re.compile(
    r"^[A-Za-z]+-[A-Za-z0-9]+-\d+$"
)

# Looser check: must contain at least one letter AND at least one digit
_HAS_LETTER: re.Pattern[str] = re.compile(r"[A-Za-z]")
_HAS_DIGIT: re.Pattern[str] = re.compile(r"\d")


def match_by_canonical_id(
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
