"""Sixth AC grammar: structured EARS-style ``behavior:`` acceptance criteria.

Grammar::

    behavior: <subject> <verb> <object> when <condition>

At load time :func:`parse_behavior_criterion` parses the AC string into a
structured :class:`~ears_criteria.BehaviorCriterion` tuple.  The evaluator
:func:`check_behavior` uses those discrete fields (subject/verb/object/
condition) to produce a targeted verification rather than relying on
freeform prose.

Public API
----------
parse_behavior_criterion(ac) -> BehaviorCriterion | None
    Parse a ``behavior:`` AC string into a structured tuple.  Returns
    ``None`` for non-behavior ACs; raises ``ValueError`` for malformed
    behavior ACs (prefix present but ``when`` clause missing/unparseable).
check_behavior(criterion, code_context=None) -> dict
    Evaluate a parsed :class:`BehaviorCriterion` (or a raw ``behavior:``
    string) against optional code context, returning a verdict dict.
"""

from __future__ import annotations

from typing import Any

from ears_criteria import BehaviorCriterion, parse_behavior
from ears.evaluator import check_behavior as _check_behavior


def parse_behavior_criterion(ac: str) -> BehaviorCriterion | None:
    """Parse a ``behavior:`` acceptance criterion into a structured tuple.

    Grammar::

        behavior: <subject> <verb> <object> when <condition>

    Args:
        ac: Raw acceptance-criterion string.

    Returns:
        A :class:`~ears_criteria.BehaviorCriterion` when *ac* matches the
        behavior grammar, or ``None`` when *ac* is empty or does not start
        with the ``behavior:`` prefix (so callers may skip non-behavior ACs
        transparently).

    Raises:
        ValueError: When *ac* starts with ``behavior:`` but is malformed
            (missing the required ``when`` clause or otherwise unparseable).

    Examples::

        >>> parse_behavior_criterion(
        ...     "behavior: parser returns BehaviorAC when AC matches grammar"
        ... )
        BehaviorCriterion(subject='parser', verb='returns', object_='BehaviorAC', condition='AC matches grammar')

        >>> parse_behavior_criterion("pytest: tests/test_foo.py")  # non-behavior AC
        None
    """
    return parse_behavior(ac)


def check_behavior(
    criterion: BehaviorCriterion | str,
    code_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a parsed behavior criterion against optional code context.

    Accepts either a pre-parsed :class:`~ears_criteria.BehaviorCriterion`
    or a raw ``behavior:`` string (which is parsed first).  Delegates the
    structured evaluation to :func:`ears.evaluator.check_behavior`.

    Args:
        criterion: A :class:`BehaviorCriterion` or a raw ``behavior:`` AC
            string to parse and check.
        code_context: Optional dict with a ``files`` mapping of path->content
            and/or ``test_results`` / ``diff`` entries used as evidence.

    Returns:
        A dict with keys ``verdict`` (bool), ``evidence`` (str),
        ``confidence`` (float) and ``prompt`` (str).

    Raises:
        ValueError: When *criterion* is a malformed ``behavior:`` string, or
            is not a :class:`BehaviorCriterion` / behavior-AC string.

    Examples::

        >>> res = check_behavior(
        ...     "behavior: parser returns BehaviorAC when AC matches grammar"
        ... )
        >>> res["verdict"]
        False
    """
    if isinstance(criterion, str):
        parsed = parse_behavior_criterion(criterion)
        if parsed is None:
            raise ValueError(
                f"check_behavior expected a behavior: AC string, got: {criterion!r}"
            )
        criterion = parsed
    elif not isinstance(criterion, BehaviorCriterion):
        raise ValueError(
            "check_behavior expects a BehaviorCriterion or behavior: string, "
            f"got {type(criterion).__name__!r}"
        )

    return _check_behavior(criterion, code_context)


__all__ = ["BehaviorCriterion", "parse_behavior_criterion", "check_behavior"]
