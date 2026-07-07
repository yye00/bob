"""Extended behavior-AC parser (hippy namespace).

Accepts canonical clause forms beyond the strict
``behavior: <subject> <verb> <object> when <condition>`` grammar that the
original ears_parser enforced. The strict regex rejected roughly 70% of
well-formed behavior ACs because it only accepted ``when`` as the conditional
keyword and refused compound predicates joined by ``and``.

This module additionally accepts:

  - ``on <event>`` as a synonym for ``when <condition>``
  - Compound predicates joined by ``and`` (kept as a single verifiable clause)

The F-R7-556 example that triggered this feature::

    behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves
        the offending file to <path>.corrupt.<unix_ts> and returns an
        empty findings dict so boot proceeds

That AC is well-formed and mechanically verifiable; the strict regex rejected
"on X" (synonym for "when X") and "moves... and returns..." (compound
predicate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BehaviorAC:
    """Parsed behavior acceptance criterion supporting extended clause forms.

    Attributes:
        raw:           Verbatim AC string after stripping surrounding whitespace.
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


# Canonical form: "behavior: S V O when C"
_WHEN_RE = re.compile(
    r"^behavior\s*:\s*(?P<svo>.+?)\s+when\s+(?P<condition>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Extended form: "behavior: S on <event> V O ..." — subject followed by "on"
_ON_SUBJECT_RE = re.compile(
    r"^behavior\s*:\s*(?P<subject>\S+(?:\s+\S+){0,4}?)\s+on\s+"
    r"(?P<condition>\S+(?:\s+\S+){0,4}?)\s+(?P<pred>.+)$",
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


def _split_svo(svo: str) -> tuple[str, str, str]:
    """Split a 'subject verb object' string using the verb heuristic."""
    m = _VERB_SPLIT_RE.match(svo.strip())
    if m:
        return (
            m.group("subject").strip(),
            m.group("verb").strip(),
            m.group("object").strip(),
        )
    return svo.strip(), "", ""


def _split_pred(pred: str) -> tuple[str, str]:
    """Split a predicate (verb phrase + object); the verb is the first token."""
    parts = pred.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0] if parts else "", ""


def accepts_synonym_conditional(ac: str) -> bool:
    """Return True when *ac* uses 'on <event>' as a synonym for 'when <condition>'.

    Handles the F-R7-556 pattern where "on yaml.scanner.ScannerError" is
    semantically equivalent to "when yaml.scanner.ScannerError is raised".

    Args:
        ac: Raw AC string.

    Returns:
        True when the string carries an 'on <token>' conditional that the strict
        'when' regex alone would not accept.
    """
    stripped = ac.strip()
    if not re.match(r"^behavior\s*:", stripped, re.IGNORECASE):
        return False
    if re.search(r"\bwhen\b", stripped, re.IGNORECASE):
        return False
    return bool(_ON_SUBJECT_RE.match(stripped) or _ON_SUFFIX_RE.match(stripped))


def parse_behavior_ac(ac: str) -> BehaviorAC:
    """Parse a ``behavior:`` AC string into its structured components.

    Accepts these forms:

    1. Canonical: ``behavior: <subject> <verb> <object> when <condition>``
    2. 'on' synonym: ``behavior: <subject> on <event> <verb> <object>``
    3. 'on' suffix:  ``behavior: <subject> <verb> <object> on <event>``
    4. Compound predicate: any of the above with 'and' joining multiple verb
       phrases — kept as a single verifiable clause.

    Args:
        ac: A raw AC string.

    Returns:
        A :class:`BehaviorAC` with all components populated.

    Raises:
        ValueError: When *ac* is empty, does not start with ``behavior:``, or
            has neither a ``when`` nor ``on`` conditional clause.
    """
    stripped = ac.strip()

    if not stripped:
        raise ValueError("AC string must not be empty")

    if not re.match(r"^behavior\s*:", stripped, re.IGNORECASE):
        raise ValueError(
            f"AC string does not start with 'behavior:': {stripped!r}"
        )

    m = _WHEN_RE.match(stripped)
    if m:
        subject, verb, obj = _split_svo(m.group("svo").strip())
        return BehaviorAC(
            raw=stripped,
            subject=subject,
            verb=verb,
            object=obj,
            condition=m.group("condition").strip(),
            conditional_keyword="when",
        )

    m2 = _ON_SUBJECT_RE.match(stripped)
    if m2:
        verb, obj = _split_pred(m2.group("pred").strip())
        return BehaviorAC(
            raw=stripped,
            subject=m2.group("subject").strip(),
            verb=verb,
            object=obj,
            condition=m2.group("condition").strip(),
            conditional_keyword="on",
        )

    m3 = _ON_SUFFIX_RE.match(stripped)
    if m3:
        body = re.sub(
            r"^behavior\s*:\s*", "", m3.group("pred").strip(), flags=re.IGNORECASE
        ).strip()
        subject, verb, obj = _split_svo(body)
        return BehaviorAC(
            raw=stripped,
            subject=subject,
            verb=verb,
            object=obj,
            condition=m3.group("condition").strip(),
            conditional_keyword="on",
        )

    raise ValueError(
        f"AC string has no 'when' or 'on' conditional clause: {stripped!r}"
    )


__all__ = ["BehaviorAC", "accepts_synonym_conditional", "parse_behavior_ac"]
