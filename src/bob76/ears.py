"""bob76.ears — Structured EARS-style behavior acceptance criteria.

Provides the sixth AC grammar:

    behavior: <subject> <verb> <object> when <condition>

At load time, ``parse_behavior_criterion`` parses the AC string into a
structured :class:`BehaviorCriterion` named tuple. The evaluator uses
those discrete fields to produce a targeted verification prompt rather than
relying on freeform prose.

Public API
----------
BehaviorCriterion
    Named-tuple (subject, verb, object_, condition) representing a parsed
    behavior AC.
parse_behavior_criterion(ac) -> BehaviorCriterion | None
    Parse a ``behavior:`` AC string. Returns a :class:`BehaviorCriterion`
    on success, or ``None`` for non-behavior ACs. Raises ``ValueError``
    for malformed behavior ACs (prefix present but ``when`` clause missing).
"""

from __future__ import annotations

import re
from typing import NamedTuple


class BehaviorCriterion(NamedTuple):
    """Parsed EARS-style behavior acceptance criterion.

    Attributes:
        subject:   Who/what performs the action.
        verb:      The observable action verb phrase.
        object_:   What the action is performed on.
        condition: The triggering condition (the ``when ...`` clause).
    """

    subject: str
    verb: str
    object_: str
    condition: str


_BEHAVIOR_PREFIX_RE = re.compile(r"^behavior\s*:", re.IGNORECASE)

_BEHAVIOR_FULL_RE = re.compile(
    r"^behavior\s*:\s*"
    r"(?P<subject>.+?)\s+"
    r"(?P<verb>\w+(?:\s+\w+){0,2}?)\s+"
    r"(?P<object>.+?)\s+"
    r"when\s+(?P<condition>.+)$",
    re.IGNORECASE,
)

_BEHAVIOR_SIMPLE_RE = re.compile(
    r"^behavior\s*:\s*(?P<svo>.+?)\s+when\s+(?P<condition>.+)$",
    re.IGNORECASE,
)

_VERB_SPLIT_RE = re.compile(
    r"^(?P<subject>\S+(?:\s+\S+){0,3}?)\s+(?P<verb>[a-z]\w+(?:\s+[a-z]\w+)?)\s+(?P<object>.+)$"
)


def parse_behavior_criterion(ac: str) -> BehaviorCriterion | None:
    """Parse a ``behavior:`` acceptance criterion into a structured tuple.

    Returns a :class:`BehaviorCriterion` if *ac* matches the behavior grammar,
    or ``None`` if *ac* does not start with the ``behavior:`` prefix (so
    callers can skip non-behavior AC strings transparently).

    Raises ``ValueError`` for ACs that have the ``behavior:`` prefix but are
    otherwise malformed (e.g. missing the required ``when`` clause).

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    The ``when`` keyword is mandatory; everything before it is split into
    (subject, verb, object) using a greedy verb-heuristic parse.

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        A :class:`BehaviorCriterion` when *ac* matches; ``None`` otherwise.

    Raises:
        ValueError: When *ac* starts with ``behavior:`` but lacks a ``when``
            clause or cannot be further parsed.
    """
    if not ac or not ac.strip():
        return None

    stripped = ac.strip()

    if not _BEHAVIOR_PREFIX_RE.match(stripped):
        return None

    if not re.search(r"\bwhen\b", stripped, re.IGNORECASE):
        raise ValueError(
            f"behavior: AC is missing the required 'when' clause: {stripped!r}"
        )

    m = _BEHAVIOR_FULL_RE.match(stripped)
    if m:
        return BehaviorCriterion(
            subject=m.group("subject").strip(),
            verb=m.group("verb").strip(),
            object_=m.group("object").strip(),
            condition=m.group("condition").strip(),
        )

    m2 = _BEHAVIOR_SIMPLE_RE.match(stripped)
    if not m2:
        raise ValueError(f"behavior: AC could not be parsed: {stripped!r}")

    svo = m2.group("svo").strip()
    condition = m2.group("condition").strip()

    m3 = _VERB_SPLIT_RE.match(svo)
    if m3:
        return BehaviorCriterion(
            subject=m3.group("subject").strip(),
            verb=m3.group("verb").strip(),
            object_=m3.group("object").strip(),
            condition=condition,
        )

    return BehaviorCriterion(
        subject=svo,
        verb="",
        object_="",
        condition=condition,
    )


__all__ = ["BehaviorCriterion", "parse_behavior_criterion"]
