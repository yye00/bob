"""bob3.property_ac — property-based AC registration and Hypothesis test generation.

Provides the public API for the seventh AC grammar:

    property: <name> for <generator> assert <predicate>

Functions:
- ``register_property_assertion`` — register a property AC into a registry dict.
- ``generate_hypothesis_tests``   — generate Hypothesis test source for all registered properties.
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.example_grammar import (
    PropertyAC,
    emit_hypothesis_test,
    parse_property_ac,
    raises_on_malformed_property,
)

__all__ = [
    "register_property_assertion",
    "generate_hypothesis_tests",
    "PropertyAC",
]


def register_property_assertion(
    registry: dict[str, PropertyAC],
    ac_string: str,
    *,
    seed: int = 0,
) -> PropertyAC:
    """Parse and register a property AC into *registry*.

    The seventh AC grammar is::

        property: <name> for <generator> assert <predicate>

    Args:
        registry:  Mutable dict mapping property name to :class:`PropertyAC`.
        ac_string: Raw property AC string.
        seed:      Seed stored on the registry entry for reproducibility.

    Returns:
        The parsed :class:`PropertyAC`.

    Raises:
        ValueError: When *ac_string* starts with ``property:`` but is malformed,
                    or does not match the property grammar at all.
    """
    if not ac_string or not ac_string.strip():
        raise ValueError(f"Property AC string must not be empty: {ac_string!r}")

    prop = raises_on_malformed_property(ac_string)
    registry[prop.name] = prop
    return prop


def generate_hypothesis_tests(
    registry: dict[str, PropertyAC],
    *,
    seed: int = 0,
) -> dict[str, str]:
    """Generate Hypothesis test source for every property in *registry*.

    Args:
        registry: Dict mapping property name to :class:`PropertyAC`.
        seed:     Hypothesis seed for reproducibility (default ``0``).

    Returns:
        Dict mapping property name to generated Python source code string.
        An empty registry returns an empty dict.
    """
    return {
        name: emit_hypothesis_test(prop, seed=seed)
        for name, prop in registry.items()
    }
