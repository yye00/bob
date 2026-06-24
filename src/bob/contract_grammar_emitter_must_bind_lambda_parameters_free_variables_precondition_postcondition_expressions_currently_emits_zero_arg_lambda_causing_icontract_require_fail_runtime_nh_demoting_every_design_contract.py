"""Contract grammar emitter lambda parameter binding fix.

Feature a8588f10: Public entry point verifying and demonstrating that the
contract_grammar emitter correctly binds lambda parameters to free variables
in precondition/postcondition expressions.

Root cause (feature 73879589 NH-demotion): the emitter previously wrote
``@icontract.require(lambda: (x > 0))`` — a zero-arg lambda referencing free
variable ``x`` that icontract cannot bind, causing NameError at runtime.

This module exposes the corrected emitter (emit_bound_require_decorator) and
the binding validator (validate_lambda_binding) as the canonical public API
for contract-grammar decoration, and provides the named entry-point function
required by the AC.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar import (
    ContractSpec,
    emit_icontract_decorators,
    extract_lambda_parameters,
    validate_lambda_bindings,
)
from bob.spec_quality.contract_grammar_lambda_binder import (
    ContractGrammarBindingError,
    emit_bound_require_decorator,
    extract_free_variables,
    validate_lambda_binding,
)


def contract_grammar_emitter_must_bind_lambda_parameters_free_variables_precondition_postcondition_expressions_currently_emits_zero_arg_lambda_causing_icontract_require_fail_runtime_nh_demoting_every_design_contract(
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
    "ContractSpec",
    "contract_grammar_emitter_must_bind_lambda_parameters_free_variables_precondition_postcondition_expressions_currently_emits_zero_arg_lambda_causing_icontract_require_fail_runtime_nh_demoting_every_design_contract",
    "emit_bound_require_decorator",
    "emit_icontract_decorators",
    "extract_free_variables",
    "extract_lambda_parameters",
    "validate_lambda_binding",
    "validate_lambda_bindings",
]
