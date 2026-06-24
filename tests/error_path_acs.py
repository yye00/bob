"""Error-path AC fixtures for synthesizer coverage tests.

These fixtures represent well-formed error-path ACs as would be injected by
inject_boundary_and_error_acs when a feature's AC list lacks them.
Used by test suites verifying the synthesizer guarantees coverage.
"""
from __future__ import annotations

ERROR_AC_TEMPLATES = [
    "pytest: tests/test_{slug}_error.py — invalid input raises ValueError and the function does not silently succeed (error path)",
    "When given invalid input, the function raises ValueError rather than returning a result (error path)",
    "When the input is malformed, the function raises an exception and does not silently succeed (error path)",
    "The function must not accept None as a valid input; it must raise TypeError (error path)",
]

ERROR_TOKENS = frozenset(
    [
        "error",
        "exception",
        "fail",
        "invalid",
        "reject",
        "raise",
        "abort",
        "refuse",
        "block",
        "does not",
        "cannot",
        "must not",
        "shall not",
        "ValueError",
        "KeyError",
        "TypeError",
        "RuntimeError",
    ]
)


def make_error_ac(slug: str) -> str:
    """Return a canonical error-path AC for *slug*."""
    return (
        f"pytest: tests/test_{slug}_error.py — invalid input raises ValueError "
        "and the function does not silently succeed (error path)"
    )


def has_error_coverage(criteria: list[str]) -> bool:
    """Return True if any criterion in *criteria* contains an error-path token."""
    import re

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in ERROR_TOKENS) + r")\b",
        re.IGNORECASE,
    )
    return any(pattern.search(c) for c in criteria)
