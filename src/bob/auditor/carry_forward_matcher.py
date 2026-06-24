"""Carry-forward matcher — canonical F-R7-NNN regex matching for bob.auditor.

Fixes the silent-drop defect described in F-R7-554: when a sidecar is renamed
(e.g. bob26 → bob27) or a feature is referenced by shortname only, the old
exact-string id check silently drops the carry-forward feature. Regex matching
with word-boundary anchors ensures F-R7-NNN tokens embedded anywhere in a text
field are found regardless of the 'id' field value.

This module is intentionally self-contained (no imports from bob.*) to avoid
the circular-import chain triggered by bob.__init__. The bootstrap auditor's
pattern and ID set are reproduced here so this module can be imported in test
environments without initialising the full bob runtime.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "match_by_canonical_id",
    "resolve_feature_reference",
]

# Canonical F-R7-NNN pattern — mirrors _COMPILED_CANONICAL_PATTERN in the
# bootstrap auditor but kept here to avoid triggering bob.__init__ on import.
# Uses [A-Z0-9]+ so that team codes like R7 (which contain digits) are matched.
_CANONICAL_PATTERN: re.Pattern[str] = re.compile(r"F-[A-Z0-9]+-\d+")
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
    shortname — fixing the exact-string defect from F-R7-554.

    Args:
        feature_entry: A single feature dict with optional id/title/description
            keys. Must be a mapping; non-mapping input raises ValueError.
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


def resolve_feature_reference(
    reference: str,
) -> str:
    """Resolve a feature reference to its canonical F-R7-NNN form.

    Extracts the first canonical F-R7-NNN token from a reference string that
    may be a shortname, sidecar alias, or a string embedding the canonical ID.
    If no canonical token is found, returns the original reference stripped of
    whitespace.

    Args:
        reference: A string that may contain a canonical feature ID token,
            e.g. "my-sidecar (F-R7-478)", "F-R7-478", or a bare shortname.
            Must be a non-empty string.

    Returns:
        The first F-R7-NNN token found in the reference, or the stripped
        reference if no canonical token is present.

    Raises:
        ValueError: If reference is not a non-empty string.
    """
    if not isinstance(reference, str) or not reference:
        raise ValueError(
            f"reference must be a non-empty string, got {reference!r}"
        )
    match = _CANONICAL_PATTERN.search(reference)
    if match:
        return match.group(0)
    return reference.strip()
