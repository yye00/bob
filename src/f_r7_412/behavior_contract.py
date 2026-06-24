"""Design-by-Contract sub-grammar on EARS behavior: acceptance criteria.

Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:

    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

``apply_design_by_contract`` is the public entry point. It accepts a behavior
AC dict, parses the DbC sub-keys, emits matching ``icontract`` decorator
source code, and returns structured blame assignments keyed by clause type.

Pre violations charge the caller; post/inv violations charge the implementer.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar import (
    ContractSpec,
    ContractParseError,
    attribute_blame,
    emit_icontract_decorators,
    parse_contract,
    raises_on_malformed_clause,
)


def apply_design_by_contract(ac: dict) -> dict:
    """Parse a behavior: AC dict and emit icontract decorators with blame map.

    Reads the optional ``pre``, ``post``, ``inv``, and ``raises`` sub-keys
    from *ac*, validates keys, emits matching ``icontract`` decorator strings,
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

        >>> apply_design_by_contract({"pre": "x > 0", "post": "result > 0"})
        {
            "spec": {"pre": ["x > 0"], "post": ["result > 0"], "inv": [], "raises": []},
            "decorators": "import icontract\\n\\n@icontract.require(lambda x: (x > 0))...",
            "blame": {"pre": "caller", "post": "implementer"},
        }

        >>> apply_design_by_contract({})
        {"spec": {"pre": [], "post": [], "inv": [], "raises": []}, "decorators": "", "blame": {}}
    """
    if not isinstance(ac, dict):
        raise ValueError(
            f"ac must be a dict, got {type(ac).__name__!r}: {ac!r}"
        )

    raises_on_malformed_clause(ac)

    spec: ContractSpec = parse_contract(ac)
    decorators: str = emit_icontract_decorators(spec)

    blame: dict[str, str] = {}
    if spec.pre:
        blame["pre"] = attribute_blame("pre", spec).value
    if spec.post:
        blame["post"] = attribute_blame("post", spec).value
    if spec.inv:
        blame["inv"] = attribute_blame("inv", spec).value

    spec_dict: dict = {
        "pre": list(spec.pre),
        "post": list(spec.post),
        "inv": list(spec.inv),
        "raises": list(spec.raises),
    }

    return {
        "spec": spec_dict,
        "decorators": decorators,
        "blame": blame,
    }


__all__ = ["apply_design_by_contract"]
