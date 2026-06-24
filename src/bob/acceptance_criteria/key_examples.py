"""Key-example AC class for bob.acceptance_criteria.

Provides :class:`KeyExampleAC` which wraps parsed key-example entries attached
to a behavior AC and exposes:

- ``parametrize_test(seed=0)`` — emit a ``@pytest.mark.parametrize`` test.
- ``boundary_satisfied`` — whether boundary requirements are met.
- ``few_shot_snippet`` — text block for codegen few-shot context.

Public API
----------
- ``KeyExampleAC`` — wraps key-example entries for a behavior AC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bob.spec_quality.example_grammar import (
    BoundaryRequirement,
    KeyExample,
    check_boundary_satisfied,
    emit_parametrize_test,
    parse_key_example,
    requires_boundary,
)


__all__ = [
    "KeyExampleAC",
    "KeyExample",
]


@dataclass
class KeyExampleAC:
    """Key-example sub-key on a behavior AC.

    Wraps one or more :class:`~bob.spec_quality.example_grammar.KeyExample`
    entries parsed from the ``key_example:`` sub-key of a behavior AC.

    Attributes:
        examples:     List of parsed :class:`KeyExample` objects.
        behavior_ac:  Raw behavior AC string (used for boundary checking).
    """

    examples: list[KeyExample] = field(default_factory=list)
    behavior_ac: str = ""

    @classmethod
    def from_entries(
        cls,
        entries: list[Any] | None,
        *,
        behavior_ac: str = "",
        strict: bool = False,
    ) -> "KeyExampleAC":
        """Parse *entries* into a :class:`KeyExampleAC`.

        Args:
            entries:     List of raw key-example entries (dicts or strings).
            behavior_ac: The behavior AC string for boundary checking.
            strict:      When ``True``, raise :class:`ValueError` for non-empty
                         dicts missing both ``given`` and ``then`` keys.

        Returns:
            A :class:`KeyExampleAC` instance.

        Raises:
            ValueError: When *strict* is ``True`` and a dict entry is malformed.
        """
        parsed: list[KeyExample] = []
        for entry in (entries or []):
            if entry is None:
                continue
            if strict and isinstance(entry, dict) and entry:
                has_given = "given" in entry or "Given" in entry
                has_then = "then" in entry or "Then" in entry
                if not has_given and not has_then:
                    raise ValueError(
                        f"Key-example dict is missing both 'given' and 'then' keys: {entry!r}"
                    )
            ex = parse_key_example(entry)
            if ex is not None:
                parsed.append(ex)

        return cls(examples=parsed, behavior_ac=behavior_ac)

    def parametrize_test(self, *, seed: int = 0, test_name: str = "test_key_examples") -> str:
        """Emit a ``@pytest.mark.parametrize`` test from key-examples.

        Args:
            seed:      Seed value stored in a comment for reproducibility.
            test_name: Name for the generated test function.

        Returns:
            Python source code string, or ``""`` when no examples are present.
        """
        return emit_parametrize_test(self.examples, test_name=test_name, seed=seed)

    @property
    def boundary_requirement(self) -> BoundaryRequirement:
        """Boundary requirement result for this AC."""
        if not self.behavior_ac:
            return requires_boundary("")
        return check_boundary_satisfied(self.behavior_ac, self.examples)

    @property
    def boundary_satisfied(self) -> bool:
        """``True`` when boundary requirements are met (or not required)."""
        return self.boundary_requirement.satisfied

    @property
    def boundary_required(self) -> bool:
        """``True`` when this AC requires boundary key-examples."""
        return self.boundary_requirement.required

    @property
    def few_shot_snippet(self) -> str:
        """Text block for codegen few-shot context."""
        if not self.examples:
            return ""
        lines = ["key_examples:"]
        for ex in self.examples:
            lines.append(f"  given: {ex.given}, then: {ex.then}")
        return "\n".join(lines)
