"""Design-by-Contract sub-grammar on behavior — pre / post / inv / raises.

Facade module extending the F-R7-412 EARS ``behavior:`` AC with four optional
sub-keys parsed via ``bob.spec_quality.contract_grammar``:

    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

``design_contract_sub_grammar_behavior_pre_post_inv_raises`` is the single
public entry point: it parses a behavior AC dict, emits matching icontract
decorator source strings, and returns blame assignments keyed by clause type.

Pre violations charge the caller; post/inv violations charge the implementer.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar import (
    ContractSpec,
    attribute_blame,
    emit_icontract_decorators,
    parse_contract,
)


def design_contract_sub_grammar_behavior_pre_post_inv_raises(
    ac: dict,
) -> dict:
    """Parse a behavior: AC dict and emit icontract decorator source + blame map.

    Reads the optional ``pre``, ``post``, ``inv``, and ``raises`` sub-keys from
    *ac*, emits matching ``icontract`` decorator strings, and computes blame
    assignments following Meyer's DbC rule (pre → caller, post/inv →
    implementer).

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``. Unknown keys are
            silently ignored. Each contract key may be a bare string or a list.

    Returns:
        A dict with three keys:

        ``spec``
            A plain dict view of the parsed contract clauses:
            ``{"pre": [...], "post": [...], "inv": [...], "raises": [...]}``.

        ``decorators``
            A string of Python decorator source code (possibly empty) suitable
            for prepending to a function or class definition.  Includes
            ``import icontract`` when any clause is present.

        ``blame``
            A dict mapping each present clause type to the responsible party:
            ``{"pre": "caller", "post": "implementer", "inv": "implementer"}``.
            Clause types with no expressions are omitted.
    """
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


__all__ = ["design_contract_sub_grammar_behavior_pre_post_inv_raises"]
