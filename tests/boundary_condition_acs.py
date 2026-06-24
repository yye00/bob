"""Boundary-condition AC fixtures for synthesizer coverage tests.

These fixtures represent well-formed boundary-condition ACs as would be
injected by inject_boundary_and_error_acs when a feature's AC list lacks them.
Used by test suites verifying the synthesizer guarantees coverage.
"""
from __future__ import annotations

BOUNDARY_AC_TEMPLATES = [
    "pytest: tests/test_{slug}_boundary.py — empty, zero, or minimum input returns a well-defined result rather than raising (boundary case)",
    "When the input is empty or None, the function returns None without raising an exception (boundary)",
    "When given the minimum valid input (1 element), the function returns a non-empty result (boundary)",
    "When the input list has zero elements, the function returns a well-defined result (boundary/zero case)",
]

BOUNDARY_TOKENS = frozenset(
    [
        "empty",
        "null",
        "none",
        "zero",
        "negative",
        "maximum",
        "minimum",
        "max",
        "min",
        "boundary",
        "edge case",
        "corner case",
        "overflow",
        "underflow",
        "limit",
        "threshold",
        "floor",
        "ceiling",
    ]
)


def make_boundary_ac(slug: str) -> str:
    """Return a canonical boundary-condition AC for *slug*."""
    return (
        f"pytest: tests/test_{slug}_boundary.py — empty, zero, or minimum "
        "input returns a well-defined result rather than raising (boundary case)"
    )


def has_boundary_coverage(criteria: list[str]) -> bool:
    """Return True if any criterion in *criteria* contains a boundary token."""
    import re

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in BOUNDARY_TOKENS) + r")\b",
        re.IGNORECASE,
    )
    return any(pattern.search(c) for c in criteria)
