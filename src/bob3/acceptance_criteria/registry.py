"""Registry for bob3 acceptance-criteria grammar handlers.

Maps AC grammar names to their handler classes so the verifier and codegen
can dispatch by grammar type.

Registered grammars
-------------------
1. ``file_exists``   — ``File exists: <path>``
2. ``function``      — ``Function defined: <module>.<name>``
3. ``pytest``        — ``pytest: <file>``
4. ``integration``   — ``integration: <module>``
5. ``behavior``      — EARS behavior ACs (When/If/While/Where + shall)
6. ``contract``      — Contract/lambda grammars
7. ``property``      — ``property: <name> for <generator> assert <predicate>`` (seventh grammar)

Public API
----------
- ``AC_REGISTRY``    — dict mapping grammar name → handler class.
- ``get_handler``    — look up a handler by grammar name.
- ``register``       — register a custom handler class.
"""

from __future__ import annotations

from typing import Any

from bob3.acceptance_criteria.key_examples import KeyExampleAC
from bob3.acceptance_criteria.property_based import PropertyBasedAC


__all__ = [
    "AC_REGISTRY",
    "get_handler",
    "register",
    "PropertyBasedAC",
    "KeyExampleAC",
]


AC_REGISTRY: dict[str, type] = {
    "property": PropertyBasedAC,
    "key_example": KeyExampleAC,
}


def get_handler(grammar: str) -> type | None:
    """Return the handler class for *grammar*, or ``None`` if not registered.

    Args:
        grammar: Grammar name (e.g. ``"property"``, ``"key_example"``).

    Returns:
        The registered handler class, or ``None``.
    """
    return AC_REGISTRY.get(grammar)


def register(grammar: str, handler: type) -> None:
    """Register a handler class for *grammar*.

    Args:
        grammar: Grammar name key.
        handler: Handler class to associate with this grammar.

    Raises:
        ValueError: When *grammar* is empty or *handler* is not a class.
    """
    if not grammar:
        raise ValueError("Grammar name must be non-empty.")
    if not isinstance(handler, type):
        raise ValueError(f"Handler must be a class, got {type(handler).__name__!r}.")
    AC_REGISTRY[grammar] = handler
