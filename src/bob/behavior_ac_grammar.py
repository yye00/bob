"""Design-by-Contract sub-grammar on behavior — pre / post / inv / raises.

Provides ``parse_dbc_behavior_ac`` and ``codegen_icontract_decorators`` as the
canonical API for the Design-by-Contract EARS behavior: AC extension (F-R7-412).

Sub-keys recognised in a behavior: AC dict:
    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

``parse_dbc_behavior_ac`` parses the dict and returns spec, decorators, and
blame assignments in a single call.

``codegen_icontract_decorators`` generates Python icontract decorator source
strings from a :class:`~bob.spec_quality.contract_grammar.ContractSpec`.

Pre violations charge the caller; post/inv violations charge the implementer.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar import (
    ContractParseError,
    ContractSpec,
    BlameTarget,
    attribute_blame,
    emit_icontract_decorators,
    parse_contract,
    raises_on_malformed_clause,
)


def parse_dbc_behavior_ac(ac: dict) -> dict:
    """Parse a behavior: AC dict with DbC sub-keys and return structured output.

    Reads the optional ``pre``, ``post``, ``inv``, and ``raises`` sub-keys from
    *ac*, validates keys, emits matching ``icontract`` decorator strings, and
    computes blame assignments following Meyer's DbC rule:
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


def codegen_icontract_decorators(spec: ContractSpec) -> str:
    """Generate Python icontract decorator source strings from a ContractSpec.

    Delegates to :func:`~bob.spec_quality.contract_grammar.emit_icontract_decorators`.
    Each ``pre`` condition becomes ``@icontract.require``; each ``post`` becomes
    ``@icontract.ensure``; each ``inv`` becomes ``@icontract.invariant``.
    Declared ``raises`` are emitted as structured comments.

    Args:
        spec: A parsed :class:`~bob.spec_quality.contract_grammar.ContractSpec`.

    Returns:
        A string of Python decorator lines (empty when no clauses are present).
        Includes ``import icontract`` when any clause is present.
    """
    return emit_icontract_decorators(spec)


__all__ = [
    "parse_dbc_behavior_ac",
    "codegen_icontract_decorators",
    "ContractSpec",
    "ContractParseError",
    "BlameTarget",
    "attribute_blame",
    "parse_contract",
    "raises_on_malformed_clause",
]
