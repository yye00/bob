"""Key-examples / property-based AC variant — seventh AC grammar integration.

Adds two extensions to the existing six AC grammars:

1. **Property AC** (seventh grammar)::

       property: <name> for <generator> assert <predicate>

   ``key_examples_property_based_ac_variant`` parses this form and emits a
   runnable Hypothesis test.  The property spec is also returned as few-shot
   context for the codegen agent.

2. **Key-example sub-key** on any behavior AC::

       key_example:
         given: <input values>
         then:  <expected output/state>

   One ``@pytest.mark.parametrize`` test is emitted per key-example, with
   ``seed=0`` for reproducibility.

Boundary examples are *required* for any AC involving data transformation or
a numeric range.  ``boundary_required`` and ``boundary_satisfied`` keys in the
returned dict communicate this to the verifier.

Public API
----------
- ``key_examples_property_based_ac_variant`` — primary integration function
"""

from __future__ import annotations

from typing import Any

from bob3.spec_quality.example_grammar import (
    KeyExample,
    PropertyAC,
    check_boundary_satisfied,
    emit_hypothesis_test,
    emit_parametrize_test,
    parse_key_example,
    parse_property_ac,
    requires_boundary,
)


def key_examples_property_based_ac_variant(
    *,
    property_ac: str | None,
    key_examples: list[Any],
    behavior_ac: str | None = None,
) -> dict[str, Any]:
    """Parse and emit artifacts for the property-based AC variant.

    Handles the seventh AC grammar (``property: <name> for <generator>
    assert <predicate>``) and the ``key_example:`` sub-key on behavior ACs.

    Args:
        property_ac:  Raw property AC string (may be ``None`` or a non-property AC).
        key_examples: List of key-example entries.  Each entry may be a dict
                      with ``given``/``then`` keys or a string in
                      ``given: … then: …`` format.  Invalid entries are
                      silently skipped.
        behavior_ac:  Optional raw behavior AC string used to determine whether
                      boundary key-examples are required.

    Returns:
        A dict with the following keys:

        - ``property``:          Parsed :class:`PropertyAC` or ``None``.
        - ``hypothesis_test``:   Hypothesis test source code string (empty when
                                 no property AC is present).
        - ``key_examples``:      List of parsed :class:`KeyExample` objects.
        - ``parametrize_test``:  Parametrize test source (empty when no examples).
        - ``boundary_required``: ``True`` when *behavior_ac* involves numeric
                                 ranges or data transformation.
        - ``boundary_satisfied``: ``True`` when the boundary requirement is met
                                  (or not required).
        - ``few_shot_context``:  A string snippet suitable for use as codegen
                                 few-shot context.
    """
    # --- Property AC ---
    parsed_property: PropertyAC | None = None
    hypothesis_test: str = ""
    if property_ac is not None:
        parsed_property = parse_property_ac(property_ac)
    if parsed_property is not None:
        hypothesis_test = emit_hypothesis_test(parsed_property, seed=0)

    # --- Key examples ---
    parsed_examples: list[KeyExample] = []
    for entry in key_examples:
        if entry is None:
            continue
        ex = parse_key_example(entry)
        if ex is not None:
            parsed_examples.append(ex)

    parametrize_test = emit_parametrize_test(parsed_examples, seed=0)

    # --- Boundary check ---
    boundary_required = False
    boundary_satisfied = True
    if behavior_ac is not None:
        req = check_boundary_satisfied(behavior_ac, parsed_examples)
        boundary_required = req.required
        boundary_satisfied = req.satisfied

    # --- Few-shot context for codegen ---
    few_shot_context = _build_few_shot_context(parsed_property, parsed_examples)

    return {
        "property": parsed_property,
        "hypothesis_test": hypothesis_test,
        "key_examples": parsed_examples,
        "parametrize_test": parametrize_test,
        "boundary_required": boundary_required,
        "boundary_satisfied": boundary_satisfied,
        "few_shot_context": few_shot_context,
    }


def _build_few_shot_context(
    prop: PropertyAC | None,
    examples: list[KeyExample],
) -> str:
    """Build a few-shot context string for the codegen agent."""
    parts: list[str] = []

    if prop is not None:
        parts.append(
            f"property: {prop.name} for {prop.generator} assert {prop.predicate}"
        )

    if examples:
        parts.append("key_examples:")
        for ex in examples:
            parts.append(f"  given: {ex.given}, then: {ex.then}")

    return "\n".join(parts)
