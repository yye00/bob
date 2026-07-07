"""Boundary tests: empty / zero / minimum input returns a well-defined result.

Feature 91fee1a2 — hippy.verifier.backend_required_check.
"""

from __future__ import annotations

from hippy.verifier import (
    backend_required_check,
    has_simulation_admission,
    scope_to_modified_files,
)


def test_backend_required_check_empty_file_list_returns_result():
    result = backend_required_check([])
    assert isinstance(result, dict)
    assert result["passed"] is False
    assert isinstance(result["reason"], str)


def test_backend_required_check_empty_list_harness_exempt_passes():
    result = backend_required_check([], is_harness=True)
    assert result["passed"] is True


def test_has_simulation_admission_empty_string_returns_false():
    assert has_simulation_admission("") is False


def test_scope_to_modified_files_empty_returns_empty_list():
    assert scope_to_modified_files([], feature_start_time=0.0) == []


def test_scope_to_modified_files_none_start_time_returns_all():
    # With no feature_start_time the window is a default lookback; a fresh
    # temp-less list falls back to the full list rather than raising.
    import pathlib

    result = scope_to_modified_files([], feature_start_time=None)
    assert result == []
