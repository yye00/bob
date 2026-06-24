"""Design-by-Contract sub-grammar on behavior — pre / post / inv / raises.

Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:

    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

Primary entry points:
- ``parse_contract_spec`` — parse a behavior AC dict into a :class:`ContractSpec`
- ``emit_icontract_decorators`` — emit icontract decorator source from a :class:`ContractSpec`

Codegen integration: import ``emit_icontract_decorators`` from this module to emit
decorator stacks during bob.codegen synthesis. Pre violations charge the caller;
post/inv violations charge the implementer.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar import (
    ContractParseError,
    ContractSpec,
    BlameTarget,
    attribute_blame,
    emit_icontract_decorators as _emit_icontract_decorators,
    parse_contract as _parse_contract,
    raises_on_malformed_clause,
)

__all__ = [
    "emit_icontract_decorators",
    "generate_icontract_decorators",
    "parse_contract_spec",
    "ContractSpec",
    "ContractParseError",
]

_RECOGNISED_KEYS = frozenset({"pre", "post", "inv", "raises", "behavior"})


def parse_contract_spec(ac: dict) -> ContractSpec:
    """Parse DbC sub-keys from a behavior: AC dict into a ContractSpec.

    Reads the optional ``pre``, ``post``, ``inv``, and ``raises`` sub-keys from
    *ac* and returns a :class:`ContractSpec` with normalised lists for each clause.
    The ``behavior`` key is silently ignored. Unknown keys raise :exc:`ValueError`.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``. Each contract key may
            be a bare string or a list of strings.

    Returns:
        A :class:`ContractSpec` with normalised lists for each clause.

    Raises:
        ValueError: When *ac* is not a dict, or when it contains unrecognised
            sub-keys that cannot be part of a valid DbC specification.
    """
    if not isinstance(ac, dict):
        raise ValueError(
            f"ac must be a dict, got {type(ac).__name__!r}: {ac!r}"
        )

    unknown = set(ac.keys()) - _RECOGNISED_KEYS
    if unknown:
        raise ValueError(
            f"Unrecognised DbC sub-keys: {sorted(unknown)!r}. "
            f"Recognised keys are: {sorted(_RECOGNISED_KEYS)!r}"
        )

    return _parse_contract(ac)


def emit_icontract_decorators(spec: ContractSpec) -> str:
    """Emit Python source-code decorator stacks for a :class:`ContractSpec`.

    Codegen entry point: given a parsed :class:`ContractSpec`, produces the
    Python decorator source that can be prepended to a function or class
    definition. Each ``pre`` clause becomes ``@icontract.require``; each
    ``post`` becomes ``@icontract.ensure``; each ``inv`` becomes
    ``@icontract.invariant``; ``raises`` are emitted as structured comments.

    Returns an empty string when *spec* has no clauses.

    Args:
        spec: A :class:`ContractSpec` parsed from a behavior: AC dict.

    Returns:
        Python decorator source code string; empty string when no clauses are
        present. Includes ``import icontract`` when any decorator clause is
        present.
    """
    return _emit_icontract_decorators(spec)


def generate_icontract_decorators(spec: ContractSpec) -> str:
    """Alias for :func:`emit_icontract_decorators` — generate icontract decorator source.

    Provides an alternate name matching the AC contract.
    """
    return _emit_icontract_decorators(spec)
