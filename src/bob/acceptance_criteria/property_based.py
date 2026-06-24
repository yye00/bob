"""Property-based AC class (seventh AC grammar) for bob.acceptance_criteria.

Provides :class:`PropertyBasedAC` which wraps a parsed property AC and exposes
the Hypothesis test emitter.

Public API
----------
- ``PropertyBasedAC`` — wraps a ``property: <name> for <generator> assert <predicate>`` AC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bob.spec_quality.example_grammar import (
    PropertyAC,
    PropertyParseError,
    emit_hypothesis_test,
    parse_property_ac as _parse_property_ac,
    raises_on_malformed_property,
)


__all__ = [
    "PropertyBasedAC",
    "PropertyParseError",
]


@dataclass
class PropertyBasedAC:
    """Seventh AC grammar: ``property: <name> for <generator> assert <predicate>``.

    Wraps a :class:`~bob.spec_quality.example_grammar.PropertyAC` and provides:

    - ``hypothesis_test(seed=0)`` — emit a runnable Hypothesis test.
    - ``few_shot_snippet`` — one-line snippet for codegen few-shot context.

    Attributes:
        parsed:  The underlying :class:`PropertyAC` dataclass.
        raw:     Verbatim AC string.
    """

    parsed: PropertyAC
    raw: str

    @classmethod
    def from_string(cls, ac: str) -> "PropertyBasedAC":
        """Parse *ac* and return a :class:`PropertyBasedAC`.

        Args:
            ac: Raw AC string that must match the property grammar.

        Returns:
            A :class:`PropertyBasedAC` instance.

        Raises:
            PropertyParseError: When *ac* is malformed (missing ``for``/``assert``).
            ValueError: Alias — :class:`PropertyParseError` is a subclass.
        """
        parsed = raises_on_malformed_property(ac)
        return cls(parsed=parsed, raw=ac)

    @classmethod
    def try_parse(cls, ac: str | None) -> "PropertyBasedAC | None":
        """Try to parse *ac*; return ``None`` for non-property or empty strings.

        Args:
            ac: Raw AC string, or ``None``.

        Returns:
            A :class:`PropertyBasedAC` when *ac* matches the property grammar,
            else ``None``.

        Raises:
            PropertyParseError: When *ac* starts with ``property:`` but is malformed.
        """
        if ac is None:
            return None
        stripped = ac.strip()
        if not stripped:
            return None

        import re
        if re.match(r"^property\s*:", stripped, re.IGNORECASE):
            # Strict parse — raise on malformed property: ACs
            parsed = raises_on_malformed_property(stripped)
            return cls(parsed=parsed, raw=stripped)

        parsed = _parse_property_ac(stripped)
        if parsed is None:
            return None

        return cls(parsed=parsed, raw=stripped)

    def hypothesis_test(self, *, seed: int = 0) -> str:
        """Emit a runnable Hypothesis test for this property AC.

        Args:
            seed: Hypothesis database seed for reproducibility.

        Returns:
            Python source code string containing a ``@given``-decorated test.
        """
        return emit_hypothesis_test(self.parsed, seed=seed)

    @property
    def name(self) -> str:
        """Property name."""
        return self.parsed.name

    @property
    def generator(self) -> str:
        """Hypothesis generator expression."""
        return self.parsed.generator

    @property
    def predicate(self) -> str:
        """Boolean assertion expression."""
        return self.parsed.predicate

    @property
    def few_shot_snippet(self) -> str:
        """One-line snippet for codegen few-shot context."""
        return f"property: {self.name} for {self.generator} assert {self.predicate}"
