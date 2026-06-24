"""Public top-level API for contract grammar lambda binding validation.

Exposes the core lambda-binding functions from bob.spec_quality.contract_grammar
and bob.spec_quality.contract_grammar_lambda_binder at the bob.contract_grammar
namespace, satisfying the AC requirement for:
    Function defined: bob.contract_grammar.validate_lambda_binding

Root cause (feature 73879589 NH-demotion): the emitter previously wrote
``@icontract.require(lambda: (x > 0))`` — a zero-arg lambda referencing free
variable ``x`` that icontract cannot bind, causing NameError at runtime.

This module exposes the corrected emitter and binding validator as a canonical
public API at the bob top level.
"""

from __future__ import annotations

from bob.spec_quality.contract_grammar_lambda_binder import (
    ContractGrammarBindingError,
    emit_bound_require_decorator,
    extract_free_variables,
    validate_lambda_binding,
)
from bob.spec_quality.contract_grammar import (
    BlameTarget,
    ContractParseError,
    ContractSpec,
    attribute_blame,
    emit_icontract_decorators,
    extract_lambda_parameters,
    parse_contract,
    validate_decorator_binding,
    validate_decorator_bindings,
    validate_lambda_bindings,
)


__all__ = [
    "BlameTarget",
    "ContractGrammarBindingError",
    "ContractParseError",
    "ContractSpec",
    "attribute_blame",
    "emit_bound_require_decorator",
    "emit_icontract_decorators",
    "extract_free_variables",
    "extract_lambda_parameters",
    "parse_contract",
    "validate_decorator_binding",
    "validate_decorator_bindings",
    "validate_lambda_binding",
    "validate_lambda_bindings",
]
