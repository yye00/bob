"""Seventh AC grammar: property-based and key-example acceptance criteria.

Public API for the ``ac_grammar`` package:

- ``parse_property_ac`` — parse ``property: <name> for <generator> assert <predicate>``
- ``parse_key_example_ac`` — parse ``key_example:`` sub-key entries (dict or string)

These functions delegate to :mod:`bob3.spec_quality.example_grammar` and expose
the same return types (:class:`~bob3.spec_quality.example_grammar.PropertyAC` and
:class:`~bob3.spec_quality.example_grammar.KeyExample`).

Grammar
-------
Property AC (seventh grammar)::

    property: <name> for <generator> assert <predicate>

Key-example sub-key (on any behavior AC)::

    key_example:
      given: <input values>
      then:  <expected output/state>

Both grammars are used by the verifier to emit Hypothesis tests and
``@pytest.mark.parametrize`` tests respectively.  The codegen agent uses
property specs and key-examples as few-shot context.
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.example_grammar import (
    KeyExample,
    PropertyAC,
    parse_key_example,
    parse_property_ac as _parse_property_ac,
)


def parse_property_ac(ac: str) -> PropertyAC | None:
    """Parse a ``property:`` acceptance criterion.

    Grammar::

        property: <name> for <generator> assert <predicate>

    Args:
        ac: Raw AC string.

    Returns:
        A :class:`~bob3.spec_quality.example_grammar.PropertyAC` when *ac*
        matches the property grammar, else ``None``.

    Raises:
        ValueError: When *ac* starts with ``property:`` but is malformed
                    (missing generator or predicate clause).

    Examples::

        >>> parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        PropertyAC(name='non_negative', ...)

        >>> parse_property_ac("pytest: tests/test_foo.py")  # non-property AC
        None
    """
    if ac is None:
        return None
    stripped = ac.strip()
    if not stripped:
        return None

    import re

    # If it starts with "property:" it MUST parse — raise on malformed input.
    if re.match(r"^property\s*:", stripped, re.IGNORECASE):
        if not re.search(r"\bfor\b", stripped, re.IGNORECASE):
            raise ValueError(
                f"Property AC is missing the 'for <generator>' clause: {ac!r}"
            )
        if not re.search(r"\bassert\b", stripped, re.IGNORECASE):
            raise ValueError(
                f"Property AC is missing the 'assert <predicate>' clause: {ac!r}"
            )
        result = _parse_property_ac(stripped)
        if result is None:
            raise ValueError(f"Property AC could not be parsed (malformed): {ac!r}")
        return result

    return _parse_property_ac(stripped)


def parse_key_example_ac(ac: dict[str, Any] | str | None) -> KeyExample | None:
    """Parse a ``key_example:`` sub-key entry from a behavior AC.

    Accepts two input forms:

    1. **Dict** with ``given`` and ``then`` keys::

           {"given": "x=5", "then": "result=25"}

    2. **String** in ``given: … then: …`` format::

           "given: x=5, then: result=25"

    Args:
        ac: Dict or string representation of a key-example entry.  ``None``
            is accepted and returns ``None`` (so callers may pass any value
            from a list without pre-filtering).

    Returns:
        A :class:`~bob3.spec_quality.example_grammar.KeyExample` when *ac*
        contains the required fields, else ``None``.

    Raises:
        ValueError: When *ac* is a non-empty dict that is missing both
                    ``given`` and ``then`` keys (i.e. the entry is clearly
                    intended as a key-example but is malformed).

    Examples::

        >>> parse_key_example_ac({"given": "x=5", "then": "result=25"})
        KeyExample(given='x=5', then='result=25', ...)

        >>> parse_key_example_ac("given: x=5, then: result=25")
        KeyExample(given='x=5', then='result=25', ...)

        >>> parse_key_example_ac(None)
        None

        >>> parse_key_example_ac("")
        None
    """
    if ac is None:
        return None

    if isinstance(ac, str) and not ac.strip():
        return None

    if isinstance(ac, dict) and not ac:
        return None

    # Validate that a dict-form entry has the required keys; raise on malformed.
    if isinstance(ac, dict):
        has_given = "given" in ac or "Given" in ac
        has_then = "then" in ac or "Then" in ac
        if not has_given and not has_then:
            raise ValueError(
                f"Key-example dict is missing both 'given' and 'then' keys: {ac!r}"
            )

    return parse_key_example(ac)
