"""bob77.ac_grammar — seventh AC grammar: property-based and key-example AC parsing.

Exposes :func:`parse_property_ac` and :func:`parse_key_example_ac` from the
``ac_grammar.property_based`` package as the canonical ``bob77.ac_grammar`` API.

Grammar
-------
Property AC (seventh grammar)::

    property: <name> for <generator> assert <predicate>

Key-example sub-key (on any behavior AC)::

    key_example:
      given: <input values>
      then:  <expected output/state>

Both grammars are used by:

- The codegen agent — property specs and key-examples serve as few-shot context.
- The verifier — one Hypothesis test is emitted per property AC; one
  ``@pytest.mark.parametrize`` test is emitted per key-example with seed=0.

Boundary examples are required for any AC involving data transformation or a
numeric range.
"""

from __future__ import annotations

from typing import Any

from ac_grammar.property_based import (
    parse_key_example_ac,
    parse_property_ac,
)

__all__ = [
    "parse_property_ac",
    "parse_key_example_ac",
]
