"""Behavior AC extensions: KeyExampleVariant and property-based sub-grammar.

Exposes :class:`KeyExampleVariant` — the typed representation of a behavior AC
with an attached ``key_example:`` sub-key — and re-exports the public AC-parsing
helpers from the canonical sub-modules.

Public API
----------
- ``KeyExampleVariant`` — wraps a behavior AC + its key-example entries.
- ``parse_property_ac``  — seventh AC grammar: ``property: <name> for <generator> assert <predicate>``
- ``parse_key_example``  — parse one ``key_example:`` entry (dict or string).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bob3.spec_quality.example_grammar import (
    BoundaryRequirement,
    KeyExample,
    PropertyAC,
    check_boundary_satisfied,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_key_example,
    parse_property_ac,
    requires_boundary,
)


@dataclass
class KeyExampleVariant:
    """A behavior AC annotated with ``key_example:`` sub-key entries.

    This is the typed representation of the key-example variant described in
    feature "Key-examples / property-based AC variant".  The verifier emits
    one ``@pytest.mark.parametrize`` test per :class:`KeyExample` in
    ``examples``.  The codegen agent uses ``few_shot_context`` as a prompt
    prefix.

    Attributes:
        behavior_ac:  Raw behavior AC string (EARS or MUST form).
        examples:     Parsed key-example entries attached to *behavior_ac*.
        property_ac:  Optional seventh-grammar property AC associated with
                      *behavior_ac*.
    """

    behavior_ac: str
    examples: list[KeyExample] = field(default_factory=list)
    property_ac: PropertyAC | None = None

    @classmethod
    def from_ac_dict(
        cls,
        behavior_ac: str,
        key_examples: list[Any] | None = None,
        property_ac_str: str | None = None,
    ) -> "KeyExampleVariant":
        """Build a :class:`KeyExampleVariant` from raw AC dict values.

        Args:
            behavior_ac:    Raw behavior AC string.
            key_examples:   List of raw key-example entries (dicts or strings).
            property_ac_str: Optional raw property AC string.

        Returns:
            A :class:`KeyExampleVariant` instance.

        Raises:
            ValueError: When *property_ac_str* starts with ``property:`` but is
                        malformed (missing ``for``/``assert`` clauses).
        """
        parsed_examples: list[KeyExample] = []
        for entry in (key_examples or []):
            if entry is None:
                continue
            ex = parse_key_example(entry)
            if ex is not None:
                parsed_examples.append(ex)

        parsed_property: PropertyAC | None = None
        if property_ac_str is not None:
            parsed_property = parse_property_ac(property_ac_str)

        return cls(
            behavior_ac=behavior_ac,
            examples=parsed_examples,
            property_ac=parsed_property,
        )

    # ------------------------------------------------------------------
    # Emission helpers
    # ------------------------------------------------------------------

    def parametrize_test(
        self,
        *,
        seed: int = 0,
        test_name: str = "test_key_examples",
    ) -> str:
        """Emit a ``@pytest.mark.parametrize`` test from the key-examples.

        Args:
            seed:      Reproducibility seed stored in a comment.
            test_name: Name for the generated test function.

        Returns:
            Python source code string, or ``""`` when no examples are present.
        """
        return emit_parametrize_test(self.examples, test_name=test_name, seed=seed)

    def hypothesis_test(self, *, seed: int = 0) -> str:
        """Emit a Hypothesis test from the property AC (if present).

        Args:
            seed: Hypothesis database seed for reproducibility.

        Returns:
            Python source code string, or ``""`` when no property AC is set.
        """
        if self.property_ac is None:
            return ""
        return emit_hypothesis_test(self.property_ac, seed=seed)

    # ------------------------------------------------------------------
    # Boundary checking
    # ------------------------------------------------------------------

    @property
    def boundary_requirement(self) -> BoundaryRequirement:
        """Boundary requirement result for this behavior AC."""
        return check_boundary_satisfied(self.behavior_ac, self.examples)

    @property
    def boundary_satisfied(self) -> bool:
        """``True`` when boundary requirements are met (or not required)."""
        return self.boundary_requirement.satisfied

    @property
    def boundary_required(self) -> bool:
        """``True`` when this AC requires boundary key-examples."""
        return self.boundary_requirement.required

    # ------------------------------------------------------------------
    # Few-shot context
    # ------------------------------------------------------------------

    @property
    def few_shot_context(self) -> str:
        """Text snippet for codegen few-shot context."""
        parts: list[str] = []
        if self.property_ac is not None:
            parts.append(
                f"property: {self.property_ac.name}"
                f" for {self.property_ac.generator}"
                f" assert {self.property_ac.predicate}"
            )
        if self.examples:
            parts.append("key_examples:")
            for ex in self.examples:
                parts.append(f"  given: {ex.given}, then: {ex.then}")
        return "\n".join(parts)


__all__ = [
    "KeyExample",
    "KeyExampleVariant",
    "PropertyAC",
    "emit_hypothesis_test",
    "emit_parametrize_test",
    "parse_key_example",
    "parse_property_ac",
]
