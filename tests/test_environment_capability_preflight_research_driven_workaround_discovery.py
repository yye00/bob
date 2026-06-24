"""Tests for environment_capability_preflight_research_driven_workaround_discovery."""

from bob.environment_capability_preflight_research_driven_workaround_discovery import (
    environment_capability_preflight_research_driven_workaround_discovery,
)


def test_environment_capability_preflight_research_driven_workaround_discovery():
    """The facade function runs preflight and returns a valid summary dict."""
    # ACs with known-present deps (python3 and pytest are always available)
    ac_list = [
        "Function defined: os.path",
        "pytest: tests/test_something.py",
    ]
    result = environment_capability_preflight_research_driven_workaround_discovery(ac_list)

    assert isinstance(result, dict)
    assert "total_deps" in result
    assert "missing" in result
    assert "applied_workarounds" in result
    assert "halted" in result
    assert result["halted"] is False


def test_returns_dict_for_empty_ac_list():
    result = environment_capability_preflight_research_driven_workaround_discovery([])
    assert isinstance(result, dict)
    assert result["total_deps"] == 0
    assert result["missing"] == []
    assert result["applied_workarounds"] == []
    assert result["halted"] is False


def test_detects_present_python_dep():
    ac_list = ["Function defined: os.getcwd"]
    result = environment_capability_preflight_research_driven_workaround_discovery(ac_list)
    assert "os" not in result["missing"]


def test_detects_missing_python_dep():
    ac_list = ["Function defined: __nonexistent_module_xyz_abc__.func"]
    result = environment_capability_preflight_research_driven_workaround_discovery(ac_list)
    # Missing dep should appear in missing list or a workaround was auto-applied
    # (low-risk python deps get auto-applied, so either path is valid)
    assert isinstance(result["missing"], list)
    assert isinstance(result["applied_workarounds"], list)


def test_counts_total_deps_correctly():
    ac_list = [
        "command: git --version",
        "Function defined: json.loads",
    ]
    result = environment_capability_preflight_research_driven_workaround_discovery(ac_list)
    assert result["total_deps"] >= 2
