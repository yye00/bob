"""Design-by-Contract sub-grammar on EARS behavior: acceptance criteria.

Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:

    pre:    precondition on caller (violations charge the caller)
    post:   postcondition on routine (violations charge the implementer)
    inv:    class/state invariant (violations charge the implementer)
    raises: declared exception types

``behavior_with_contract`` is the public entry point. It accepts a behavior
AC dict, extracts the optional ``behavior`` prose key, delegates DbC parsing
and codegen to :mod:`f_r7_412.behavior_contract`, and returns structured
output including the behavior prose, the parsed contract spec, emitted
``icontract`` decorator source, and blame assignments keyed by clause type.
"""

from __future__ import annotations

from f_r7_412.behavior_contract import apply_design_by_contract


def behavior_with_contract(ac: dict) -> dict:
    """Parse a behavior: AC dict and return DbC contract info with blame map.

    Reads the optional ``behavior`` prose key and the optional DbC sub-keys
    ``pre``, ``post``, ``inv``, and ``raises`` from *ac*. Validates the dict
    for unrecognised keys, emits matching ``icontract`` decorator strings, and
    computes blame assignments following Meyer's DbC rule:

    - ``pre`` violations: the **caller** passed invalid inputs.
    - ``post`` / ``inv`` violations: the **implementer** returned incorrect output.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``behavior``,
            ``pre``, ``post``, ``inv``, ``raises``. Each contract key may be a bare
            string or a list of strings.

    Returns:
        A dict with four keys:

        ``behavior``
            The behavior prose string from the AC (empty string when absent).

        ``spec``
            Plain dict view of parsed contract clauses:
            ``{"pre": [...], "post": [...], "inv": [...], "raises": [...]}``.

        ``decorators``
            Python decorator source code string (empty when no clauses are
            present). Includes ``import icontract`` when any clause is present.

        ``blame``
            Dict mapping each present clause type to the responsible party:
            ``{"pre": "caller", "post": "implementer", "inv": "implementer"}``.
            Clause types with no expressions are omitted.

    Raises:
        ValueError: When *ac* is not a dict, or when it contains unrecognised
            sub-keys that cannot be part of a valid DbC specification.
    """
    if not isinstance(ac, dict):
        raise ValueError(
            f"ac must be a dict, got {type(ac).__name__!r}: {ac!r}"
        )

    behavior_text: str = ac.get("behavior", "") or ""

    contract_result = apply_design_by_contract(ac)

    return {
        "behavior": behavior_text,
        "spec": contract_result["spec"],
        "decorators": contract_result["decorators"],
        "blame": contract_result["blame"],
    }


__all__ = ["behavior_with_contract"]
