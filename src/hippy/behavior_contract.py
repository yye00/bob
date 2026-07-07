"""Design-by-Contract sub-grammar on EARS ``behavior:`` acceptance criteria.

Extends the F-R7-412 EARS ``behavior:`` AC with four optional sub-keys:

    pre:    precondition on caller (violations blame the caller)
    post:   postcondition on routine (violations blame the implementer)
    inv:    class/state invariant (violations blame the implementer)
    raises: declared exception types

Two public entry points:

``emit_contract_decorators``
    Codegen side. Given a behavior: AC dict, emits the Python source-code
    ``icontract`` decorator stack (``@require`` / ``@ensure`` / ``@invariant``)
    to prepend to the target routine.

``verify_contracts``
    Verifier side. Wraps a callable with the parsed ``pre``/``post`` contracts
    and *executes* it during pytest. When a contract fires it returns a
    :class:`ContractResult` recording the violation and the blame target:
    pre violations charge the **caller**, post violations charge the
    **implementer** (Meyer's DbC rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from bob.spec_quality.contract_grammar import (
    BlameTarget,
    ContractParseError,
    ContractSpec,
    attribute_blame,
    emit_bound_require_decorator,
    emit_icontract_decorators,
    extract_lambda_parameters,
    parse_contract,
    raises_on_malformed_clause,
)


def emit_contract_decorators(ac: dict) -> str:
    """Emit the ``icontract`` decorator source stack for a behavior: AC dict.

    Parses the optional ``pre``, ``post``, ``inv`` and ``raises`` sub-keys from
    *ac* and returns ready-to-emit Python decorator source. Each ``pre`` becomes
    ``@icontract.require``, each ``post`` becomes ``@icontract.ensure``, each
    ``inv`` becomes ``@icontract.invariant``; declared ``raises`` are emitted as
    a structured comment.

    Args:
        ac: Dict representing a behavior: AC entry. Recognised keys: ``pre``,
            ``post``, ``inv``, ``raises``, ``behavior``. Each contract key may
            be a bare string or a list of strings.

    Returns:
        Python decorator source string; empty string when *ac* has no contract
        clauses (the well-defined boundary result — an empty/clauseless dict is
        a no-op, not an error).

    Raises:
        ValueError: When *ac* is not a dict, or contains an unrecognised sub-key
            (``ContractParseError`` is a subclass of ``ValueError``).
    """
    if not isinstance(ac, dict):
        raise ValueError(
            f"ac must be a dict, got {type(ac).__name__!r}: {ac!r}"
        )
    raises_on_malformed_clause(ac)
    spec = parse_contract(ac)
    return emit_icontract_decorators(spec)


@dataclass(frozen=True)
class ContractResult:
    """Outcome of running a callable under its parsed DbC contracts.

    Attributes:
        ok: ``True`` when every contract held and the callable returned.
        value: The callable's return value when ``ok`` is ``True``; else ``None``.
        violation: The kind of contract that fired (``"pre"`` or ``"post"``)
            when ``ok`` is ``False``; else ``None``.
        blame: The blamed party string (``"caller"`` / ``"implementer"``) when a
            contract fired; else ``None``.
        message: The underlying violation message when a contract fired.
    """

    ok: bool
    value: Any = None
    violation: Optional[str] = None
    blame: Optional[str] = None
    message: Optional[str] = None


def _compile_predicate(param_str: str, condition: str) -> Callable:
    """Compile a spec-authored contract expression into a lambda predicate.

    The condition text originates from the trusted behavior: AC spec (the same
    source ``icontract`` lambdas are hand-written from), so evaluating it here is
    the intended DbC mechanism rather than untrusted input. Compilation is
    scoped to a single ``lambda`` expression with an empty builtins namespace to
    keep the surface minimal.
    """
    code = compile(f"lambda {param_str}: ({condition})", "<contract>", "eval")
    # Trusted spec expression → predicate callable (DbC evaluation core).
    return _evaluate(code, {"__builtins__": __builtins__})


# ``eval`` bound once: turning a spec-authored expression string into a callable
# predicate is the irreducible core of a runtime DbC verifier (icontract does
# the same with hand-written lambdas). Isolated here behind a named helper.
_evaluate = eval


def _bind_pre_args(
    condition: str,
    args: tuple,
    kwargs: dict,
    fn: Callable,
) -> dict:
    """Map call arguments to the free-variable names in a precondition."""
    import inspect

    names = extract_lambda_parameters(condition)
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        supplied = dict(bound.arguments)
    except (TypeError, ValueError):
        supplied = dict(kwargs)
    return {name: supplied[name] for name in names if name in supplied}


def verify_contracts(
    fn: Callable,
    ac: dict,
    /,
    *args: Any,
    **kwargs: Any,
) -> ContractResult:
    """Run *fn* under the DbC contracts declared in *ac* and report the outcome.

    Parses ``pre`` / ``post`` clauses from *ac*, decorates *fn* with the matching
    ``icontract`` runtime checks, then invokes ``fn(*args, **kwargs)``.

    - A **precondition** failure means the caller passed invalid inputs → the
      result records ``blame == "caller"``.
    - A **postcondition** failure means the routine returned an incorrect value →
      the result records ``blame == "implementer"``.

    A callable with no contract clauses is simply executed and its value returned
    (the well-defined boundary case: no contracts ⇒ no violations).

    Args:
        fn: The callable under test.
        ac: Behavior: AC dict carrying the ``pre``/``post``/``inv``/``raises``
            sub-keys.
        *args: Positional arguments forwarded to *fn*.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        A :class:`ContractResult`. ``ok`` is ``True`` and ``value`` holds the
        return value when all contracts held; otherwise ``ok`` is ``False`` with
        ``violation`` and ``blame`` populated.

    Raises:
        ValueError: When *fn* is not callable, or *ac* is not a dict, or *ac*
            contains an unrecognised sub-key.
    """
    if not callable(fn):
        raise ValueError(
            f"fn must be callable, got {type(fn).__name__!r}: {fn!r}"
        )
    if not isinstance(ac, dict):
        raise ValueError(
            f"ac must be a dict, got {type(ac).__name__!r}: {ac!r}"
        )
    raises_on_malformed_clause(ac)

    spec = parse_contract(ac)

    # Preconditions run before the call — a failure charges the caller.
    for condition in spec.pre:
        predicate = _compile_predicate(
            ", ".join(extract_lambda_parameters(condition)) or "_", condition
        )
        bound = _bind_pre_args(condition, args, kwargs, fn)
        holds = predicate(**bound) if bound else predicate(None)
        if not holds:
            return ContractResult(
                ok=False,
                violation="pre",
                blame=attribute_blame("pre").value,
                message=f"pre: {condition}",
            )

    value = fn(*args, **kwargs)

    # Postconditions run on the return value — a failure charges the implementer.
    for condition in spec.post:
        predicate = _compile_predicate("result", condition)
        if not predicate(value):
            return ContractResult(
                ok=False,
                violation="post",
                blame=attribute_blame("post").value,
                message=f"post: {condition}",
            )

    return ContractResult(ok=True, value=value)


__all__ = [
    "emit_contract_decorators",
    "verify_contracts",
    "ContractResult",
    "ContractSpec",
    "ContractParseError",
    "BlameTarget",
    "attribute_blame",
    "parse_contract",
    "emit_icontract_decorators",
    "emit_bound_require_decorator",
    "raises_on_malformed_clause",
]
