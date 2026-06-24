"""Lambda parameter binder for icontract decorator emission.

Fixes the zero-arg lambda bug (feature 73879589): the emitter previously wrote
``@icontract.require(lambda: (x > 0))`` — a zero-arg lambda referencing free
variable ``x`` that icontract cannot bind, causing NameError at runtime.

This module provides:
- ``extract_free_variables``: AST-based extraction of identifiers from a
  condition expression that must appear as lambda parameters.
- ``emit_bound_require_decorator``: produces a correctly-bound decorator string,
  e.g. ``@icontract.require(lambda x: (x > 0))``.
- ``validate_lambda_binding``: AST-validates a generated decorator string and
  raises ``ContractGrammarBindingError`` if any body name is unbound.
- ``ContractGrammarBindingError``: raised on binding validation failure.
"""

from __future__ import annotations

import ast
import builtins
from typing import FrozenSet

# Names that must never be treated as free variables requiring lambda binding.
_BUILTIN_NAMES: FrozenSet[str] = frozenset(dir(builtins))
_KEYWORD_CONSTANTS: FrozenSet[str] = frozenset({"None", "True", "False"})
_EXCLUDED_NAMES: FrozenSet[str] = _BUILTIN_NAMES | _KEYWORD_CONSTANTS


class ContractGrammarBindingError(ValueError):
    """Raised when a generated decorator has unbound names in its lambda body."""


def extract_free_variables(condition: str) -> tuple[str, ...]:
    """Extract identifier names from *condition* that need lambda parameter binding.

    Parses *condition* as a Python expression and collects every ``Name`` node
    whose id is not a builtin, keyword constant (``None``/``True``/``False``),
    or attribute access result.  Attribute access base names (e.g. ``self`` in
    ``self.count``) ARE included because they must be bound by the caller.

    Args:
        condition: A Python expression string, e.g. ``"x > 0 and y < 10"``.

    Returns:
        A sorted tuple of unique identifier strings, e.g. ``("x", "y")``.
    """
    try:
        tree = ast.parse(condition, mode="eval")
    except SyntaxError:
        return ()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _EXCLUDED_NAMES:
            names.add(node.id)

    return tuple(sorted(names))


def emit_bound_require_decorator(condition: str) -> str:
    """Emit a correctly-bound ``@icontract.require`` decorator string.

    Extracts free variables from *condition* and emits them as lambda parameters
    so that icontract can bind them at decoration time.

    Examples::

        emit_bound_require_decorator("x > 0")
        # → "@icontract.require(lambda x: (x > 0))"

        emit_bound_require_decorator("x > 0 and y < 10")
        # → "@icontract.require(lambda x, y: (x > 0 and y < 10))"

    Args:
        condition: A Python expression string for the precondition.

    Returns:
        A decorator source string with all free variables bound.
    """
    free_vars = extract_free_variables(condition)
    params = ", ".join(free_vars)
    return f"@icontract.require(lambda {params}: ({condition}))"


def validate_lambda_binding(decorator: str) -> bool:
    """Validate that every name in the lambda body is bound or available.

    Parses *decorator* as a Python expression, locates the lambda node, and
    checks that every ``Name`` in the lambda body is either a lambda parameter
    or a builtin/keyword constant.  Raises ``ContractGrammarBindingError`` if
    any name is unbound.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all names are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    # Strip leading '@' to parse as an expression
    expr_src = decorator.lstrip("@")

    try:
        tree = ast.parse(expr_src, mode="eval")
    except SyntaxError as exc:
        raise ContractGrammarBindingError(
            f"Cannot parse decorator as expression: {exc}"
        ) from exc

    # Find the first Lambda node anywhere in the tree
    lambda_node: ast.Lambda | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda):
            lambda_node = node
            break

    if lambda_node is None:
        # No lambda found — nothing to validate
        return True

    # Collect bound names from lambda parameters
    bound_names: set[str] = set()
    for arg in lambda_node.args.args:
        bound_names.add(arg.arg)
    # Also cover *args and **kwargs if present
    if lambda_node.args.vararg:
        bound_names.add(lambda_node.args.vararg.arg)
    if lambda_node.args.kwarg:
        bound_names.add(lambda_node.args.kwarg.arg)

    # Collect all Name references in the lambda body
    unbound: list[str] = []
    for node in ast.walk(lambda_node.body):
        if isinstance(node, ast.Name):
            name = node.id
            if name not in bound_names and name not in _EXCLUDED_NAMES:
                unbound.append(name)

    if unbound:
        raise ContractGrammarBindingError(
            f"Lambda body references unbound name(s) {sorted(set(unbound))!r}. "
            f"Lambda parameters are: {sorted(bound_names)!r}. "
            f"Decorator: {decorator!r}"
        )

    return True
