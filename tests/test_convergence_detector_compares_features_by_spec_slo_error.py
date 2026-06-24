"""Error-path tests for check_convergence: invalid input raises ValueError.

AC: invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest


def test_error_none_db_a_raises_value_error():
    """Passing None as db_a must raise ValueError."""
    from bob3.convergence import check_convergence

    with pytest.raises(ValueError):
        check_convergence(None, "/tmp/valid.db")  # type: ignore[arg-type]


def test_error_none_db_b_raises_value_error():
    """Passing None as db_b must raise ValueError."""
    from bob3.convergence import check_convergence

    with pytest.raises(ValueError):
        check_convergence("/tmp/valid.db", None)  # type: ignore[arg-type]


def test_error_empty_string_db_a_raises_value_error():
    """Passing an empty string as db_a must raise ValueError."""
    from bob3.convergence import check_convergence

    with pytest.raises(ValueError):
        check_convergence("", "/tmp/valid.db")


def test_error_empty_string_db_b_raises_value_error():
    """Passing an empty string as db_b must raise ValueError."""
    from bob3.convergence import check_convergence

    with pytest.raises(ValueError):
        check_convergence("/tmp/valid.db", "")


def test_error_whitespace_string_db_a_raises_value_error():
    """Passing a whitespace-only string as db_a must raise ValueError."""
    from bob3.convergence import check_convergence

    with pytest.raises(ValueError):
        check_convergence("   ", "/tmp/valid.db")


def test_error_non_path_type_raises_value_error():
    """Passing a non-str/non-Path type must raise ValueError."""
    from bob3.convergence import check_convergence

    with pytest.raises(ValueError):
        check_convergence(42, "/tmp/valid.db")  # type: ignore[arg-type]


def test_error_does_not_silently_succeed_on_invalid_input():
    """Verify the function doesn't silently return a result for None input."""
    from bob3.convergence import check_convergence

    raised = False
    try:
        result = check_convergence(None, None)  # type: ignore[arg-type]
        # If we reach here, it silently returned — that's a failure
    except ValueError:
        raised = True
    except Exception:
        # Any other exception also means it didn't silently succeed
        raised = True

    assert raised, "check_convergence must not silently succeed on None inputs"
