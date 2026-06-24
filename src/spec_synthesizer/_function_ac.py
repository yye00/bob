"""Verbatim-in-prose gate for Function-defined acceptance criteria.

A ``Function defined: <module>.<symbol>`` AC is contractual ONLY when the
exact symbol appears verbatim (as a whole identifier) in the feature's prose
description.  This module provides the guard function that spec_synthesizer
calls before emitting such an AC.
"""
from __future__ import annotations

import re


def should_emit_function_ac(symbol: str, description: str) -> bool:
    """Return True iff *symbol* appears verbatim as a whole identifier in *description*.

    The synthesizer MUST call this before emitting a
    ``Function defined: <module>.<symbol>`` AC.  If it returns False the
    synthesizer must instead emit a capability-/behavior-oriented AC.

    Parameters
    ----------
    symbol:
        The candidate function name (e.g. ``apply_exponential_backoff``).
    description:
        The feature's prose description (human/PEAS text).

    Returns
    -------
    bool
        True only when *symbol* is non-empty, *description* is non-empty, and
        *symbol* appears as a complete identifier (word-boundary match) within
        *description*.  Non-string inputs raise TypeError.
    """
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a str, got {type(symbol).__name__!r}")
    if not isinstance(description, str):
        raise TypeError(f"description must be a str, got {type(description).__name__!r}")
    if not symbol or not symbol.strip():
        return False
    if not description.strip():
        return False
    return bool(re.search(r"\b" + re.escape(symbol) + r"\b", description))
