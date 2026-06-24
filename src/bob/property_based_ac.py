"""Seventh AC grammar: property-based acceptance criteria for bob.

Public API:
- ``parse_property_ac`` — parse ``property: <name> for <generator> assert <predicate>``
- ``parse_key_example_ac`` — parse ``key_example:`` sub-key entries (dict or string)

Delegates to :mod:`bob.spec_quality.example_grammar` for the actual parsing
and emitting logic. This module is the canonical ``bob``-namespaced entry
point for the seventh AC grammar.

Grammar::

    property: <name> for <generator> assert <predicate>

The verifier emits one Hypothesis test per property AC. The codegen agent
uses the property spec as few-shot context.
"""

from __future__ import annotations

from typing import Any, Sequence

from bob.spec_quality.example_grammar import (  # noqa: F401
    KeyExample,
    PropertyAC,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_key_example,
    parse_property_ac as _parse_property_ac,
)


def parse_key_example_ac(ac: dict | str | None) -> "KeyExample | None":
    """Parse a ``key_example:`` sub-key entry.

    Delegates to :func:`~bob.spec_quality.example_grammar.parse_key_example`.
    This is the canonical ``bob``-namespaced entry point for parsing
    ``key_example:`` sub-key entries in behavior ACs.

    Args:
        ac: A dict with ``given``/``then`` keys, a plain string, or ``None``.

    Returns:
        A :class:`~bob.spec_quality.example_grammar.KeyExample` when *ac*
        can be parsed, else ``None``.

    Raises:
        ValueError: When *ac* is a dict that lacks the required ``given``/``then``
                    keys (i.e. is not a valid key_example entry).
    """
    return parse_key_example(ac)

import re


def parse_property_ac(ac: str | None) -> PropertyAC | None:
    """Parse a ``property:`` acceptance criterion.

    Grammar::

        property: <name> for <generator> assert <predicate>

    Args:
        ac: Raw AC string. ``None`` or empty strings return ``None``.

    Returns:
        A :class:`~bob.spec_quality.example_grammar.PropertyAC` when *ac*
        matches the property grammar, else ``None``.

    Raises:
        ValueError: When *ac* starts with ``property:`` but is malformed
                    (missing ``for <generator>`` or ``assert <predicate>`` clause).

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


def emit_hypothesis_tests(
    properties: Sequence[PropertyAC | str | None],
    *,
    seed: int = 0,
) -> list[str]:
    """Emit one Hypothesis test source string per property AC.

    This is the plural form of :func:`emit_hypothesis_test`. The verifier
    calls this to produce one ``@given``-decorated test per property in a
    feature's AC list.

    Args:
        properties: Iterable of property ACs.  Each element may be a
                    :class:`PropertyAC` dataclass, a raw property AC string
                    (which is parsed first), or ``None`` (skipped).
        seed:       Hypothesis seed stored in the ``@settings`` decorator for
                    reproducibility.  Defaults to 0.

    Returns:
        A list of Python source strings, one per successfully parsed property.
        Empty when *properties* is empty or all entries are ``None`` / invalid.
    """
    results: list[str] = []
    for prop in properties:
        if prop is None:
            continue
        if isinstance(prop, str):
            try:
                prop = parse_property_ac(prop)
            except ValueError:
                continue
        if prop is None:
            continue
        results.append(emit_hypothesis_test(prop, seed=seed))
    return results


def generate_hypothesis_test(prop: "PropertyAC", *, seed: int = 0) -> str:
    """Generate a runnable Hypothesis test for a :class:`PropertyAC`.

    Alias for :func:`emit_hypothesis_test` satisfying the AC function name
    requirement: ``bob.property_based_ac.generate_hypothesis_test``.

    Args:
        prop: A parsed :class:`~bob.spec_quality.example_grammar.PropertyAC`.
        seed: Hypothesis seed for reproducibility (default ``0``).

    Returns:
        Python source code string for a single ``@given``-decorated Hypothesis test.
    """
    return emit_hypothesis_test(prop, seed=seed)


def generate_parametrized_pytest(
    examples: "list[KeyExample]",
    *,
    test_name: str = "test_key_examples",
    seed: int = 0,
) -> str:
    """Generate a ``@pytest.mark.parametrize`` test from key-examples.

    Alias for :func:`emit_parametrize_test` satisfying the AC function name
    requirement: ``bob.property_based_ac.generate_parametrized_pytest``.

    Args:
        examples:  List of :class:`~bob.spec_quality.example_grammar.KeyExample` objects.
        test_name: Name for the generated test function.
        seed:      Seed stored in a comment for reproducibility tracking.

    Returns:
        Python source code string for a ``@pytest.mark.parametrize`` test,
        or an empty string when *examples* is empty.
    """
    return emit_parametrize_test(examples, test_name=test_name, seed=seed)


__all__ = [
    "KeyExample",
    "PropertyAC",
    "emit_hypothesis_test",
    "emit_hypothesis_tests",
    "generate_hypothesis_test",
    "generate_parametrized_pytest",
    "parse_key_example_ac",
    "parse_property_ac",
]
