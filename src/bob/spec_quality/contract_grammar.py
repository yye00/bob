"""Design-by-Contract sub-grammar for EARS behavior: acceptance criteria.

Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:

    pre:    precondition on caller (violations blame the caller / upstream feature)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

``parse_contract`` reads these keys from a dict representation of a behavior: AC.
``emit_icontract_decorators`` produces Python source-code strings with the
matching ``icontract`` decorator stacks.
``attribute_blame`` maps violation_type → BlameTarget following Meyer's DbC rule:
pre violations are the caller's fault; post/inv violations are the implementer's.

Per Agent 3 §8 empirical results, executable contracts cut LLM verification
misjudgment from 31-58% to 11-19% by giving the verifier assertions rather than
NL paraphrase.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional

from bob.spec_quality.contract_grammar_lambda_binder import (
    ContractGrammarBindingError,
    emit_bound_require_decorator,
    extract_free_variables as _extract_free_variables,
    validate_lambda_binding as _validate_lambda_binding_impl,
)


def validate_lambda_binding(decorator: str) -> bool:
    """Validate that every name in the lambda body is bound or available.

    AST-parses *decorator*, locates the lambda node, and asserts every ``Name``
    in the lambda body is either a lambda parameter or a builtin/keyword constant.
    Raises ``ContractGrammarBindingError`` if any name is unbound, rejecting the
    contract-grammar synthesis before persistence.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all names are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    return _validate_lambda_binding_impl(decorator)


def validate_contract_decorator(decorator: str) -> bool:
    """Validate that every name in the lambda body is bound or available.

    AC-required canonical name. AST-parses *decorator*, locates the lambda
    node, and asserts every ``Name`` in the lambda body is either a lambda
    parameter or a builtin/keyword constant.  Raises
    ``ContractGrammarBindingError`` if any name is unbound, rejecting the
    contract-grammar synthesis before persistence.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all names are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    return _validate_lambda_binding_impl(decorator)


def validate_decorator_binding(decorator: str) -> bool:
    """Validate that every name in the lambda body is bound or available.

    AC-required alias for :func:`validate_lambda_bindings`. AST-parses
    *decorator*, locates the lambda node, and asserts every ``Name`` in the
    lambda body is either a lambda parameter or a builtin/keyword constant.
    Raises ``ContractGrammarBindingError`` if any name is unbound, rejecting
    the contract-grammar synthesis before persistence.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all names are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    return validate_lambda_binding(decorator)


def validate_lambda_bindings(decorator: str) -> bool:
    """Validate that every name in the lambda body is bound or available.

    Plural alias for :func:`~bob.spec_quality.contract_grammar_lambda_binder.validate_lambda_binding`.
    AST-parses *decorator*, locates the lambda node, and asserts every ``Name``
    in the lambda body is either a lambda parameter or a builtin/keyword constant.
    Raises ``ContractGrammarBindingError`` if any name is unbound, rejecting the
    contract-grammar synthesis before persistence.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all names are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    return validate_lambda_binding(decorator)


def validate_decorator_bindings(decorator: str) -> bool:
    """Validate that every name in the lambda body is bound or available.

    AC-required plural form. AST-parses *decorator*, locates the lambda node,
    and asserts every ``Name`` in the lambda body is either a lambda parameter
    or a builtin/keyword constant. Raises ``ContractGrammarBindingError`` if
    any name is unbound, rejecting the contract-grammar synthesis before
    persistence.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all names are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    return validate_lambda_binding(decorator)


def validate_decorator_lambda(decorator: str) -> bool:
    """Validate that every name in the lambda body is bound or available.

    AC-required canonical name (singular). AST-parses *decorator*, locates the
    lambda node, and asserts every ``Name`` in the lambda body is either a
    lambda parameter or a builtin/keyword constant. Raises
    ``ContractGrammarBindingError`` if any name is unbound, rejecting the
    contract-grammar synthesis before persistence.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all names are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    return validate_lambda_binding(decorator)


def emit_require_decorator(condition: str) -> str:
    """Emit a correctly-bound ``@icontract.require`` decorator string.

    AC-required canonical name. Extracts the free variables from *condition*
    and emits them as lambda parameters so that ``icontract`` can bind them at
    decoration time, fixing the zero-arg lambda bug (feature 73879589) where
    ``@icontract.require(lambda: (x > 0))`` raised NameError at runtime.

    Examples::

        emit_require_decorator("x > 0")
        # → "@icontract.require(lambda x: (x > 0))"

        emit_require_decorator("x > 0 and y < 10")
        # → "@icontract.require(lambda x, y: (x > 0 and y < 10))"

    Args:
        condition: A Python expression string for the precondition.

    Returns:
        A decorator source string with all free variables bound as lambda
        parameters.
    """
    return emit_bound_require_decorator(condition)


def validate_lambda_free_variables(decorator: str) -> bool:
    """Validate that every free variable in the lambda body is bound.

    AC-required canonical name. AST-parses *decorator*, locates the lambda
    node, and asserts every free ``Name`` in the lambda body is bound by the
    lambda parameters (or is a builtin / keyword constant). Rejects the
    contract-grammar synthesis before persistence when any name is unbound.

    Args:
        decorator: A decorator source string, e.g.
            ``"@icontract.require(lambda x: (x > 0))"``.

    Returns:
        ``True`` when all free variables are bound.

    Raises:
        ContractGrammarBindingError: When one or more names in the lambda body
            are not bound by the lambda parameters.
    """
    return _validate_lambda_binding_impl(decorator)


def extract_lambda_parameters(condition: str) -> tuple[str, ...]:
    """Extract lambda parameter names needed to bind a precondition expression.

    Delegates to :func:`~bob.spec_quality.contract_grammar_lambda_binder.extract_free_variables`.

    Args:
        condition: A Python expression string, e.g. ``"x > 0 and y < 10"``.

    Returns:
        A sorted tuple of identifier strings that must appear as lambda
        parameters, e.g. ``("x", "y")``.
    """
    return _extract_free_variables(condition)


def extract_lambda_params(condition: str) -> tuple[str, ...]:
    """Extract lambda parameter names needed to bind a precondition expression.

    Short-form alias for :func:`extract_lambda_parameters`.

    Args:
        condition: A Python expression string, e.g. ``"x > 0 and y < 10"``.

    Returns:
        A sorted tuple of identifier strings that must appear as lambda
        parameters, e.g. ``("x", "y")``.
    """
    return _extract_free_variables(condition)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractSpec:
    """Structured DbC contract parsed from a behavior: AC dict.

    Attributes:
        pre:    List of precondition expression strings (caller must satisfy).
        post:   List of postcondition expression strings (implementer must satisfy).
        inv:    List of class/state invariant expression strings.
        raises: List of declared exception type names.
    """

    pre: list[str] = field(default_factory=list)
    post: list[str] = field(default_factory=list)
    inv: list[str] = field(default_factory=list)
    raises: list[str] = field(default_factory=list)


class BlameTarget(enum.Enum):
    """Blame assignment per Meyer's Design-by-Contract."""

    CALLER = "caller"
    IMPLEMENTER = "implementer"

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# parse_contract
# ---------------------------------------------------------------------------


def _normalise_to_list(value: object) -> list[str]:
    """Convert a string, list, or None to a normalised list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def parse_contract(ac: dict) -> ContractSpec:
    """Parse DbC sub-keys from a behavior: AC dict.

    Accepts any subset of the four sub-keys ``pre``, ``post``, ``inv``,
    ``raises``. Unknown keys (e.g. ``behavior``) are silently ignored.
    Each key may be a bare string or a list of strings.

    Args:
        ac: Dict representing the behavior: AC entry, e.g.::

                {"pre": "x > 0", "post": "result > 0", "inv": "self.ok",
                 "raises": ["ValueError", "TypeError"]}

    Returns:
        A :class:`ContractSpec` with normalised lists for each clause.
    """
    return ContractSpec(
        pre=_normalise_to_list(ac.get("pre")),
        post=_normalise_to_list(ac.get("post")),
        inv=_normalise_to_list(ac.get("inv")),
        raises=_normalise_to_list(ac.get("raises")),
    )


# ---------------------------------------------------------------------------
# emit_icontract_decorators
# ---------------------------------------------------------------------------


def emit_icontract_decorators(spec: ContractSpec) -> str:
    """Emit Python source-code decorator stacks for a :class:`ContractSpec`.

    The emitted snippet is intended to be prepended to a function or class
    definition by the codegen agent. Each ``pre`` condition becomes an
    ``@icontract.require`` decorator; each ``post`` becomes
    ``@icontract.ensure``; each ``inv`` becomes ``@icontract.invariant``.
    Declared ``raises`` are emitted as structured comments.

    Args:
        spec: A parsed :class:`ContractSpec`.

    Returns:
        A string of Python decorator lines (potentially multi-line), e.g.::

            import icontract

            @icontract.require(lambda x: x > 0)
            @icontract.ensure(lambda result: result > 0)

        Returns an empty string when the spec has no clauses.
    """
    parts: list[str] = []

    if not (spec.pre or spec.post or spec.inv or spec.raises):
        return ""

    parts.append("import icontract")
    parts.append("")

    decorator_lines: list[str] = []

    for condition in spec.pre:
        decorator = emit_bound_require_decorator(condition)
        validate_lambda_binding(decorator)
        decorator_lines.append(decorator)

    for condition in spec.post:
        decorator = f"@icontract.ensure(lambda result: ({condition}))"
        validate_lambda_binding(decorator)
        decorator_lines.append(decorator)

    for condition in spec.inv:
        decorator = f"@icontract.invariant(lambda self: ({condition}))"
        validate_lambda_binding(decorator)
        decorator_lines.append(decorator)

    if spec.raises:
        raises_str = ", ".join(spec.raises)
        decorator_lines.append(f"# raises: {raises_str}")

    parts.extend(decorator_lines)
    # Append a placeholder function so the snippet is valid Python on its own.
    parts.append("def _contract_target(*args, **kwargs): ...")

    return "\n".join(parts)


def emit_contract_decorators(spec: ContractSpec) -> str:
    """Emit Python source-code decorator stacks for a :class:`ContractSpec`.

    AC-required canonical name; delegates to :func:`emit_icontract_decorators`.
    Each ``pre`` condition becomes an ``@icontract.require`` decorator whose
    lambda binds every free variable in the condition (fixing the zero-arg
    lambda bug from feature 73879589); each ``post`` becomes
    ``@icontract.ensure(lambda result: ...)``; each ``inv`` becomes
    ``@icontract.invariant(lambda self: ...)``. Every emitted decorator is
    validated with :func:`validate_lambda_binding` before it is returned, so a
    contract whose lambda references an unbound variable raises
    :exc:`~bob.spec_quality.contract_grammar_lambda_binder.ContractGrammarBindingError`
    rather than being persisted.

    Args:
        spec: A parsed :class:`ContractSpec`.

    Returns:
        A string of Python decorator lines, or an empty string when the spec
        has no clauses.

    Raises:
        ContractGrammarBindingError: When any emitted lambda leaves a free
            variable unbound.
    """
    return emit_icontract_decorators(spec)


# ---------------------------------------------------------------------------
# attribute_blame
# ---------------------------------------------------------------------------


def attribute_blame(
    violation_type: str,
    spec: Optional[ContractSpec] = None,
) -> BlameTarget:
    """Map a contract violation type to the responsible party.

    Implements Meyer's DbC blame rule:
    - ``pre`` violations: the **caller** passed invalid inputs.
    - ``post`` / ``inv`` violations: the **implementer** produced incorrect output.

    Args:
        violation_type: One of ``"pre"``, ``"post"``, or ``"inv"``.
        spec: Optional :class:`ContractSpec` (unused currently, reserved for
              future context-aware blame enrichment).

    Returns:
        :attr:`BlameTarget.CALLER` for ``"pre"``;
        :attr:`BlameTarget.IMPLEMENTER` for ``"post"`` or ``"inv"``.

    Raises:
        ValueError: When *violation_type* is not a recognised contract clause.
    """
    mapping: dict[str, BlameTarget] = {
        "pre": BlameTarget.CALLER,
        "post": BlameTarget.IMPLEMENTER,
        "inv": BlameTarget.IMPLEMENTER,
    }
    if violation_type not in mapping:
        raise ValueError(
            f"Unknown violation_type {violation_type!r}. "
            f"Expected one of: {list(mapping)}"
        )
    return mapping[violation_type]


# ---------------------------------------------------------------------------
# ContractParseError
# ---------------------------------------------------------------------------


class ContractParseError(ValueError):
    """Raised when a contract clause dict contains an unrecognised sub-key."""


# ---------------------------------------------------------------------------
# Clause-level parsers
# ---------------------------------------------------------------------------

_KNOWN_KEYS = frozenset({"pre", "post", "inv", "raises", "behavior"})


@dataclass(frozen=True)
class PreClause:
    """AST node for a parsed precondition clause."""
    expressions: list[str]


@dataclass(frozen=True)
class PostClause:
    """AST node for a parsed postcondition clause."""
    expressions: list[str]


@dataclass(frozen=True)
class InvClause:
    """AST node for a parsed invariant clause."""
    expressions: list[str]


def parse_pre_clause(ac: dict) -> PreClause:
    """Parse the ``pre`` sub-key and return a precondition AST node.

    Args:
        ac: Behavior AC dict that may contain a ``pre`` key.

    Returns:
        :class:`PreClause` with normalised expression list.
    """
    return PreClause(expressions=_normalise_to_list(ac.get("pre")))


def parse_post_clause(ac: dict) -> PostClause:
    """Parse the ``post`` sub-key and return a postcondition AST node.

    Args:
        ac: Behavior AC dict that may contain a ``post`` key.

    Returns:
        :class:`PostClause` with normalised expression list.
    """
    return PostClause(expressions=_normalise_to_list(ac.get("post")))


def parse_inv_clause(ac: dict) -> InvClause:
    """Parse the ``inv`` sub-key and return an invariant AST node.

    Args:
        ac: Behavior AC dict that may contain an ``inv`` key.

    Returns:
        :class:`InvClause` with normalised expression list.
    """
    return InvClause(expressions=_normalise_to_list(ac.get("inv")))


def parse_raises_clause(ac: dict) -> list[str]:
    """Parse the ``raises`` sub-key and return a list of exception type names.

    Args:
        ac: Behavior AC dict that may contain a ``raises`` key.

    Returns:
        List of exception type name strings (may be empty).
    """
    return _normalise_to_list(ac.get("raises"))


# ---------------------------------------------------------------------------
# Blame assignment convenience functions
# ---------------------------------------------------------------------------


def assign_blame_on_pre_violation() -> str:
    """Return the blame target string for a precondition violation.

    Per Meyer's DbC rule, the **caller** is responsible when a precondition
    fires (they passed invalid inputs).

    Returns:
        The string ``"caller"``.
    """
    return "caller"


def assign_blame_on_post_violation() -> str:
    """Return the blame target string for a postcondition violation.

    Per Meyer's DbC rule, the **implementer** is responsible when a
    postcondition fires (they returned incorrect output).

    Returns:
        The string ``"implementer"``.
    """
    return "implementer"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def raises_on_malformed_clause(ac: dict) -> None:
    """Raise :exc:`ContractParseError` if *ac* contains any unrecognised sub-key.

    Recognised sub-keys are: ``pre``, ``post``, ``inv``, ``raises``,
    ``behavior``.  Any other key is considered malformed.

    Args:
        ac: Behavior AC dict to validate.

    Raises:
        ContractParseError: When *ac* contains an unrecognised sub-key.
    """
    bad_keys = [k for k in ac if k not in _KNOWN_KEYS]
    if bad_keys:
        raise ContractParseError(
            f"Unrecognised contract sub-key(s): {bad_keys!r}. "
            f"Allowed keys: {sorted(_KNOWN_KEYS)}"
        )
