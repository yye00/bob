"""EARS-style behavior acceptance criterion parser for bob3.

Sixth AC grammar alongside File exists, Function defined, Class defined,
pytest, and integration:

    behavior: <subject> <verb> <object> when <condition>

``parse_behavior_ac`` extracts the structured (subject, verb, object,
condition) tuple from a raw AC string. ``BehaviorTuple`` is the NamedTuple
holding the parsed fields.

At load time the AC string is parsed into a structured tuple; the evaluator
uses those discrete fields to produce a targeted verification prompt rather
than relying on freeform prose.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class BehaviorTuple(NamedTuple):
    """Parsed EARS-style behavior acceptance criterion.

    Attributes:
        subject:   Who/what performs the action.
        verb:      The observable action verb phrase.
        object_:   What the action is performed on.
        condition: The triggering condition (the ``when …`` clause).
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


def parse_behavior_ac(ac: str) -> BehaviorTuple | None:
    """Parse a ``behavior:`` acceptance criterion into a structured tuple.

    Returns a :class:`BehaviorTuple` if *ac* matches the behavior grammar,
    or ``None`` if *ac* does not start with the ``behavior:`` prefix.

    Raises ``ValueError`` for ACs that have the ``behavior:`` prefix but are
    otherwise malformed (e.g. missing the required ``when`` clause).

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        A :class:`BehaviorTuple` when *ac* matches; ``None`` otherwise.

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
        return BehaviorTuple(
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
        return BehaviorTuple(
            subject=m3.group("subject").strip(),
            verb=m3.group("verb").strip(),
            object_=m3.group("object").strip(),
            condition=condition,
        )

    return BehaviorTuple(
        subject=svo,
        verb="",
        object_="",
        condition=condition,
    )


def evaluate_behavior_ac(bt: BehaviorTuple) -> str:
    """Produce a structured grading prompt for a parsed :class:`BehaviorTuple`.

    Returns a targeted, structured prompt fragment that instructs the
    independent grader to verify the exact subject-verb-object under the
    exact condition, rather than consulting freeform prose.

    Args:
        bt: A parsed behavior acceptance criterion from :func:`parse_behavior_ac`.

    Returns:
        A multi-line string with a structured grading question.
    """
    subject = bt.subject or "(unspecified subject)"
    verb = bt.verb or "(unspecified verb)"
    obj = bt.object_ or "(unspecified object)"
    condition = bt.condition

    return (
        "### Behavior AC check\n"
        f"Does **{subject}** **{verb}** **{obj}** when **{condition}**?\n\n"
        "Verify each part specifically:\n"
        f"- Subject `{subject}`: identify the code entity responsible for this action.\n"
        f"- Verb `{verb}`: confirm the action is actually performed (not mocked, stubbed, or no-op).\n"
        f"- Object `{obj}`: confirm the target entity is affected, produced, or returned.\n"
        f"- Condition `when {condition}`: confirm the behavior is triggered only/specifically under this condition.\n\n"
        "Answer YES/NO for each part above, then give an overall PASS or FAIL "
        "for this criterion with a one-sentence rationale and a `file:line` reference."
    )


#: Alias required by AC "Function defined: bob3.ears_parser.parse_behavior_criterion".
parse_behavior_criterion = parse_behavior_ac

__all__ = ["BehaviorTuple", "parse_behavior_ac", "parse_behavior_criterion", "evaluate_behavior_ac"]
