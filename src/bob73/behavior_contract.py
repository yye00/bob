"""Design-by-Contract sub-grammar for bob73 — public entry point.

Exposes :func:`apply_contract_decorators` as the bob73-namespaced API for
applying DbC contracts parsed from EARS ``behavior:`` acceptance-criteria.

The four optional sub-keys are:

    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

Pre violations charge the caller; post/inv violations charge the implementer.
"""

from __future__ import annotations

from f_r7_412.behavior_contract import apply_design_by_contract


def apply_contract_decorators(ac: dict) -> dict:
    """Parse a behavior: AC dict and emit icontract decorators with blame map.

    Delegates to :func:`f_r7_412.behavior_contract.apply_design_by_contract`.

    Reads the optional ``pre``, ``post``, ``inv``, and ``raises`` sub-keys
    from *ac*, validates keys, emits matching ``icontract`` decorator strings,
    and computes blame assignments following Meyer's DbC rule.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``.

    Returns:
        A dict with three keys: ``spec``, ``decorators``, ``blame``.

    Raises:
        ValueError: When *ac* is not a dict or contains unrecognised sub-keys.
    """
    return apply_design_by_contract(ac)


__all__ = ["apply_contract_decorators"]
