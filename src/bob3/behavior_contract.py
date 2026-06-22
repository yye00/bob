"""Design-by-Contract sub-grammar on EARS behavior: acceptance criteria.

Public API for the F-R7-412 EARS ``behavior:`` AC Design-by-Contract extension.
Extends behavior ACs with four optional sub-keys:

    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

``emit_icontract_decorators`` is the primary entry point for codegen use:
given a :class:`~bob3.spec_quality.contract_grammar.ContractSpec`, it produces
Python source-code decorator stacks for ``icontract``.

``parse_behavior_contract`` parses a raw behavior AC dict end-to-end and
returns spec, decorators, and blame assignments in a single call.
"""

from __future__ import annotations

from bob3.spec_quality.contract_grammar import (
    ContractParseError,
    ContractSpec,
    BlameTarget,
    attribute_blame,
    emit_icontract_decorators,
    parse_contract,
    raises_on_malformed_clause,
    validate_lambda_binding as _validate_lambda_binding,
    extract_lambda_parameters as _extract_lambda_parameters,
)


def parse_behavior_contract(ac: dict) -> dict:
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


def apply_contract_decorators(ac: dict) -> str:
    """Emit icontract decorator source code for a behavior: AC dict.

    Convenience entry point for codegen: parses the DbC sub-keys (``pre``,
    ``post``, ``inv``, ``raises``) from *ac* and returns the ready-to-emit
    Python decorator string. Delegates to :func:`parse_behavior_contract`.

    Pre violations charge the caller; post/inv violations charge the implementer.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``. Each contract key may
            be a bare string or a list of strings.

    Returns:
        Python decorator source code string; empty string when no contract
        clauses are present. Includes ``import icontract`` when any clause
        is present.

    Raises:
        ValueError: When *ac* is not a dict, or when it contains unrecognised
            sub-keys that cannot be part of a valid DbC specification.
    """
    return parse_behavior_contract(ac)["decorators"]


codegen_icontract_decorators = emit_icontract_decorators

apply_design_by_contract = parse_behavior_contract


def apply_dbc_decorators(ac: dict) -> str:
    """Emit icontract decorator source code for a behavior: AC dict.

    Primary codegen entry point for Design-by-Contract decorator emission.
    Parses the DbC sub-keys (``pre``, ``post``, ``inv``, ``raises``) from *ac*
    and returns the ready-to-emit Python decorator string.

    Pre violations charge the caller; post/inv violations charge the implementer.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``. Each contract key may
            be a bare string or a list of strings.

    Returns:
        Python decorator source code string; empty string when no contract
        clauses are present. Includes ``import icontract`` when any clause
        is present.

    Raises:
        ValueError: When *ac* is not a dict, or when it contains unrecognised
            sub-keys that cannot be part of a valid DbC specification.
    """
    return apply_contract_decorators(ac)


def validate_precondition(condition: str) -> bool:
    """Validate that a precondition expression is syntactically bindable.

    Wraps the lambda-binding validator for a precondition (``pre``) expression.
    Emits a candidate ``@icontract.require`` decorator and checks that all
    free variable names can be bound as lambda parameters.

    Pre violations charge the **caller** per Meyer's DbC rule.

    Args:
        condition: A Python expression string, e.g. ``"x > 0 and y < 10"``.

    Returns:
        ``True`` when the expression is valid and all names are bindable.

    Raises:
        ValueError: When *condition* is not a string.
        ContractGrammarBindingError: When the expression contains names that
            cannot be auto-bound as lambda parameters.
    """
    if not isinstance(condition, str):
        raise ValueError(
            f"condition must be a str, got {type(condition).__name__!r}: {condition!r}"
        )
    params = _extract_lambda_parameters(condition)
    param_str = ", ".join(params) if params else "_"
    decorator = f"@icontract.require(lambda {param_str}: ({condition}))"
    return _validate_lambda_binding(decorator)


def validate_postcondition(condition: str) -> bool:
    """Validate that a postcondition expression is syntactically bindable.

    Wraps the lambda-binding validator for a postcondition (``post``) expression.
    Emits a candidate ``@icontract.ensure`` decorator and checks that the
    expression is syntactically valid.

    Post violations charge the **implementer** per Meyer's DbC rule.

    Args:
        condition: A Python expression string, e.g. ``"result >= 0"``.

    Returns:
        ``True`` when the expression is valid and bindable.

    Raises:
        ValueError: When *condition* is not a string.
        ContractGrammarBindingError: When the expression contains names that
            cannot be auto-bound as lambda parameters.
    """
    if not isinstance(condition, str):
        raise ValueError(
            f"condition must be a str, got {type(condition).__name__!r}: {condition!r}"
        )
    decorator = f"@icontract.ensure(lambda result: ({condition}))"
    return _validate_lambda_binding(decorator)


__all__ = [
    "apply_contract_decorators",
    "apply_dbc_decorators",
    "emit_icontract_decorators",
    "codegen_icontract_decorators",
    "parse_behavior_contract",
    "apply_design_by_contract",
    "validate_precondition",
    "validate_postcondition",
    "ContractSpec",
    "ContractParseError",
    "BlameTarget",
    "attribute_blame",
    "parse_contract",
    "raises_on_malformed_clause",
]
