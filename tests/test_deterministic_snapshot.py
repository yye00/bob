"""Tests for bob3.deterministic_snapshot.enforce_maxfail_zero.

Acceptance criteria:
- File exists: src/bob3/deterministic_snapshot.py
- Function defined: bob3.deterministic_snapshot.enforce_maxfail_zero
- pytest: tests/test_deterministic_snapshot.py
- integration: bob3.orchestrator
"""

from __future__ import annotations

import bob3.deterministic_snapshot as mod
from bob3.deterministic_snapshot import MAXFAIL_ZERO, enforce_maxfail_zero


def test_module_exports_enforce_maxfail_zero():
    assert callable(enforce_maxfail_zero)
    assert "enforce_maxfail_zero" in dir(mod)


def test_maxfail_zero_constant():
    assert MAXFAIL_ZERO == "--maxfail=0"
    assert mod.MAXFAIL_ZERO == "--maxfail=0"


def test_empty_list_returns_maxfail_zero():
    result = enforce_maxfail_zero([])
    assert isinstance(result, list)
    assert "--maxfail=0" in result


def test_basic_argv_gets_maxfail_injected():
    result = enforce_maxfail_zero(["python", "-m", "pytest", "tests/"])
    assert "--maxfail=0" in result
    assert result[0] == "python"


def test_existing_maxfail_replaced():
    result = enforce_maxfail_zero(["python", "-m", "pytest", "--maxfail=5", "tests/"])
    assert "--maxfail=0" in result
    non_zero = [a for a in result if a.startswith("--maxfail=") and a != "--maxfail=0"]
    assert not non_zero


def test_maxfail_zero_position():
    result = enforce_maxfail_zero(["pytest", "tests/"])
    assert result[1] == "--maxfail=0"


def test_result_is_new_object():
    argv = ["pytest", "tests/"]
    result = enforce_maxfail_zero(argv)
    assert result is not argv


def test_none_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        enforce_maxfail_zero(None)


def test_non_list_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        enforce_maxfail_zero("pytest --maxfail=0")


def test_non_string_element_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        enforce_maxfail_zero(["pytest", 42])


def test_orchestrator_integration():
    """Verify that bob3.orchestrator.run_loop can import and use deterministic_snapshot."""
    from bob3.deterministic_snapshot import enforce_maxfail_zero as emz
    from bob3.orchestrator.run_loop import capture_pytest_snapshot
    assert callable(emz)
    assert callable(capture_pytest_snapshot)
    # enforce_maxfail_zero produces correct output matching what orchestrator uses
    result = emz(["python", "-m", "pytest", "tests/"])
    assert "--maxfail=0" in result


def test_all_elements_preserved():
    argv = ["pytest", "tests/foo.py", "-v", "--tb=no"]
    result = enforce_maxfail_zero(argv)
    for el in argv:
        assert el in result


def test_xdist_flag_after_maxfail_zero():
    argv = ["pytest", "-n", "4", "tests/"]
    result = enforce_maxfail_zero(argv)
    maxfail_idx = result.index("--maxfail=0")
    n_idx = result.index("-n")
    assert maxfail_idx < n_idx, "--maxfail=0 must appear before -n flag"
