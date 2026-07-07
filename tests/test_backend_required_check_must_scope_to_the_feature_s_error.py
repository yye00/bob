"""Error-path tests: invalid input raises ValueError, no silent success.

Feature 91fee1a2 — hippy.verifier.backend_required_check.
"""

from __future__ import annotations

import pytest

from hippy.verifier import (
    backend_required_check,
    has_simulation_admission,
    scope_to_modified_files,
)


def test_has_simulation_admission_none_raises_value_error():
    with pytest.raises(ValueError):
        has_simulation_admission(None)


def test_has_simulation_admission_non_str_raises_value_error():
    with pytest.raises(ValueError):
        has_simulation_admission(123)


def test_backend_required_check_none_files_raises_value_error():
    with pytest.raises(ValueError):
        backend_required_check(None)


def test_backend_required_check_non_iterable_raises_value_error():
    with pytest.raises(ValueError):
        backend_required_check(42)


def test_scope_to_modified_files_none_files_raises_value_error():
    with pytest.raises(ValueError):
        scope_to_modified_files(None, feature_start_time=0.0)
