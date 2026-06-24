"""Brownfield example module for BF-6 characterization tests.

Provides a ``Bar`` class whose ``method`` serves as the concrete target
used in acceptance-criteria examples and integration tests for the
characterization AC kind.
"""

from __future__ import annotations


class Bar:
    """Example brownfield class used as a characterization target."""

    def method(self, value: int) -> str:
        """Return a string representation of *value* doubled.

        Args:
            value: An integer to double.

        Returns:
            A string in the form ``'result=<value*2>'``.

        Raises:
            ValueError: If *value* is negative.
        """
        if value < 0:
            raise ValueError(f"value must be non-negative, got {value}")
        return f"result={value * 2}"


def bar_method(value: int) -> str:
    """Module-level wrapper for ``Bar().method`` — usable as a plain function target.

    This is the canonical characterization target for BF-6 tests because
    ``_resolve_target`` resolves ``src/foo/bar.py::bar_method`` to a plain
    callable that can be called with positional args without needing ``self``.

    Args:
        value: An integer to double.

    Returns:
        A string in the form ``'result=<value*2>'``.

    Raises:
        ValueError: If *value* is negative.
    """
    return Bar().method(value)


def sample_inputs() -> list[tuple[int, ...]]:
    """Return representative sample inputs for ``Bar.method``.

    Each element is a positional-argument tuple suitable for passing to
    :func:`bob.acceptance.kinds._prepare_inputs` (or calling directly as
    ``Bar().method(*args)``).

    Boundary cases covered:
      - ``(0,)``  — zero / empty boundary (must not crash).
      - ``(1,)``  — minimal positive input.
      - ``(10,)`` — typical positive input.

    Returns:
        A list of one-element tuples containing integer inputs.
    """
    return [(0,), (1,), (10,)]
