"""Design-by-Contract sub-grammar on behavior — pre / post / inv / raises.

Canonical public entry point for the F-R7-412 Design-by-Contract sub-grammar.
Extends the EARS ``behavior:`` acceptance criterion with four optional
sub-keys:

    pre:    precondition on the caller (violations blame the **caller**)
    post:   postcondition on the routine (violations blame the **implementer**)
    inv:    class/state invariant (violations blame the **implementer**)
    raises: declared exception type names

Two functions are exported:

``parse_behavior_contract``
    Validates a behavior AC dict and returns a structured, JSON-friendly
    view of the parsed contract clauses plus a per-clause blame map.

``emit_icontract_decorators``
    Emits Python ``icontract`` decorator source code for a parsed contract
    (accepting either the dict returned by :func:`parse_behavior_contract`
    or a raw behavior AC dict).

Pre violations charge the caller; post/inv violations charge the implementer,
following Meyer's Design-by-Contract blame rule.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar import (
    ContractSpec,
    attribute_blame,
    emit_icontract_decorators as _emit_from_spec,
    parse_contract,
    raises_on_malformed_clause,
)

__all__ = ["parse_behavior_contract", "emit_icontract_decorators"]


def _spec_to_dict(spec: ContractSpec) -> dict:
    """Return a plain-dict view of a :class:`ContractSpec`."""
    return {
        "pre": list(spec.pre),
        "post": list(spec.post),
        "inv": list(spec.inv),
        "raises": list(spec.raises),
    }


def _blame_for_spec(spec: ContractSpec) -> dict:
    """Compute the per-clause blame map for a parsed contract spec."""
    blame: dict[str, str] = {}
    if spec.pre:
        blame["pre"] = attribute_blame("pre", spec).value
    if spec.post:
        blame["post"] = attribute_blame("post", spec).value
    if spec.inv:
        blame["inv"] = attribute_blame("inv", spec).value
    return blame


def parse_behavior_contract(ac: dict) -> dict:
    """Parse the DbC sub-keys of a behavior AC dict into a structured contract.

    Reads the optional ``pre``, ``post``, ``inv`` and ``raises`` sub-keys from
    *ac*, validates that no unrecognised sub-keys are present, and returns a
    structured contract view together with a per-clause blame map.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys are
            ``pre``, ``post``, ``inv``, ``raises`` and ``behavior``. Each
            contract key may be a bare string or a list of strings.

    Returns:
        A dict with three keys:

        ``spec``
            ``{"pre": [...], "post": [...], "inv": [...], "raises": [...]}``.

        ``blame``
            Maps each present clause type to the responsible party
            (``"caller"`` for ``pre``; ``"implementer"`` for ``post``/``inv``).
            Clause types with no expressions are omitted. ``raises`` never
            appears in the blame map (it declares types, not a checkable
            condition).

        ``has_contract``
            ``True`` when at least one clause is present, else ``False``.

    Raises:
        ValueError: When *ac* is not a dict, or contains an unrecognised
            sub-key that cannot be part of a valid DbC specification.
    """
    if not isinstance(ac, dict):
        raise ValueError(
            f"ac must be a dict, got {type(ac).__name__!r}: {ac!r}"
        )

    raises_on_malformed_clause(ac)

    spec = parse_contract(ac)
    spec_dict = _spec_to_dict(spec)
    return {
        "spec": spec_dict,
        "blame": _blame_for_spec(spec),
        "has_contract": any(spec_dict[k] for k in ("pre", "post", "inv", "raises")),
    }


def emit_icontract_decorators(contract: dict) -> str:
    """Emit ``icontract`` decorator source code for a behavior contract.

    Accepts either a raw behavior AC dict (with ``pre``/``post``/``inv``/
    ``raises`` sub-keys) or the structured dict returned by
    :func:`parse_behavior_contract` (which nests the clauses under a ``spec``
    key). Each ``pre`` becomes ``@icontract.require``, each ``post`` becomes
    ``@icontract.ensure``, each ``inv`` becomes ``@icontract.invariant``, and
    declared ``raises`` are emitted as a structured comment.

    Args:
        contract: Behavior AC dict, or the result of
            :func:`parse_behavior_contract`.

    Returns:
        A string of Python decorator source (empty when no clauses are
        present). Includes ``import icontract`` when any clause is present.

    Raises:
        ValueError: When *contract* is not a dict, or a raw AC dict contains
            an unrecognised sub-key.
    """
    if not isinstance(contract, dict):
        raise ValueError(
            f"contract must be a dict, got {type(contract).__name__!r}: {contract!r}"
        )

    inner = contract.get("spec") if isinstance(contract.get("spec"), dict) else contract

    if inner is contract:
        raises_on_malformed_clause(inner)

    spec = parse_contract(inner)
    return _emit_from_spec(spec)
