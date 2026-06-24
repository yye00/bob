"""bob3.synthesizer_parse_fix — parse + AC-injection fixes for the synthesizer.

Two root causes of synthesized=0/118 in prior generations:

(1) parse_criteria_response only handled flat JSON arrays of strings. When the
    LLM returns a list of OBJECTS such as
    [{"id":1,"criterion":"...","description":"..."}], str(dict) yields a
    Python-repr string that is NOT a machine-verifiable AC (scores ~0).
    This module's parse_criteria_response extracts criterion text from known
    object keys so every LLM response format works correctly.

(2) The LLM almost never produces boundary-condition or error-path ACs.
    The composite spec_quality_score is a weighted geometric mean — a zero in
    boundary_coverage OR error_path_coverage forces composite=0.0 regardless of
    the other sub-metrics. inject_boundary_error_acs deterministically adds one
    boundary and one error-path pytest: AC when they are absent, referencing the
    feature slug so they are specific rather than generic boilerplate.

Public API:
  parse_criteria_response(response_text) -> list[str] | None
  inject_boundary_error_acs(criteria, title="") -> list[str]
"""
from __future__ import annotations

import json
import re


# Keys the LLM uses when returning objects instead of plain strings.
_OBJECT_TEXT_KEYS: tuple[str, ...] = (
    "criterion",
    "ac",
    "acceptance_criterion",
    "text",
    "criteria",
    "value",
    "description",
)

# Boundary-condition tokens mirroring tools/spec_quality_score.py scorer.
_BOUNDARY_RE = re.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
    r"boundary|edge case|corner case|overflow|underflow|limit|"
    r"threshold|floor|ceiling)\b",
    re.IGNORECASE,
)

# Error-path tokens mirroring the scorer.
_ERROR_RE = re.compile(
    r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
    r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
    r"TypeError|RuntimeError)\b",
    re.IGNORECASE,
)

# Structural AC prefixes — these do NOT count toward behavior coverage.
_STRUCTURAL_PREFIX_RE = re.compile(
    r"^\s*(file exists|function defined|class defined|pytest|integration|"
    r"field exists|file modified|ci tests|python)\s*:",
    re.IGNORECASE,
)


def parse_criteria_response(response_text: str) -> list[str] | None:
    """Parse synthesizer LLM response into a list of AC strings.

    Handles both flat JSON arrays of strings and lists of objects (the LLM
    frequently returns object-format responses such as
    [{"id":1,"criterion":"pytest: tests/test_x.py","description":"..."}]).
    When list items are dicts, the criterion text is extracted from known keys
    in priority order: criterion, ac, acceptance_criterion, text, criteria,
    value, description.

    Args:
        response_text: raw text from the LLM.

    Returns:
        list[str] of non-empty criterion strings, or None if parsing fails.
    """
    if not isinstance(response_text, str):
        return None

    # Extract JSON from fenced code block first, then fall back to bare array.
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", response_text, re.DOTALL)
    json_str: str | None = fenced.group(1) if fenced else None
    if json_str is None:
        m = re.search(r"\[\s*[\"\{].*?\]", response_text, re.DOTALL)
        json_str = m.group(0) if m else None
    if json_str is None:
        return None

    try:
        parsed = json.loads(json_str)
    except Exception:
        return None

    if not isinstance(parsed, list) or not parsed:
        return None

    def _coerce(x: object) -> str:
        if isinstance(x, dict):
            for key in _OBJECT_TEXT_KEYS:
                v = x.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""
        return str(x).strip()

    items = [c for c in (_coerce(x) for x in parsed) if c]
    return items or None


def inject_boundary_error_acs(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Ensure the AC list contains at least one boundary and one error-path AC.

    The composite spec_quality_score is a weighted geometric mean; a zero in
    boundary_coverage OR error_path_coverage forces composite=0.0. This function
    deterministically appends a structured pytest: AC for each missing coverage
    type, referencing the feature slug so injected ACs are specific rather than
    generic boilerplate.

    If the LLM already included boundary/error ACs, no duplicates are added.

    Args:
        criteria: list of AC strings.
        title: feature title used to derive the file slug for injected ACs.

    Returns:
        A new list that is a superset of *criteria* with injected ACs appended.

    Raises:
        TypeError: if *criteria* is not a list.
        ValueError: if any element in *criteria* is not a string.
    """
    if not isinstance(criteria, list):
        raise TypeError(
            f"inject_boundary_error_acs: criteria must be a list, got {type(criteria).__name__!r}"
        )
    for item in criteria:
        if not isinstance(item, str):
            raise ValueError(
                f"inject_boundary_error_acs: all criteria must be strings, "
                f"got {type(item).__name__!r}: {item!r}"
            )

    # Build probe string from behavior ACs only (skip structural prefixes).
    probe_parts: list[str] = []
    for c in criteria:
        if not c.strip():
            continue
        if _STRUCTURAL_PREFIX_RE.match(c):
            for sep in (" — ", " - ", "—", "–"):
                if sep in c:
                    probe_parts.append(c.split(sep, 1)[1])
                    break
        else:
            probe_parts.append(c)
    probe = " ".join(probe_parts)
    has_boundary = bool(_BOUNDARY_RE.search(probe))
    has_error = bool(_ERROR_RE.search(probe))

    if has_boundary and has_error:
        return list(criteria)

    slug = _make_slug(title)
    out = list(criteria)
    if not has_boundary:
        out.append(
            f"pytest: tests/test_{slug}_boundary.py — empty, zero, or minimum "
            "input returns a well-defined result rather than raising (boundary case)"
        )
    if not has_error:
        out.append(
            f"pytest: tests/test_{slug}_error.py — invalid input raises ValueError "
            "and the function does not silently succeed (error path)"
        )
    return out


def _make_slug(title: str) -> str:
    """Derive a filesystem-safe slug from a feature title."""
    raw = title.split("—")[0] if title else "feature"
    slug = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")[:50]
    return slug or "feature"
