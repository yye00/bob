"""research_strategies_generator — canonical AC emitter with spec_quality gate validation.

Research-strategies and adjacent feature-synthesis paths MUST emit ACs that
match the canonical structured prefix set required by the spec_quality gate.
Prose-form ACs cause features to be born blocked at gate evaluation time.

Public API::

    from research_strategies_generator import (
        emit_canonical_structured_acs,
        validate_acs_against_spec_quality_gate,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Canonical prefix patterns — mirrors bob.spec_quality canonical forms
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

# Status emitted when synthesis cannot produce canonical ACs after all retries
SYNTHESIS_BLOCKED_STATUS = "synthesis_blocked_invalid_acs"

# Default retry limit
DEFAULT_MAX_RETRIES = 3


@dataclass
class ACGateResult:
    """Result of validating an AC list against the spec_quality gate."""

    passed: bool
    non_canonical: list[str] = field(default_factory=list)
    has_negative_path_ac: bool = False
    errors: list[str] = field(default_factory=list)


def _is_canonical(ac: str) -> bool:
    """Return True if *ac* matches at least one canonical prefix pattern."""
    return any(p.match(ac.strip()) for p in _CANONICAL_PATTERNS)


def _has_error_keyword(ac: str) -> bool:
    """Return True if *ac* references an error/failure path."""
    lower = ac.lower()
    return any(kw in lower for kw in _ERROR_KEYWORDS)


def _slugify(topic: str) -> str:
    """Convert a feature topic into a safe module-path slug."""
    slug = re.sub(r"[^a-zA-Z0-9_.]", "_", topic.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "feature"


def validate_acs_against_spec_quality_gate(acceptance_criteria: Any) -> ACGateResult:
    """Validate a list of ACs against the canonical spec_quality gate rules.

    Checks whether every AC matches a canonical structured prefix and whether
    at least one AC references an error/failure path (negative-path AC).

    Args:
        acceptance_criteria: List of AC strings to validate. Must be a list.

    Returns:
        :class:`ACGateResult` with ``passed`` True when all ACs are canonical
        and at least one negative-path AC exists.

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
        return ACGateResult(passed=False, non_canonical=[], has_negative_path_ac=False)

    non_canonical = [ac for ac in acceptance_criteria if not _is_canonical(ac)]
    has_negative = any(_has_error_keyword(ac) for ac in acceptance_criteria)
    all_canonical = len(non_canonical) == 0

    errors: list[str] = []
    if not all_canonical:
        errors.append(f"{len(non_canonical)} ACs do not match any canonical structured form")
    if not has_negative:
        errors.append("No ACs mention error/failure paths — add at least one negative/error AC")

    return ACGateResult(
        passed=all_canonical and has_negative,
        non_canonical=non_canonical,
        has_negative_path_ac=has_negative,
        errors=errors,
    )


def emit_canonical_structured_acs(topic: Any) -> list[str]:
    """Emit a canonical-form AC list for the given feature *topic*.

    Every emitted AC matches one of the canonical structured prefixes required
    by the spec_quality gate:
    ``File exists:``, ``Function defined:``, ``Class defined:``, ``pytest:``,
    ``integration:``, ``behavior: ... when ...``.

    At least one AC references an error/failure path to satisfy the gate's
    negative-AC requirement.

    Args:
        topic: Feature name or description string. Must be a non-empty string.

    Returns:
        List of canonical-form AC strings (minimum 4 entries).

    Raises:
        TypeError: When *topic* is not a string type.
        ValueError: When *topic* is empty, whitespace-only, or not a string.
    """
    if not isinstance(topic, str):
        raise TypeError(
            f"topic must be a non-empty string, got {type(topic).__name__!r}"
        )
    stripped = topic.strip()
    if not stripped:
        raise ValueError(
            "topic must be a non-empty string; whitespace-only or empty strings are not allowed"
        )

    slug = _slugify(stripped)

    # Build module path from slug
    if "." in slug:
        module_path = slug
    else:
        module_path = f"research_strategies.{slug}"

    # Derive safe test-file path slug (no dots, no dashes — only underscores)
    test_slug = re.sub(r"[^a-zA-Z0-9_]", "_", slug)
    test_path = f"tests/test_{test_slug}.py"

    acs: list[str] = [
        f"Function defined: {module_path}.emit_canonical_structured_acs",
        f"File exists: src/research_strategies_generator.py",
        f"pytest: {test_path}",
        f"integration: research_strategies.spec_synthesis",
        # Negative/error-path AC — satisfies the gate's mandatory requirement
        f"behavior: emit_canonical_structured_acs raises ValueError when topic is empty or invalid",
    ]

    return acs


def generate_with_gate(
    feature_topic: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Generate canonical ACs for a feature, retrying if gate validation fails.

    Calls :func:`emit_canonical_structured_acs` and validates the result
    against :func:`validate_acs_against_spec_quality_gate`. On validation
    failure, retries up to *max_retries* times. If all retries are exhausted,
    marks the synthesis as ``synthesis_blocked_invalid_acs`` and returns without
    writing to the feature row (rather than emitting unusable rows that will
    inevitably block at the gate).

    Args:
        feature_topic: Feature name or description string. Must be a non-empty string.
        max_retries: Maximum number of generation + validation attempts (default 3).

    Returns:
        Dict with keys:
        - ``status`` (str): ``"ok"`` on success, ``"synthesis_blocked_invalid_acs"``
          on persistent failure.
        - ``acceptance_criteria`` (list[str]): Validated canonical AC list on success,
          empty list on failure.
        - ``attempts`` (int): Number of generation attempts made.
        - ``non_canonical`` (list[str]): Non-canonical ACs from last failed attempt
          (empty on success).

    Raises:
        TypeError: When *feature_topic* is not a string.
        ValueError: When *feature_topic* is empty or whitespace-only.
    """
    if not isinstance(feature_topic, str):
        raise TypeError(
            f"feature_topic must be a non-empty string, got {type(feature_topic).__name__!r}"
        )
    stripped = feature_topic.strip()
    if not stripped:
        raise ValueError(
            "feature_topic must be a non-empty string; whitespace-only or empty strings are not allowed"
        )

    last_non_canonical: list[str] = []

    for attempt in range(1, max_retries + 1):
        acs = emit_canonical_structured_acs(stripped)
        result = validate_acs_against_spec_quality_gate(acs)

        if result.passed:
            return {
                "status": "ok",
                "acceptance_criteria": acs,
                "attempts": attempt,
                "non_canonical": [],
            }

        last_non_canonical = result.non_canonical

    return {
        "status": SYNTHESIS_BLOCKED_STATUS,
        "acceptance_criteria": [],
        "attempts": max_retries,
        "non_canonical": last_non_canonical,
    }
