"""bob3.codegen — code generation utilities for acceptance criteria.

Provides helpers for generating Hypothesis and pytest test code from
property-based ACs and key-example ACs, and icontract decorator emission
from Design-by-Contract behavior: sub-keys.

Public API
----------
- ``emit_hypothesis_test`` — emit a Hypothesis ``@given``-decorated test for a property AC.
- ``emit_key_example_test`` — emit a ``@pytest.mark.parametrize`` test for key-examples.
- ``emit_behavior_contract_decorators`` — emit icontract decorators from a behavior AC dict.
"""

from __future__ import annotations

from bob3.spec_quality.example_grammar import (
    KeyExample,
    PropertyAC,
    emit_hypothesis_test as _emit_hypothesis_test,
    emit_parametrize_test as _emit_parametrize_test,
)
from bob3.behavior_contract import apply_design_by_contract
from bob3.design_by_contract import (
    emit_icontract_decorators,
    parse_contract_spec,
)

__all__ = [
    "emit_hypothesis_test",
    "emit_key_example_test",
    "emit_behavior_contract_decorators",
    "emit_icontract_decorators",
    "parse_contract_spec",
]


def emit_hypothesis_test(prop: PropertyAC, *, seed: int = 0) -> str:
    """Emit a runnable Hypothesis test for a property AC.

    Wraps :func:`bob3.spec_quality.example_grammar.emit_hypothesis_test`
    and is the canonical integration point in ``bob3.codegen``.

    The generated test uses ``@settings(deriving=["database"])`` and
    ``@seed(seed)`` so the test run is reproducible with ``seed=0`` by default.

    Args:
        prop: A :class:`~bob3.spec_quality.example_grammar.PropertyAC` dataclass
              parsed from a ``property: <name> for <generator> assert <predicate>`` AC.
        seed: Integer seed for Hypothesis reproducibility.  Default is ``0``.

    Returns:
        Python source code string containing a ``@given``-decorated test function.

    Raises:
        TypeError: When *prop* is not a :class:`PropertyAC`.
    """
    if not isinstance(prop, PropertyAC):
        raise TypeError(
            f"prop must be a PropertyAC, got {type(prop).__name__!r}"
        )
    return _emit_hypothesis_test(prop, seed=seed)


def emit_key_example_test(
    examples: list[KeyExample],
    *,
    test_name: str = "test_key_examples",
    seed: int = 0,
) -> str:
    """Emit a ``@pytest.mark.parametrize`` test from key-examples.

    Wraps :func:`bob3.spec_quality.example_grammar.emit_parametrize_test`
    and is the canonical integration point in ``bob3.codegen``.

    Each :class:`~bob3.spec_quality.example_grammar.KeyExample` becomes one
    parametrize row.  Fixed seed=0 ensures reproducibility.

    Args:
        examples:  List of :class:`KeyExample` objects to parametrize over.
        test_name: Name for the generated test function.
        seed:      Seed stored in a comment for reproducibility tracking.

    Returns:
        Python source code string, or ``""`` when *examples* is empty.
    """
    return _emit_parametrize_test(examples, test_name=test_name, seed=seed)


def emit_behavior_contract_decorators(ac: dict) -> str:
    """Emit icontract decorators for a behavior: AC dict.

    Convenience wrapper around :func:`bob3.behavior_contract.apply_design_by_contract`
    that returns only the decorator source string. Integrates Design-by-Contract
    sub-grammar (pre/post/inv/raises) into the codegen pipeline.

    Args:
        ac: Behavior AC dict with optional ``pre``, ``post``, ``inv``, ``raises``
            sub-keys. Non-dict input raises :exc:`ValueError`.

    Returns:
        Python decorator source code string; empty string when no clauses present.

    Raises:
        ValueError: When *ac* is not a dict or contains unrecognised sub-keys.
    """
    return apply_design_by_contract(ac)["decorators"]
