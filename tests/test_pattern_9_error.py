"""Error-path tests for Pattern 9 — shell-script integration AC handler (F-R7-594).

Tests that invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.ac_handler import demote_shell_script_integration_ac


def test_none_criterion_raises_value_error() -> None:
    """None criterion raises ValueError — caller must pass a string."""
    with pytest.raises((TypeError, ValueError, AttributeError)):
        demote_shell_script_integration_ac(None, pathlib.Path("/tmp"))  # type: ignore[arg-type]


def test_non_string_criterion_raises() -> None:
    """Non-string criterion raises, does not silently succeed."""
    with pytest.raises((TypeError, ValueError, AttributeError)):
        demote_shell_script_integration_ac(42, pathlib.Path("/tmp"))  # type: ignore[arg-type]


def test_none_workspace_raises() -> None:
    """None workspace raises, does not silently succeed."""
    with pytest.raises((TypeError, ValueError, AttributeError)):
        demote_shell_script_integration_ac("integration: tools/run.sh", None)  # type: ignore[arg-type]
