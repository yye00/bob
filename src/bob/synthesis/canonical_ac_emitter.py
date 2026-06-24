"""Canonical AC emitter — validates and gates synthesis output against spec_quality canonical forms.

Research-strategies and adjacent feature-synthesis paths MUST emit ACs that
match the canonical structured prefix set before persisting feature rows.
Prose-form ACs fail the composite spec_quality gate at plan --create time,
causing every research-derived feature to be born blocked.

Public API::

    from bob.synthesis.canonical_ac_emitter import (
        validate_canonical_form,
        emit_negative_path_ac,
        synthesise_with_canonical_gate,
    )
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical prefix patterns (mirrors ambiguity_linter._AC_FORMS)
# ---------------------------------------------------------------------------

_CANONICAL_PREFIXES: list[tuple[str, re.Pattern[str]]] = [
    ("File exists", re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE)),
    ("Function defined", re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE)),
    ("Class defined", re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE)),
    ("pytest", re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE)),
    ("integration", re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE)),
    (
        "behavior (EARS)",
        re.compile(r"^behavior\s*:\s*.+\bwhen\b.+", re.IGNORECASE),
    ),
    ("python", re.compile(r"^python\s*:\s*\S+", re.IGNORECASE)),
    ("Field exists", re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE)),
]

# Error/failure path keywords — an AC must contain one to count as negative-path.
_ERROR_PATH_KEYWORDS: frozenset[str] = frozenset(
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

# Sentinel status written when synthesis cannot produce canonical ACs.
SYNTHESIS_BLOCKED_STATUS = "synthesis_blocked_invalid_acs"

# Maximum retry attempts when emitted ACs fail validation.
DEFAULT_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _matches_canonical(ac: str) -> bool:
    """Return True if *ac* matches at least one canonical prefix pattern."""
    stripped = ac.strip()
    return any(pattern.match(stripped) for _, pattern in _CANONICAL_PREFIXES)


def validate_canonical_form(acceptance_criteria: list[str]) -> list[str]:
    """Return the subset of *acceptance_criteria* that does NOT match any canonical prefix.

    An empty return list means all ACs are canonical; a non-empty list
    contains the prose-form or otherwise non-canonical ACs that would cause
    the spec_quality gate to reject the feature row.

    Args:
        acceptance_criteria: List of AC strings to validate.

    Returns:
        List of ACs that fail canonical-form validation (the non-canonical subset).
    """
    return [ac for ac in acceptance_criteria if not _matches_canonical(ac)]


# ---------------------------------------------------------------------------
# Negative-path AC emission
# ---------------------------------------------------------------------------


def emit_negative_path_ac(feature_topic: str) -> str:
    """Return a canonical-form AC string referencing an error/failure path for *feature_topic*.

    The emitted AC satisfies the spec_quality gate's requirement that at least
    one AC mention an error/failure path.  It uses the ``behavior:`` canonical
    prefix so it passes ``validate_canonical_form``.

    Args:
        feature_topic: Short name or description of the feature (used to
                       construct a meaningful AC string).

    Returns:
        A canonical ``behavior:`` AC string that references an error/failure
        path, e.g. ``"behavior: <feature_topic> raises ValueError when input
        is invalid"``.
    """
    safe_topic = feature_topic.strip() or "the operation"
    return (
        f"behavior: {safe_topic} raises an error or returns a failure indicator "
        f"when given invalid or missing input"
    )


def _has_negative_path_ac(acceptance_criteria: list[str]) -> bool:
    """Return True if at least one AC references an error/failure path."""
    for ac in acceptance_criteria:
        lower = ac.lower()
        if any(kw in lower for kw in _ERROR_PATH_KEYWORDS):
            return True
    return False


# ---------------------------------------------------------------------------
# Synthesis gate
# ---------------------------------------------------------------------------


@dataclass
class SynthesisResult:
    """Result of a synthesise_with_canonical_gate call."""

    status: str  # "ok" | SYNTHESIS_BLOCKED_STATUS
    acceptance_criteria: list[str] = field(default_factory=list)
    attempts: int = 0
    non_canonical: list[str] = field(default_factory=list)


def synthesise_with_canonical_gate(
    feature_topic: str,
    generator: Callable[[str, int], list[str]],
    persist: Callable[[list[str]], Any] | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> SynthesisResult:
    """Validate emitted ACs against the canonical gate before persisting.

    Calls *generator(feature_topic, attempt)* to produce a list of AC strings,
    validates them with :func:`validate_canonical_form`, and retries up to
    *max_retries* times with progressively more-explicit canonical-form prompting
    on failure.  If all retries are exhausted, marks the result
    ``synthesis_blocked_invalid_acs`` and skips the persist call rather than
    writing unusable rows.

    On success (all ACs canonical), calls *persist(acs)* if provided and
    returns a ``SynthesisResult`` with ``status="ok"``.

    Args:
        feature_topic: The feature name/description passed to *generator*.
        generator: Callable(feature_topic, attempt_number) -> list[str].
                   ``attempt_number`` starts at 1 and increments on each retry;
                   callers can use this to inject progressively stronger prompting.
        persist: Optional callable invoked with the final canonical AC list when
                 synthesis succeeds.  Skipped on failure.
        max_retries: Maximum number of generation attempts (default 3).

    Returns:
        :class:`SynthesisResult` with ``status="ok"`` on success or
        ``status=SYNTHESIS_BLOCKED_STATUS`` when all retries are exhausted.
    """
    last_non_canonical: list[str] = []

    for attempt in range(1, max_retries + 1):
        topic = _build_prompt_topic(feature_topic, attempt, max_retries)
        acs = generator(topic, attempt)

        non_canonical = validate_canonical_form(acs)

        if not non_canonical:
            # All ACs are canonical — call persist if provided.
            if persist is not None:
                persist(acs)
            logger.debug(
                "synthesise_with_canonical_gate: success on attempt %d for %r",
                attempt,
                feature_topic,
            )
            return SynthesisResult(
                status="ok",
                acceptance_criteria=acs,
                attempts=attempt,
                non_canonical=[],
            )

        last_non_canonical = non_canonical
        logger.warning(
            "synthesise_with_canonical_gate: attempt %d/%d produced %d non-canonical AC(s) for %r: %s",
            attempt,
            max_retries,
            len(non_canonical),
            feature_topic,
            non_canonical,
        )

    # All retries exhausted — skip persist.
    logger.error(
        "synthesise_with_canonical_gate: all %d attempts failed for %r; "
        "marking as %s (persist skipped)",
        max_retries,
        feature_topic,
        SYNTHESIS_BLOCKED_STATUS,
    )
    return SynthesisResult(
        status=SYNTHESIS_BLOCKED_STATUS,
        acceptance_criteria=[],
        attempts=max_retries,
        non_canonical=last_non_canonical,
    )


def _build_prompt_topic(feature_topic: str, attempt: int, max_retries: int) -> str:
    """Return a progressively more explicit canonical-form prompt for *feature_topic*.

    Attempt 1 returns the topic as-is.  Subsequent attempts inject canonical-
    form guidance so that the generator (whether an LLM or a rule engine) can
    produce correctly-formed ACs.
    """
    if attempt == 1:
        return feature_topic

    canonical_hint = (
        "IMPORTANT: Every acceptance criterion MUST start with one of these "
        "canonical prefixes:\n"
        "  File exists: <path>\n"
        "  Function defined: <dotted.module.name>\n"
        "  Class defined: <dotted.module.ClassName>\n"
        "  pytest: <test_path>\n"
        "  integration: <dotted.module>\n"
        "  behavior: <subject> <verb> <object> when <condition>\n"
        "At least one AC MUST mention an error/failure path.\n"
        "Do NOT emit prose-form criteria.\n\n"
    )

    if attempt >= max_retries:
        # Maximum explicitness on the final attempt.
        canonical_hint = (
            "CRITICAL: This is the final retry. Output ONLY canonical-form ACs "
            "matching the required prefixes (File exists:, Function defined:, "
            "Class defined:, pytest:, integration:, behavior: ... when ...).\n"
            "At least one AC MUST contain the word 'error', 'failure', or 'invalid'.\n\n"
        ) + canonical_hint

    return canonical_hint + feature_topic
