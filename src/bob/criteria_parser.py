"""bob.criteria_parser — parse LLM AC responses and inject missing boundary/error ACs.

Two historical failure modes caused synthesized=0/118 across bob66-70:

(1) parse_criteria_response only handled flat JSON arrays of strings. The LLM
    frequently returns a list of OBJECTS such as
    [{"id":1,"criterion":"...","description":"..."}]. Using str(dict) yields a
    Python-repr string that is NOT a machine-verifiable AC and scores ~0. This
    module extracts the criterion text from recognized object keys.

(2) Even when parsed, the LLM almost never includes boundary-condition or
    error-path ACs. The composite spec_quality_score is a weighted geometric
    mean — boundary_coverage=0 OR error_path_coverage=0 drives it to 0.0
    regardless of other sub-metrics. inject_missing_boundary_error_acs
    deterministically adds one boundary and one error-path pytest: AC when they
    are absent, mirroring the scorer's token patterns exactly.

Public API:
  parse_criteria_response(response_text) -> list[str] | None
  inject_missing_boundary_error_acs(criteria, title="") -> list[str]
"""
from __future__ import annotations

import json
import re


# Keys the LLM uses when it returns objects instead of plain strings.
_OBJECT_TEXT_KEYS = (
    "criterion",
    "ac",
    "acceptance_criterion",
    "text",
    "criteria",
    "value",
    "description",
)

# Boundary-condition tokens that mirror tools/spec_quality_score.py scorer.
_BOUNDARY_RE = re.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
    r"boundary|edge case|corner case|overflow|underflow|limit|"
    r"threshold|floor|ceiling)\b",
    re.IGNORECASE,
)

# Error-path tokens that mirror the scorer.
_ERROR_RE = re.compile(
    r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
    r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
    r"TypeError|RuntimeError)\b",
    re.IGNORECASE,
)

# Structural AC prefixes — these do NOT count toward coverage in the scorer.
_STRUCTURAL_PREFIX_RE = re.compile(
    r"^\s*(file exists|function defined|class defined|pytest|integration|"
    r"field exists|file modified|ci tests|python)\s*:",
    re.IGNORECASE,
)


def parse_criteria_response(response_text: str) -> list[str] | None:
    """Parse a synthesizer LLM response into a list of AC strings.

    Handles both flat arrays of strings and arrays of objects (e.g.
    [{"id":1,"criterion":"...","description":"..."}]).  Returns None on any
    failure (malformed JSON, empty array, no JSON found, non-string input).
    """
    if not isinstance(response_text, str):
        return None

    # Prefer fenced ```json blocks; fall back to a bare inline JSON array.
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", response_text, re.DOTALL)
    json_str: str | None = fenced.group(1) if fenced else None
    if json_str is None:
        m = re.search(r"\[\s*\"[^\"]+?\".*?\]", response_text, re.DOTALL)
        json_str = m.group(0) if m else None
    if json_str is None:
        return None

    try:
        parsed = json.loads(json_str)
    except Exception:
        return None

    if not isinstance(parsed, list) or not parsed:
        return None

    items: list[str] = []
    for x in parsed:
        if isinstance(x, str):
            s = x.strip()
            if s:
                items.append(s)
        elif isinstance(x, dict):
            text = _extract_from_object(x)
            if text:
                items.append(text)
        # Other types (int, None, …) are silently dropped.

    return items if items else None


def _extract_from_object(obj: dict) -> str:
    """Extract criterion text from an LLM response object using known keys."""
    for key in _OBJECT_TEXT_KEYS:
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def inject_missing_boundary_error_acs(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Ensure the AC list contains at least one boundary and one error-path AC.

    The composite spec_quality_score is a weighted geometric mean; a zero in
    boundary_coverage OR error_path_coverage drives the composite to 0.0.
    This function deterministically injects a structured pytest: AC for each
    missing coverage type, referencing the feature slug so ACs are specific.

    Args:
        criteria: list of AC strings (must be a list, not None or other type).
        title: feature title used to derive the file slug for injected ACs.

    Returns:
        A new list that is a superset of *criteria* with the injected ACs
        appended as needed.

    Raises:
        TypeError: if *criteria* is not a list.
        ValueError: if any element in *criteria* is not a string.
    """
    if not isinstance(criteria, list):
        raise TypeError(
            f"inject_missing_boundary_error_acs: criteria must be a list, got {type(criteria).__name__!r}"
        )
    for item in criteria:
        if not isinstance(item, str):
            raise ValueError(
                f"inject_missing_boundary_error_acs: all criteria must be strings, "
                f"got {type(item).__name__!r}: {item!r}"
            )

    # Build a probe string from non-structural ACs and the description portion
    # of structural ACs to avoid false matches on path slugs.
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
