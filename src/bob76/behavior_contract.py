"""Design-by-Contract sub-grammar on EARS behavior: acceptance criteria.

Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:

    pre:    precondition on caller (violations charge the caller)
    post:   postcondition on routine (violations charge the implementer)
    inv:    class/state invariant (violations charge the implementer)
    raises: declared exception types

``apply_contract_decorators`` is the public entry point. It accepts a behavior
AC dict, parses the DbC sub-keys (pre/post/inv/raises), emits matching
``icontract`` decorator source code, and returns structured blame assignments
keyed by clause type.

Pre violations charge the caller; post/inv violations charge the implementer.
"""

from __future__ import annotations

from f_r7_412.behavior_contract import apply_design_by_contract


_KNOWN_KEYS = frozenset({"pre", "post", "inv", "raises", "behavior"})


def apply_contract_decorators(ac: dict) -> dict:
    """Parse a behavior: AC dict and emit icontract decorators with blame map.

    Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:
    ``pre``, ``post``, ``inv``, and ``raises``. Validates the dict for
    unrecognised keys, emits matching ``icontract`` decorator source strings,
    and computes blame assignments following Meyer's DbC rule:

    - ``pre`` violations: the **caller** passed invalid inputs.
    - ``post`` / ``inv`` violations: the **implementer** returned incorrect output.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``. Each contract key may
            be a bare string or a list of strings.

    Returns:
        A dict with three keys:

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

    Examples::

        >>> apply_contract_decorators({"pre": "x > 0", "post": "result > 0"})
        {
            "spec": {"pre": ["x > 0"], "post": ["result > 0"], "inv": [], "raises": []},
            "decorators": "import icontract\\n\\n@icontract.require(lambda x: (x > 0))...",
            "blame": {"pre": "caller", "post": "implementer"},
        }

        >>> apply_contract_decorators({})
        {"spec": {"pre": [], "post": [], "inv": [], "raises": []}, "decorators": "", "blame": {}}
    """
    if not isinstance(ac, dict):
        raise ValueError(
            f"ac must be a dict, got {type(ac).__name__!r}: {ac!r}"
        )

    bad_keys = [k for k in ac if k not in _KNOWN_KEYS]
    if bad_keys:
        raise ValueError(
            f"Unrecognised contract sub-key(s): {bad_keys!r}. "
            f"Allowed keys: {sorted(_KNOWN_KEYS)}"
        )

    return apply_design_by_contract(ac)


__all__ = ["apply_contract_decorators"]
