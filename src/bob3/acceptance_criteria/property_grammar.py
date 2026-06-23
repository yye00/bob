"""Property-based AC grammar (seventh AC grammar).

Parses the ``property: <name> for <generator> assert <predicate>`` form
and exposes it as the ``parse_property_ac`` public function.

The parsed :class:`~bob3.spec_quality.example_grammar.PropertyAC` is used by:

- The codegen agent as few-shot context.
- The verifier, which emits one Hypothesis test per property AC.

Public API
----------
- ``parse_property_ac`` — parse a property: AC string.
"""

from __future__ import annotations

from bob3.spec_quality.example_grammar import (
    PropertyAC,
    PropertyParseError,
    parse_property_ac as _parse_property_ac,
    raises_on_malformed_property,
)

__all__ = [
    "PropertyAC",
    "PropertyParseError",
    "parse_property_ac",
    "raises_on_malformed_property",
]


def parse_property_ac(ac: str | None) -> PropertyAC | None:
    """Parse a ``property:`` acceptance criterion.

    Grammar::

        property: <name> for <generator> assert <predicate>

    Delegates to :func:`bob3.spec_quality.example_grammar.parse_property_ac`.
    Extends its behaviour:

    - Accepts ``None`` and returns ``None`` (safe for iteration over AC lists).
    - Accepts empty strings and returns ``None``.
    - Raises :class:`~bob3.spec_quality.example_grammar.PropertyParseError`
      (a :class:`ValueError` subclass) when the string starts with
      ``property:`` but the grammar is violated (missing generator or predicate).

    Args:
        ac: Raw AC string, or ``None``.

    Returns:
        A :class:`~bob3.spec_quality.example_grammar.PropertyAC` when *ac*
        matches the property grammar, else ``None``.

    Raises:
        PropertyParseError: When the string starts with ``property:`` but is
                            malformed (missing ``for``/``assert`` clauses or
                            empty predicate/generator).

    Examples::

        >>> parse_property_ac("property: non_negative for st.integers() assert x >= 0")
        PropertyAC(name='non_negative', generator='st.integers()', predicate='x >= 0', ...)

        >>> parse_property_ac("pytest: tests/test_foo.py")
        None

        >>> parse_property_ac(None)
        None
    """
    if ac is None:
        return None
    stripped = ac.strip()
    if not stripped:
        return None

    import re

    if re.match(r"^property\s*:", stripped, re.IGNORECASE):
        # Must succeed or raise — delegate to the strict form
        return raises_on_malformed_property(stripped)

    return _parse_property_ac(stripped)
