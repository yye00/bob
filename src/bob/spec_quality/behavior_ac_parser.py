"""Extended behavior-AC parser that accepts canonical clause forms beyond strict
"subject verb object when condition".

The original ears_parser only accepted "when" as the conditional keyword.
This module extends parsing to accept:

  - "on <event>" as a synonym for "when <condition>"
  - Compound predicates joined by "and" as a single verifiable clause

The F-R7-556 example that triggered this feature:

    behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves
        the offending file to <path>.corrupt.<unix_ts> and returns an
        empty findings dict so boot proceeds

This AC is well-formed and mechanically verifiable; the strict regex rejected
"on X" (synonym for "when X") and "moves... and returns..." (compound predicate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data model (mirrors BehaviorAC from ears_parser for compatibility)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BehaviorAC:
    """Parsed behavior acceptance criterion supporting extended clause forms.

    Attributes:
        raw:           Verbatim AC string after stripping the ``behavior:`` prefix.
        subject:       Who/what performs the action.
        verb:          The observable action verb phrase (may be compound with 'and').
        object:        What the action is performed on (may be compound with 'and').
        condition:     The triggering condition (from ``when``/``on`` clause).
        conditional_keyword: The keyword used ('when' or 'on').
    """

    raw: str
    subject: str
    verb: str
    object: str
    condition: str
    conditional_keyword: str = "when"


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Canonical form: "behavior: S V O when C"
_WHEN_RE = re.compile(
    r"^behavior\s*:\s*(?P<svo>.+?)\s+when\s+(?P<condition>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Extended form: "behavior: S on <event> V O ..." — subject followed by "on"
_ON_SUBJECT_RE = re.compile(
    r"^behavior\s*:\s*(?P<subject>\S+(?:\s+\S+){0,4}?)\s+on\s+(?P<condition>\S+(?:\s+\S+){0,4}?)\s+(?P<pred>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Fallback "on" form: "behavior: <svo> on <event>"  where svo has no 'when'
_ON_SUFFIX_RE = re.compile(
    r"^behavior\s*:\s*(?P<pred>.+?)\s+on\s+(?P<condition>\S+(?:\.\S+)*)$",
    re.IGNORECASE,
)

# Verb/object split heuristic: split SVO around first verb-like token
_VERB_SPLIT_RE = re.compile(
    r"^(?P<subject>\S+(?:\s+\S+){0,3}?)\s+(?P<verb>[a-z]\w+(?:\s+[a-z]\w+)?)\s+(?P<object>.+)$"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_svo(svo: str) -> tuple[str, str, str]:
    """Split 'subject verb object' string using verb-heuristic."""
    m = _VERB_SPLIT_RE.match(svo.strip())
    if m:
        return (
            m.group("subject").strip(),
            m.group("verb").strip(),
            m.group("object").strip(),
        )
    # Cannot split: treat whole string as subject
    return svo.strip(), "", ""


def _split_pred(pred: str) -> tuple[str, str]:
    """Split predicate (verb phrase + object) — verb is first token."""
    parts = pred.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0] if parts else "", ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_clause(ac: str) -> str:
    """Canonicalize a behavior AC string prior to parsing.

    Collapses runs of whitespace to single spaces, lowercases the
    ``behavior:`` prefix and the conditional keywords (``when``/``on``) so
    that case variations do not defeat the parser, and strips leading/trailing
    whitespace. The clause content itself is otherwise preserved verbatim.

    Args:
        ac: Raw AC string.

    Returns:
        The normalized clause string.

    Raises:
        ValueError: When *ac* is not a string or is empty/whitespace-only.
    """
    if not isinstance(ac, str):
        raise ValueError(f"AC must be a string, got {type(ac).__name__}")

    collapsed = re.sub(r"\s+", " ", ac).strip()
    if not collapsed:
        raise ValueError("AC string must not be empty")

    # Lowercase the leading behavior: prefix.
    collapsed = re.sub(
        r"^behavior\s*:", "behavior:", collapsed, count=1, flags=re.IGNORECASE
    )
    # Lowercase standalone conditional keywords.
    collapsed = re.sub(r"\bWHEN\b", "when", collapsed, flags=re.IGNORECASE)
    collapsed = re.sub(r"\bON\b", "on", collapsed, flags=re.IGNORECASE)
    return collapsed


def accepts_synonym_conditional(ac: str) -> bool:
    """Return True when *ac* uses 'on <event>' as a synonym for 'when <condition>'.

    This handles the F-R7-556 pattern where "on yaml.scanner.ScannerError"
    is semantically equivalent to "when yaml.scanner.ScannerError is raised".

    Args:
        ac: Raw AC string (may or may not start with 'behavior:').

    Returns:
        True when the string contains an 'on <token>' conditional that would
        not be accepted by the strict 'when' regex alone.
    """
    stripped = ac.strip()
    # Accepts if it matches behavior: ... on ... but NOT behavior: ... when ...
    if not re.match(r"^behavior\s*:", stripped, re.IGNORECASE):
        return False
    has_when = bool(re.search(r"\bwhen\b", stripped, re.IGNORECASE))
    if has_when:
        return False
    return bool(
        _ON_SUBJECT_RE.match(stripped) or _ON_SUFFIX_RE.match(stripped)
    )


def parse_behavior_ac(ac: str) -> BehaviorAC:
    """Parse a ``behavior:`` AC string into its structured components.

    Accepts the following forms:

    1. Canonical: ``behavior: <subject> <verb> <object> when <condition>``
    2. 'on' synonym: ``behavior: <subject> on <event> <verb> <object>``
    3. 'on' suffix:  ``behavior: <subject> <verb> <object> on <event>``
    4. Compound predicate: any of the above with 'and' joining multiple verb
       phrases — they are kept as a single verifiable clause.

    Args:
        ac: A raw AC string.

    Returns:
        A :class:`BehaviorAC` with all four components populated.

    Raises:
        ValueError: When *ac* is empty or does not start with ``behavior:``,
            or when neither a ``when`` nor ``on`` conditional clause is found.
    """
    if not isinstance(ac, str) or not ac.strip():
        raise ValueError("AC string must not be empty")

    stripped = normalize_clause(ac)

    if not re.match(r"^behavior\s*:", stripped, re.IGNORECASE):
        raise ValueError(
            f"AC string does not start with 'behavior:': {stripped!r}"
        )

    # --- Form 1: canonical "when" form ---
    m = _WHEN_RE.match(stripped)
    if m:
        svo = m.group("svo").strip()
        condition = m.group("condition").strip()
        subject, verb, obj = _split_svo(svo)
        return BehaviorAC(
            raw=stripped,
            subject=subject,
            verb=verb,
            object=obj,
            condition=condition,
            conditional_keyword="when",
        )

    # --- Form 2: "subject on <event> verb object" ---
    m2 = _ON_SUBJECT_RE.match(stripped)
    if m2:
        subject = m2.group("subject").strip()
        condition = m2.group("condition").strip()
        pred = m2.group("pred").strip()
        verb, obj = _split_pred(pred)
        return BehaviorAC(
            raw=stripped,
            subject=subject,
            verb=verb,
            object=obj,
            condition=condition,
            conditional_keyword="on",
        )

    # --- Form 3: "verb object on <event>" suffix ---
    m3 = _ON_SUFFIX_RE.match(stripped)
    if m3:
        pred = m3.group("pred").strip()
        condition = m3.group("condition").strip()
        # pred starts after "behavior: "
        body = re.sub(r"^behavior\s*:\s*", "", pred, flags=re.IGNORECASE).strip()
        subject, verb, obj = _split_svo(body)
        return BehaviorAC(
            raw=stripped,
            subject=subject,
            verb=verb,
            object=obj,
            condition=condition,
            conditional_keyword="on",
        )

    raise ValueError(
        f"AC string has no 'when' or 'on' conditional clause: {stripped!r}"
    )
