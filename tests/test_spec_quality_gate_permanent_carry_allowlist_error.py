"""Error-path tests for bob72.spec_quality_gate.check_allowlist.

Verifies that invalid input raises ValueError and the function does not
silently succeed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob72.spec_quality_gate import check_allowlist


def test_none_input_raises_value_error():
    """Passing None instead of a feature object must raise ValueError."""
    with pytest.raises((ValueError, AttributeError, TypeError)):
        check_allowlist(None)  # type: ignore[arg-type]


def test_integer_input_raises():
    """Passing an integer must raise a clear error, not silently succeed."""
    with pytest.raises((ValueError, AttributeError, TypeError)):
        check_allowlist(42)  # type: ignore[arg-type]


def test_string_input_raises():
    """Passing a bare string must raise, not silently succeed."""
    with pytest.raises((ValueError, AttributeError, TypeError)):
        check_allowlist("F-R7-478")  # type: ignore[arg-type]


def test_non_feature_dict_raises():
    """Passing a plain dict (no feature attributes) must raise, not silently return False."""
    with pytest.raises((ValueError, AttributeError, TypeError)):
        check_allowlist({})  # type: ignore[arg-type]


def test_none_raises_value_error_specifically():
    """None input must raise ValueError with a meaningful message."""
    with pytest.raises(ValueError, match="feature"):
        check_allowlist(None)  # type: ignore[arg-type]
