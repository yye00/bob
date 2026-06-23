"""synthesizer.parse_criteria_response — extract criterion text from LLM response objects.

The LLM frequently returns a list of OBJECTS instead of flat strings, e.g.
[{"id":1,"criterion":"...","description":"..."}]. str(dict) yields a
Python-repr string that is NOT a verifiable AC.

This module provides extract_criterion_text to extract the criterion string
from such objects using known key names.
"""
from __future__ import annotations

from synthesizer.parse_criteria import (
    _OBJECT_TEXT_KEYS,
    parse_criteria_response,
    extract_criteria_from_response,
)


def extract_criterion_text(obj: dict) -> str:
    """Extract criterion text from an LLM response object using known keys.

    Tries keys in priority order: criterion, ac, acceptance_criterion, text,
    criteria, value, description.

    Args:
        obj: a dict from a parsed LLM JSON response.

    Returns:
        The criterion string (stripped), or empty string if no known key found.

    Raises:
        TypeError: if obj is not a dict.
    """
    if not isinstance(obj, dict):
        raise TypeError(
            f"extract_criterion_text: expected dict, got {type(obj).__name__!r}"
        )
    for key in _OBJECT_TEXT_KEYS:
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


__all__ = [
    "extract_criterion_text",
    "parse_criteria_response",
    "extract_criteria_from_response",
]
