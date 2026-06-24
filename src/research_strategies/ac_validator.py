"""research_strategies.ac_validator — AC-form validator for research-strategies synthesis.

Validates that every acceptance criterion produced by the research-strategies
generator matches the canonical grammar required by the spec_quality gate.
Prose-form ACs cause features to be born blocked at gate evaluation; this
validator is the prevention layer.

Canonical AC forms accepted::

    File exists: <path>
    Function defined: <dotted.path>
    Class defined: <dotted.path>
    pytest: <test_path>
    integration: <dotted.module.or.path>
    behavior: <subject> <verb> <object> when <condition>
    python: <module_path>
    Field exists: <field_spec>

Usage::

    from research_strategies.ac_validator import validate_acs, ACValidationResult

    result = validate_acs(["pytest: tests/test_foo.py", "behavior: foo raises ValueError when input is empty"])
    assert result.passed
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Canonical prefix patterns — mirrors bob.spec_quality canonical forms
# ---------------------------------------------------------------------------

_CANONICAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE),
    re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE),
    re.compile(r"^behavior\s*:\s*.+\bwhen\b.+", re.IGNORECASE),
    re.compile(r"^python\s*:\s*\S+", re.IGNORECASE),
    re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE),
]

# Keywords that indicate an error/failure-path AC (negative AC)
_ERROR_KEYWORDS: frozenset[str] = frozenset(
    {
        "error",
        "failure",
        "fail",
        "invalid",
        "missing",
        "reject",
        "exception",
        "raises",
        "corrupt",
        "timeout",
        "negative",
        "bad",
    }
)


def _is_canonical(ac: str) -> bool:
    """Return True if *ac* matches at least one canonical prefix pattern."""
    stripped = ac.strip()
    return any(p.match(stripped) for p in _CANONICAL_PATTERNS)


def _has_error_keyword(ac: str) -> bool:
    """Return True if *ac* references an error/failure path."""
    lower = ac.lower()
    return any(kw in lower for kw in _ERROR_KEYWORDS)


@dataclass
class ACValidationResult:
    """Result of an AC list validation against the spec_quality gate."""

    passed: bool
    non_canonical: list[str] = field(default_factory=list)
    has_negative_path_ac: bool = False


def validate_acs(acceptance_criteria: list[str]) -> ACValidationResult:
    """Validate a list of ACs against the canonical spec_quality gate rules.

    Checks whether every AC matches a canonical structured prefix and whether
    at least one AC references an error/failure path (negative-path AC).

    Args:
        acceptance_criteria: List of AC strings to validate. Must be a list.

    Returns:
        :class:`ACValidationResult` with ``passed`` True when all ACs are
        canonical and at least one negative-path AC exists.

    Raises:
        TypeError: When *acceptance_criteria* is not a list.
        ValueError: When any element in the list is not a non-empty string.
    """
    if not isinstance(acceptance_criteria, list):
        raise TypeError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    for i, ac in enumerate(acceptance_criteria):
        if not isinstance(ac, str):
            raise ValueError(
                f"acceptance_criteria[{i}] must be a string, "
                f"got {type(ac).__name__!r}: {ac!r}"
            )
        if not ac.strip():
            raise ValueError(
                f"acceptance_criteria[{i}] must be a non-empty string"
            )

    if not acceptance_criteria:
        return ACValidationResult(passed=False, non_canonical=[], has_negative_path_ac=False)

    non_canonical = [ac for ac in acceptance_criteria if not _is_canonical(ac)]
    has_negative = any(_has_error_keyword(ac) for ac in acceptance_criteria)
    all_canonical = len(non_canonical) == 0

    passed = all_canonical and has_negative

    return ACValidationResult(
        passed=passed,
        non_canonical=non_canonical,
        has_negative_path_ac=has_negative,
    )


def validate_single_ac(ac: str) -> bool:
    """Return True if a single AC string matches a canonical prefix.

    Args:
        ac: AC string to validate.

    Returns:
        True when *ac* is canonical.

    Raises:
        TypeError: When *ac* is not a string.
        ValueError: When *ac* is empty or whitespace-only.
    """
    if not isinstance(ac, str):
        raise TypeError(f"ac must be a string, got {type(ac).__name__!r}")
    if not ac.strip():
        raise ValueError("ac must be a non-empty string")
    return _is_canonical(ac)
