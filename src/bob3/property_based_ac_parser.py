"""Seventh AC grammar: property-based AC parser — bob3 canonical entry point.

Exposes the two named functions required by the seventh-grammar ACs:

- ``parse_property_criterion`` — parse ``property: <name> for <generator> assert <predicate>``
- ``parse_key_example_variant`` — parse a ``key_example:`` sub-key entry (dict or string)

Both functions delegate to :mod:`bob3.spec_quality.example_grammar` for the
underlying grammar logic. The codegen agent uses returned objects as few-shot
context; the verifier emits one Hypothesis test per property and one
``@pytest.mark.parametrize`` test per key-example with ``seed=0``.

Boundary examples are required for any AC involving data transformation or
numeric range.

Public API
----------
- ``parse_property_criterion``  — canonical name for the property: grammar parser
- ``parse_key_example_variant`` — canonical name for the key_example: sub-key parser
- ``PropertyAC``                — re-exported for typed access
- ``KeyExample``                — re-exported for typed access
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.example_grammar import (  # noqa: F401
    KeyExample,
    PropertyAC,
    PropertyParseError,
    check_boundary_satisfied,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_key_example,
    parse_property_ac as _parse_property_ac,
    require_boundary_example,
    requires_boundary,
)

import re

__all__ = [
    "KeyExample",
    "PropertyAC",
    "PropertyParseError",
    "parse_key_example_variant",
    "parse_property_criterion",
]


def parse_property_criterion(ac: str | None) -> PropertyAC | None:
    """Parse a ``property:`` acceptance criterion into a :class:`PropertyAC`.

    Grammar::

        property: <name> for <generator> assert <predicate>

    When *ac* starts with ``property:`` it MUST be well-formed — a malformed
    property AC raises :class:`ValueError` rather than silently returning
    ``None``. This matches the ``parse_property_ac`` strict contract in
    :mod:`ac_grammar.property_based`.

    Non-property ACs (any other prefix) return ``None`` immediately.

    Args:
        ac: Raw AC string. ``None`` or empty strings return ``None``.

    Returns:
        A :class:`PropertyAC` when *ac* matches the property grammar, else
        ``None``.

    Raises:
        ValueError: When *ac* starts with ``property:`` but is malformed
                    (missing ``for <generator>`` or ``assert <predicate>`` clause,
                    or the predicate text is empty).

    Examples::

        >>> parse_property_criterion("property: non_negative for st.integers() assert x >= 0")
        PropertyAC(name='non_negative', generator='st.integers()', predicate='x >= 0', ...)

        >>> parse_property_criterion("pytest: tests/test_foo.py")
        None

        >>> parse_property_criterion(None)
        None
    """
    if ac is None:
        return None
    stripped = ac.strip()
    if not stripped:
        return None

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
        if not result.predicate.strip():
            raise ValueError(f"Property AC predicate is empty: {ac!r}")
        return result

    return _parse_property_ac(stripped)


def parse_key_example_variant(ac: dict[str, Any] | str | None) -> KeyExample | None:
    """Parse a ``key_example:`` sub-key entry from a behavior AC.

    Accepts two input forms:

    1. **Dict** with ``given`` and ``then`` keys::

           {"given": "x=5", "then": "result=25"}

    2. **String** in ``given: … then: …`` format::

           "given: x=5, then: result=25"

    ``None`` and empty strings/dicts are accepted without raising — they
    return ``None`` so callers may pass any value from a list without
    pre-filtering.

    A non-empty dict that is missing both ``given`` and ``then`` keys is
    considered malformed and raises :class:`ValueError`. This prevents silently
    accepting invalid input as a successful parse.

    Args:
        ac: Dict or string representation of a key-example entry, or ``None``.

    Returns:
        A :class:`KeyExample` when *ac* contains the required fields, else
        ``None``.

    Raises:
        ValueError: When *ac* is a non-empty dict missing both ``given`` and
                    ``then`` keys (clearly malformed, not merely empty).

    Examples::

        >>> parse_key_example_variant({"given": "x=5", "then": "result=25"})
        KeyExample(given='x=5', then='result=25', ...)

        >>> parse_key_example_variant("given: x=5, then: result=25")
        KeyExample(given='x=5', then='result=25', ...)

        >>> parse_key_example_variant(None)
        None

        >>> parse_key_example_variant("")
        None
    """
    if ac is None:
        return None

    if isinstance(ac, str) and not ac.strip():
        return None

    if isinstance(ac, dict) and not ac:
        return None

    if isinstance(ac, dict):
        has_given = "given" in ac or "Given" in ac
        has_then = "then" in ac or "Then" in ac
        if not has_given and not has_then:
            raise ValueError(
                f"Key-example dict is missing both 'given' and 'then' keys: {ac!r}"
            )

    return parse_key_example(ac)
