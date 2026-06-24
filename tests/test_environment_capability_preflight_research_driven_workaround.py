"""Tests for environment_capability_preflight_research_driven_workaround."""

from bob3.environment_capability_preflight_research_driven_workaround import (
    environment_capability_preflight_research_driven_workaround,
)


def test_environment_capability_preflight_research_driven_workaround():
    """The facade function runs preflight and returns a valid summary dict."""
    ac_list = [
        "Function defined: os.path",
        "pytest: tests/test_something.py",
    ]
    result = environment_capability_preflight_research_driven_workaround(ac_list)

    assert isinstance(result, dict)
    assert "total_deps" in result
    assert "missing" in result
    assert "applied_workarounds" in result
    assert "halted" in result
    assert result["halted"] is False


def test_empty_ac_list():
    result = environment_capability_preflight_research_driven_workaround([])
    assert isinstance(result, dict)
    assert result["total_deps"] == 0
    assert result["missing"] == []
    assert result["applied_workarounds"] == []
    assert result["halted"] is False


def test_detects_present_python_dep():
    ac_list = ["Function defined: os.getcwd"]
    result = environment_capability_preflight_research_driven_workaround(ac_list)
    assert "os" not in result["missing"]


def test_counts_total_deps():
    ac_list = [
        "command: git --version",
        "Function defined: json.loads",
    ]
    result = environment_capability_preflight_research_driven_workaround(ac_list)
    assert result["total_deps"] >= 2
