"""Convergence detection for bob3 cross-generation comparison.

Compares feature sets across generations by spec_slot (stable YAML key),
not by UUID (which is minted fresh on every ``bob3 init``).
"""

from __future__ import annotations

import pathlib
from typing import Union

from bob3.migrations.add_spec_slot import get_completed_spec_slots


def check_convergence_by_spec_slot(
    db_a: Union[str, pathlib.Path],
    db_b: Union[str, pathlib.Path],
) -> tuple[bool, set[str]]:
    """Compare two bob3 databases by completed spec_slot sets.

    Alias for check_convergence that makes the comparison axis explicit.
    Feature IDs (UUID) change every generation; spec_slot is stable.
    Only completed features with non-NULL spec_slot are compared.

    Parameters
    ----------
    db_a:
        Path to the first generation's SQLite database.
    db_b:
        Path to the second generation's SQLite database.

    Returns
    -------
    tuple[bool, set[str]]
        ``(converged, diff)`` — converged is True when the symmetric
        difference of spec_slot sets is empty.

    Raises
    ------
    ValueError
        If either path is not a non-empty string or Path-like.
    """
    return check_convergence(db_a, db_b)


def check_convergence(
    db_a: Union[str, pathlib.Path],
    db_b: Union[str, pathlib.Path],
) -> tuple[bool, set[str]]:
    """Compare two bob3 databases by completed spec_slot sets.

    Feature IDs (UUID) change every generation; spec_slot is stable.
    Only completed features with non-NULL spec_slot are compared.

    Parameters
    ----------
    db_a:
        Path to the first generation's SQLite database.
    db_b:
        Path to the second generation's SQLite database.

    Returns
    -------
    tuple[bool, set[str]]
        ``(converged, diff)`` — converged is True when the symmetric
        difference of spec_slot sets is empty.

    Raises
    ------
    ValueError
        If either path is not a non-empty string or Path-like.
    """
    _validate_db_path(db_a, "db_a")
    _validate_db_path(db_b, "db_b")

    slots_a = get_completed_spec_slots(db_a)
    slots_b = get_completed_spec_slots(db_b)
    diff = slots_a.symmetric_difference(slots_b)
    return (len(diff) == 0, diff)


def _validate_db_path(path: Union[str, pathlib.Path], name: str) -> None:
    if path is None:
        raise ValueError(f"{name} must not be None")
    if isinstance(path, str) and not path.strip():
        raise ValueError(f"{name} must not be an empty string")
    if not isinstance(path, (str, pathlib.Path)):
        raise ValueError(f"{name} must be a str or Path, got {type(path).__name__}")
