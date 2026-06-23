"""EARS-style behavior acceptance criteria for bob3.

Sixth AC grammar::

    behavior: <subject> <verb> <object> when <condition>

At load time, ``parse_behavior_criteria`` parses the AC string into a
structured :class:`EARSBehaviorCriterion` named-tuple. The evaluator uses
those discrete fields to produce a targeted verification prompt rather
than relying on freeform prose.

Also provides ``key_example`` for attaching given/then parametrize examples
to behavior ACs. The verifier emits one ``@pytest.mark.parametrize`` test
per key-example with ``seed=0`` for reproducibility.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple


class EARSBehaviorCriterion(NamedTuple):
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

_BEHAVIOR_SIMPLE_RE = re.compile(
    r"^behavior\s*:\s*(?P<svo>.+?)\s+when\s+(?P<condition>.+)$",
    re.IGNORECASE,
)

_VERB_SPLIT_RE = re.compile(
    r"^(?P<subject>\S+(?:\s+\S+){0,3}?)\s+(?P<verb>[a-z]\w+(?:\s+[a-z]\w+)?)\s+(?P<object>.+)$"
)


def parse_behavior_criteria(ac: str) -> EARSBehaviorCriterion | None:
    """Parse a ``behavior:`` acceptance criterion into a structured tuple.

    Returns an :class:`EARSBehaviorCriterion` if *ac* matches the behavior
    grammar, or ``None`` if *ac* does not start with the ``behavior:`` prefix.

    Raises ``ValueError`` for ACs that have the ``behavior:`` prefix but are
    otherwise malformed (e.g. missing the required ``when`` clause).

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        An :class:`EARSBehaviorCriterion` when *ac* matches; ``None`` otherwise.

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

    m2 = _BEHAVIOR_SIMPLE_RE.match(stripped)
    if not m2:
        raise ValueError(f"behavior: AC could not be parsed: {stripped!r}")

    svo = m2.group("svo").strip()
    condition = m2.group("condition").strip()

    m3 = _VERB_SPLIT_RE.match(svo)
    if m3:
        return EARSBehaviorCriterion(
            subject=m3.group("subject").strip(),
            verb=m3.group("verb").strip(),
            object_=m3.group("object").strip(),
            condition=condition,
        )

    return EARSBehaviorCriterion(
        subject=svo,
        verb="",
        object_="",
        condition=condition,
    )


def key_example(
    given: Any,
    then: Any,
) -> dict[str, Any]:
    """Attach a given/then key-example to a behavior AC.

    Key-examples are used by the verifier to emit
    ``@pytest.mark.parametrize`` tests with ``seed=0`` for reproducibility.
    The codegen agent also uses them as few-shot context.

    Args:
        given: Input value(s) — any Python object; stored as-is.
        then:  Expected output or state — any Python object.

    Returns:
        A dict with ``given`` and ``then`` keys suitable for passing to
        :func:`bob3.spec_quality.example_grammar.parse_key_example`.

    Raises:
        ValueError: When *given* or *then* is ``None`` (both are required).

    Examples::

        >>> key_example(given="x=5", then="result=25")
        {'given': 'x=5', 'then': 'result=25'}
    """
    if given is None:
        raise ValueError("key_example: 'given' must not be None")
    if then is None:
        raise ValueError("key_example: 'then' must not be None")
    return {"given": given, "then": then}


__all__ = ["EARSBehaviorCriterion", "key_example", "parse_behavior_criteria"]
