"""Contract grammar emitter lambda parameter binding fix.

Public entry point verifying and demonstrating that the contract_grammar emitter
correctly binds lambda parameters to free variables in precondition/postcondition
expressions.

Root cause (feature 73879589 NH-demotion): the emitter previously wrote
``@icontract.require(lambda: (x > 0))`` — a zero-arg lambda referencing free
variable ``x`` that icontract cannot bind, causing NameError at runtime.

This module exposes the corrected emitter and binding validator as a canonical
public API for contract-grammar decoration.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar_lambda_binder import (
    ContractGrammarBindingError,
    emit_bound_require_decorator,
    extract_free_variables,
    validate_lambda_binding,
)


def contract_grammar_emitter_must_bind_lambda_parameters_free(
    condition: str,
) -> str:
    """Emit a correctly-bound @icontract.require decorator for a precondition.

    Extracts free variables from *condition* via AST analysis and emits them as
    lambda parameters so that icontract can bind them at decoration time.
    Validates the emitted decorator before returning — raises
    ContractGrammarBindingError if binding is invalid.

    This is the corrected emitter: it will NEVER produce the broken zero-arg
    ``lambda: (x > 0)`` form that caused NH-demotion of feature 73879589.

    Args:
        condition: A Python expression string for the precondition,
            e.g. ``"x > 0"`` or ``"x > 0 and y < 10"``.

    Returns:
        A decorator source string with all free variables bound as lambda
        parameters, e.g. ``"@icontract.require(lambda x: (x > 0))"``.

    Raises:
        ContractGrammarBindingError: When the emitted decorator fails binding
            validation (should not happen in practice — this is a safety net).
    """
    decorator = emit_bound_require_decorator(condition)
    validate_lambda_binding(decorator)
    return decorator


__all__ = [
    "ContractGrammarBindingError",
    "contract_grammar_emitter_must_bind_lambda_parameters_free",
    "emit_bound_require_decorator",
    "extract_free_variables",
    "validate_lambda_binding",
]
