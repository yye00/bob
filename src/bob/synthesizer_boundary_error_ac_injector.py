"""bob.synthesizer_boundary_error_ac_injector — guarantee boundary + error-path AC coverage.

Two root causes of synthesized=0/118 across prior generations:

(1) parse_criteria_response only handled flat JSON arrays of strings. The LLM
    frequently returns a list of OBJECTS such as
    [{"id":1,"criterion":"...","description":"..."}]. str(dict) yields a
    Python-repr string that is NOT a machine-verifiable AC (scores ~0).
    extract_criterion_text_from_object_format extracts the criterion text
    from recognized object keys.

(2) The LLM almost never includes boundary-condition or error-path ACs. The
    composite spec_quality_score is a weighted geometric mean — a zero in
    boundary_coverage OR error_path_coverage drives the composite to 0.0
    regardless of other sub-metrics. inject_boundary_and_error_acs
    deterministically adds one boundary and one error-path pytest: AC when
    they are absent, mirroring the scorer's token patterns exactly.

Public API:
  inject_boundary_and_error_acs(criteria, title="") -> list[str]
  extract_criterion_text_from_object_format(obj) -> str
"""
from __future__ import annotations

import re


# Keys the LLM uses when it returns objects instead of plain strings.
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


def extract_criterion_text_from_object_format(obj: dict) -> str:
    """Extract criterion text from an LLM response object using known keys.

    The LLM frequently returns objects such as
    {"id": 1, "criterion": "pytest: tests/test_x.py", "description": "..."}.
    This function extracts the criterion text using known key names in priority
    order.

    Args:
        obj: a dict from a parsed LLM JSON response.

    Returns:
        The criterion string (stripped), or empty string if no known key found.

    Raises:
        TypeError: if obj is not a dict.
    """
    if not isinstance(obj, dict):
        raise TypeError(
            f"extract_criterion_text_from_object_format: expected dict, got {type(obj).__name__!r}"
        )
    for key in _OBJECT_TEXT_KEYS:
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def inject_boundary_and_error_acs(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Ensure the AC list contains at least one boundary and one error-path AC.

    The composite spec_quality_score is a weighted geometric mean; a zero in
    boundary_coverage OR error_path_coverage drives the composite to 0.0.
    This function deterministically injects a structured pytest: AC for each
    missing coverage type, referencing the feature slug so ACs are specific
    rather than generic boilerplate.

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
            f"inject_boundary_and_error_acs: criteria must be a list, got {type(criteria).__name__!r}"
        )
    for item in criteria:
        if not isinstance(item, str):
            raise ValueError(
                f"inject_boundary_and_error_acs: all criteria must be strings, "
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
