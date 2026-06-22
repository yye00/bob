"""AC kind registry for bob3.acceptance.

Maps AC kind names to their parse and evaluation functions. The
characterization kind is pre-registered here.
"""

from __future__ import annotations

from typing import Any, Callable

from bob3.acceptance.kinds import (
    CharacterizationAC,
    SnapshotResult,
    VerificationResult,
    observe_and_snapshot,
    parse_characterization_ac,
    verify_against_snapshots,
)

# Registry entry: (parser, observer, verifier)
_REGISTRY: dict[str, dict[str, Callable[..., Any]]] = {}


def register_ac_kind(
    name: str,
    *,
    parser: Callable[..., Any],
    observer: Callable[..., Any] | None = None,
    verifier: Callable[..., Any] | None = None,
) -> None:
    """Register an AC kind by name with its parser and optional phase functions.

    Args:
        name:     Unique kind identifier (e.g. ``'characterization'``).
        parser:   Callable that accepts a raw AC spec and returns a typed AC
                  object, or ``None`` if the spec does not match this kind.
        observer: Optional callable for the observer (snapshot) phase.
        verifier: Optional callable for the verifier (diff) phase.
    """
    _REGISTRY[name] = {
        "parser": parser,
        "observer": observer,
        "verifier": verifier,
    }


def get_ac_kind(name: str) -> dict[str, Callable[..., Any]] | None:
    """Return the registry entry for *name*, or ``None`` if not registered."""
    return _REGISTRY.get(name)


def list_registered_kinds() -> list[str]:
    """Return the names of all registered AC kinds."""
    return sorted(_REGISTRY.keys())


# Pre-register the 'characterization' kind.
register_ac_kind(
    "characterization",
    parser=parse_characterization_ac,
    observer=observe_and_snapshot,
    verifier=verify_against_snapshots,
)

__all__ = [
    "get_ac_kind",
    "list_registered_kinds",
    "register_ac_kind",
]
