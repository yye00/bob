"""Design-by-Contract sub-grammar parser for EARS behavior: ACs.

Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:

    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

``parse_dbc_behavior`` is the primary entry point. ``DBCBehavior`` is the
structured return type holding parsed spec, emitted decorators, and blame map.

Pre violations charge the caller; post/inv violations charge the implementer.
"""

from __future__ import annotations

from dataclasses import dataclass

from bob3.spec_quality.contract_grammar import (
    ContractSpec,
    attribute_blame,
    emit_icontract_decorators,
    parse_contract,
    raises_on_malformed_clause,
)


@dataclass
class DBCBehavior:
    """Parsed Design-by-Contract contract derived from a behavior: AC dict.

    Attributes:
        spec: Dict with four keys — ``pre``, ``post``, ``inv``, ``raises`` —
            each holding a list of clause strings.
        decorators: Python decorator source code (possibly empty) suitable for
            prepending to a function or class definition.
        blame: Dict mapping clause types to the responsible party:
            ``"pre"`` → ``"caller"``; ``"post"``/``"inv"`` → ``"implementer"``.
            Absent clauses are not included.
    """

    spec: dict
    decorators: str
    blame: dict


def parse_dbc_behavior(ac: object) -> DBCBehavior:
    """Parse a behavior: AC dict and return a DBCBehavior with decorators and blame.

    Reads the optional ``pre``, ``post``, ``inv``, and ``raises`` sub-keys from
    *ac*, validates that no unrecognised keys are present, emits matching
    ``icontract`` decorator strings, and computes blame assignments following
    Meyer's DbC rule.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``. Each contract key may
            be a bare string or a list of strings.

    Returns:
        A :class:`DBCBehavior` instance with:

        ``spec``
            Plain dict view of parsed contract clauses:
            ``{"pre": [...], "post": [...], "inv": [...], "raises": [...]}``.

        ``decorators``
            Python decorator source code string (empty when no clauses are
            present). Includes ``import icontract`` when any clause is present.

        ``blame``
            Dict mapping each present clause type to the responsible party.
            Clause types with no expressions are omitted.

    Raises:
        ValueError: When *ac* is not a dict, or contains unrecognised sub-keys.
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

    return DBCBehavior(
        spec=spec_dict,
        decorators=decorators,
        blame=blame,
    )


__all__ = ["DBCBehavior", "parse_dbc_behavior"]
