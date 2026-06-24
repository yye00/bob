"""Tests for Python dependency enumeration from Function defined AC text."""
from bob.orchestrator.env_preflight import (
    enumerate_python_deps_from_function_ac,
    enumerate_deps,
    DepInventory,
)


class TestEnumeratePythonDepsFromFunctionAc:
    def test_extracts_top_level_module(self):
        ac = "Function defined: bob.orchestrator.env_preflight.enumerate_deps"
        result = enumerate_python_deps_from_function_ac([ac])
        assert "bob" in result

    def test_multi_level_module(self):
        ac = "Function defined: mypackage.submodule.my_func (does something)"
        result = enumerate_python_deps_from_function_ac([ac])
        assert "mypackage" in result

    def test_multiple_function_acs(self):
        acs = [
            "Function defined: pkgA.module.func1",
            "Function defined: pkgB.mod.func2",
        ]
        result = enumerate_python_deps_from_function_ac(acs)
        assert "pkgA" in result
        assert "pkgB" in result

    def test_empty_list(self):
        result = enumerate_python_deps_from_function_ac([])
        assert result == set()

    def test_no_function_acs(self):
        result = enumerate_python_deps_from_function_ac(["File exists: foo.py"])
        assert result == set()

    def test_returns_set(self):
        ac = "Function defined: bob.mod.func"
        result = enumerate_python_deps_from_function_ac([ac])
        assert isinstance(result, set)

    def test_deduplicates_same_module(self):
        acs = [
            "Function defined: mymod.func1",
            "Function defined: mymod.func2",
        ]
        result = enumerate_python_deps_from_function_ac(acs)
        assert result == {"mymod"}


class TestEnumerateDepsIncludesPython:
    def test_python_entries_in_inventory(self):
        acs = ["Function defined: requests.api.get (HTTP GET wrapper)"]
        result = enumerate_deps(acs)
        python_names = [e.name for e in result.entries if e.kind == "python"]
        assert "requests" in python_names

    def test_python_dep_kind_is_python(self):
        acs = ["Function defined: yaml.safe_load"]
        result = enumerate_deps(acs)
        python_entries = [e for e in result.entries if e.kind == "python"]
        assert any(e.name == "yaml" for e in python_entries)
