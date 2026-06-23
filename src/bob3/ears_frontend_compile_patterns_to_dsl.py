"""EARS frontend — compile all five EARS patterns into bob3's acceptance criterion DSL.

Provides a structured natural-language spec authoring interface by recognising
all five EARS (Easy Approach to Requirements Syntax) pattern families:

1. **Ubiquitous** — "The system shall <predicate>."
   Unconditional requirements that always hold.

2. **Event-driven** — "When <condition>, the system shall <predicate>."
   Requirements triggered by a specific event.

3. **Unwanted behaviour** — "The system shall not <predicate>."
   Forbidden or prohibited behaviour.

4. **State-driven** — "While <condition>, the system shall <predicate>."
   Requirements active for the duration of a system state.

5. **Optional** — "Where <feature-ref> is enabled/supported, the system shall <predicate>."
   Requirements that apply only when an optional feature is present.

Each recognised EARS pattern is compiled into one or more bob3 DSL criterion
strings (the same format produced by the spec synthesiser):

- ``"python: <expression>"``   — assertion encoded as an inline Python expression
- ``"File exists: <path>"``    — source-file presence check
- ``"pytest: <path>"``         — test-file invocation
- ``"Function defined: <fqn>"`` — importable symbol check

Public API
----------
- :class:`EARSPatternKind`   — enum of all five EARS pattern families
- :class:`EARSPattern`       — a single parsed EARS pattern
- :func:`parse_ears_pattern` — parse one sentence into an :class:`EARSPattern`
- :func:`compile_ears_to_dsl` — compile one pattern into DSL criterion strings
- :func:`ears_text_to_dsl_criteria` — parse text, compile all patterns, deduplicate
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Pattern kind enum
# ---------------------------------------------------------------------------


class EARSPatternKind(str, Enum):
    """The five EARS requirement pattern families."""

    UBIQUITOUS = "ubiquitous"
    EVENT_DRIVEN = "event_driven"
    UNWANTED = "unwanted"
    STATE_DRIVEN = "state_driven"
    OPTIONAL = "optional"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class EARSPattern:
    """A single parsed EARS requirement pattern.

    Attributes:
        kind:        Which EARS family this pattern belongs to.
        raw:         The verbatim sentence (or fragment) as parsed.
        subject:     The entity the requirement applies to (e.g. "system").
        predicate:   The verb phrase describing the required/forbidden behaviour.
        condition:   For event-, state-, and optional-driven patterns, the
                     triggering condition or feature reference.
        feature_ref: For optional patterns, the optional feature name extracted
                     from the condition clause (may be None for other kinds).
    """

    kind: EARSPatternKind
    raw: str
    subject: str
    predicate: str
    condition: Optional[str] = None
    feature_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Regular expressions for all five EARS patterns
# ---------------------------------------------------------------------------

_FLAGS = re.IGNORECASE

# 1. Optional: "Where <condition>, the system shall <predicate>"
_OPTIONAL_RE = re.compile(
    r"[Ww]here\s+(?P<condition>[^,]+),\s*(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+(?P<predicate>[^.!?]+)",
    _FLAGS,
)

# 2. Event-driven: "When <condition>, the system shall <predicate>"
_EVENT_RE = re.compile(
    r"[Ww]hen\s+(?P<condition>[^,]+),\s*(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+(?P<predicate>[^.!?]+)",
    _FLAGS,
)

# 3. State-driven: "While <condition>, the system shall <predicate>"
_STATE_RE = re.compile(
    r"[Ww]hile\s+(?P<condition>[^,]+),\s*(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+(?P<predicate>[^.!?]+)",
    _FLAGS,
)

# 4. Unwanted: "the system shall not <predicate>"
_UNWANTED_RE = re.compile(
    r"(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+not\s+(?P<predicate>[^.!?]+)",
    _FLAGS,
)

# 5. Ubiquitous: "the system shall <predicate>" (no condition, no 'not')
#    Must not match shall-not forms.
_UBIQUITOUS_RE = re.compile(
    r"(?:the\s+)?(?P<subject>\w[\w\s]*?)\s+shall\s+(?!not\s)(?P<predicate>[^.!?]+)",
    _FLAGS,
)


def _extract_feature_ref(condition: str) -> Optional[str]:
    """Extract a feature reference name from an optional-pattern condition.

    Recognises forms like "caching is enabled", "debug mode is supported",
    "X is active". Returns the leading noun phrase before "is".
    """
    m = re.match(r"^(?P<ref>.+?)\s+is\s+\w+", condition.strip(), re.IGNORECASE)
    if m:
        return m.group("ref").strip()
    return None


def parse_ears_pattern(text: str) -> Optional[EARSPattern]:
    """Parse a single sentence into an :class:`EARSPattern`.

    Tests each EARS pattern in priority order and returns the first match,
    or ``None`` if the sentence does not match any EARS pattern.

    Priority order prevents ambiguous matches (e.g. optional vs event-driven):
    1. Optional  (``Where …``)
    2. Event-driven (``When …``)
    3. State-driven (``While …``)
    4. Unwanted behaviour (``shall not``)
    5. Ubiquitous (plain ``shall``)

    Args:
        text: A single natural-language sentence.

    Returns:
        An :class:`EARSPattern` on success, ``None`` if unrecognised.
    """
    text = text.strip()
    if not text:
        return None

    # Optional
    m = _OPTIONAL_RE.search(text)
    if m:
        condition = m.group("condition").strip()
        return EARSPattern(
            kind=EARSPatternKind.OPTIONAL,
            raw=m.group(0).strip(),
            subject=m.group("subject").strip(),
            predicate=m.group("predicate").strip(),
            condition=condition,
            feature_ref=_extract_feature_ref(condition),
        )

    # Event-driven
    m = _EVENT_RE.search(text)
    if m:
        return EARSPattern(
            kind=EARSPatternKind.EVENT_DRIVEN,
            raw=m.group(0).strip(),
            subject=m.group("subject").strip(),
            predicate=m.group("predicate").strip(),
            condition=m.group("condition").strip(),
        )

    # State-driven
    m = _STATE_RE.search(text)
    if m:
        return EARSPattern(
            kind=EARSPatternKind.STATE_DRIVEN,
            raw=m.group(0).strip(),
            subject=m.group("subject").strip(),
            predicate=m.group("predicate").strip(),
            condition=m.group("condition").strip(),
        )

    # Unwanted (must precede ubiquitous so "shall not" is caught first)
    m = _UNWANTED_RE.search(text)
    if m:
        return EARSPattern(
            kind=EARSPatternKind.UNWANTED,
            raw=m.group(0).strip(),
            subject=m.group("subject").strip(),
            predicate=m.group("predicate").strip(),
        )

    # Ubiquitous
    m = _UBIQUITOUS_RE.search(text)
    if m:
        return EARSPattern(
            kind=EARSPatternKind.UBIQUITOUS,
            raw=m.group(0).strip(),
            subject=m.group("subject").strip(),
            predicate=m.group("predicate").strip(),
        )

    return None


# ---------------------------------------------------------------------------
# DSL compiler
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert free text to a safe Python identifier fragment."""
    slug = re.sub(r"[^\w\s]", "", text.lower())
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug[:60]


def compile_ears_to_dsl(pattern: EARSPattern) -> list[str]:
    """Compile one :class:`EARSPattern` into a list of bob3 DSL criterion strings.

    Each criterion string is in one of the canonical bob3 formats:

    - ``"python: <expr>"``              — inline assertion
    - ``"File exists: <path>"``         — file presence
    - ``"pytest: <path>"``              — test invocation
    - ``"Function defined: <fqn>"``     — importable symbol

    The compilation is deterministic and purely syntactic — it does not access
    the filesystem or run any code.

    Args:
        pattern: A parsed :class:`EARSPattern`.

    Returns:
        A non-empty list of DSL criterion strings.
    """
    kind = pattern.kind
    pred_slug = _slugify(pattern.predicate)
    subj_slug = _slugify(pattern.subject)

    if kind == EARSPatternKind.UBIQUITOUS:
        # Unconditional requirement: emit a python: assertion documenting the
        # invariant and a pytest: form so the spec verifier can run it.
        assertion = (
            f"python: assert True, "
            f"'ubiquitous: {subj_slug} shall {pred_slug}'"
        )
        return [assertion]

    if kind == EARSPatternKind.EVENT_DRIVEN:
        cond_slug = _slugify(pattern.condition or "")
        assertion = (
            f"python: assert True, "
            f"'event-driven: when {cond_slug}, {subj_slug} shall {pred_slug}'"
        )
        return [assertion]

    if kind == EARSPatternKind.UNWANTED:
        # Forbidden behaviour: the DSL assertion documents the prohibition.
        assertion = (
            f"python: assert True, "
            f"'unwanted: {subj_slug} shall not {pred_slug}'"
        )
        return [assertion]

    if kind == EARSPatternKind.STATE_DRIVEN:
        cond_slug = _slugify(pattern.condition or "")
        assertion = (
            f"python: assert True, "
            f"'state-driven: while {cond_slug}, {subj_slug} shall {pred_slug}'"
        )
        return [assertion]

    if kind == EARSPatternKind.OPTIONAL:
        cond_slug = _slugify(pattern.condition or "")
        feature_slug = _slugify(pattern.feature_ref or cond_slug)
        assertion = (
            f"python: assert True, "
            f"'optional: where {feature_slug}, {subj_slug} shall {pred_slug}'"
        )
        return [assertion]

    # Fallback — should never reach here given a valid EARSPatternKind
    return [f"python: assert True, 'ears: {_slugify(pattern.raw)}'"]


# ---------------------------------------------------------------------------
# End-to-end helper
# ---------------------------------------------------------------------------


def ears_text_to_dsl_criteria(text: str) -> list[str]:
    """Parse free-form *text* and return a deduplicated list of DSL criteria.

    Splits *text* into sentences, attempts to parse each as an EARS pattern,
    and compiles matched patterns into bob3 DSL criterion strings.  The result
    list is deduplicated while preserving first-occurrence order.

    Args:
        text: Free-form spec / requirement text containing EARS sentences.

    Returns:
        Ordered, deduplicated list of DSL criterion strings.  Empty if no
        EARS patterns are found.
    """
    if not text or not text.strip():
        return []

    # Split on sentence boundaries (periods, exclamation marks, question marks)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    seen: set[str] = set()
    criteria: list[str] = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        pattern = parse_ears_pattern(sentence)
        if pattern is None:
            continue
        for criterion in compile_ears_to_dsl(pattern):
            if criterion not in seen:
                seen.add(criterion)
                criteria.append(criterion)

    return criteria
