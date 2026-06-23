"""EARS-style behavior acceptance criteria — sixth AC grammar.

Provides the sixth AC grammar:

    behavior: <subject> <verb> <object> when <condition>

At load time, ``parse_behavior_criterion`` parses the AC string into a
structured :class:`EarsBehaviorCriterion` named-tuple. The evaluator uses
those discrete fields to produce a targeted verification prompt rather than
relying on freeform prose.

Public API
----------
EarsBehaviorCriterion
    Named-tuple (subject, verb, object_, condition) representing a parsed
    behavior AC. Alias for :class:`ears_criteria.BehaviorCriterion`.
parse_behavior_criterion(ac) -> EarsBehaviorCriterion | None
    Parse a ``behavior:`` AC string into a structured tuple.
    Returns ``None`` for non-behavior ACs; raises ``ValueError`` for
    malformed behavior ACs (prefix present but ``when`` clause missing).
"""

from __future__ import annotations

from bob3.ears_criteria import BehaviorCriterion, parse_behavior_criterion as _parse_behavior_criterion

#: Public name for the parsed behavior criterion tuple (lowercase 's' in Ears).
EarsBehaviorCriterion = BehaviorCriterion


def parse_behavior_criterion(ac: str) -> EarsBehaviorCriterion | None:
    """Parse a ``behavior:`` acceptance criterion into a structured tuple.

    Returns an :class:`EarsBehaviorCriterion` if *ac* matches the behavior
    grammar, or ``None`` if *ac* does not start with the ``behavior:`` prefix.

    Raises ``ValueError`` for ACs that have the ``behavior:`` prefix but are
    otherwise malformed (e.g. missing the required ``when`` clause).

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    Args:
        ac: A raw acceptance-criterion string.

    Returns:
        An :class:`EarsBehaviorCriterion` when *ac* matches; ``None`` otherwise.

    Raises:
        ValueError: When *ac* starts with ``behavior:`` but lacks a ``when``
            clause or cannot be further parsed.

    Examples::

        >>> parse_behavior_criterion("behavior: parser returns BehaviorAC when AC matches grammar")
        EarsBehaviorCriterion(subject='parser', verb='returns', object_='BehaviorAC',
                              condition='AC matches grammar')

        >>> parse_behavior_criterion("pytest: tests/test_foo.py")
        None
    """
    return _parse_behavior_criterion(ac)


__all__ = ["EarsBehaviorCriterion", "parse_behavior_criterion"]
