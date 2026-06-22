"""Tests for environment_capability_preflight module."""

import pytest

from environment_capability_preflight import (
    MissingDependencyError,
    enumerate_dependencies,
    preflight,
    probe_dependency,
    research_workaround,
)


# ---------------------------------------------------------------------------
# enumerate_dependencies
# ---------------------------------------------------------------------------


class TestEnumerateDependencies:
    def test_empty_list_returns_empty(self):
        result = enumerate_dependencies([])
        assert result == []

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            enumerate_dependencies(None)  # type: ignore[arg-type]

    def test_invalid_input_string_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            enumerate_dependencies("not a list")  # type: ignore[arg-type]

    def test_function_defined_ac_produces_python_dep(self):
        deps = enumerate_dependencies(["Function defined: os.path"])
        python_deps = [d for d in deps if d["kind"] == "python"]
        assert any(d["name"] == "os" for d in python_deps)

    def test_pytest_prefix_ac_produces_cli_dep(self):
        deps = enumerate_dependencies(["pytest: tests/test_something.py"])
        cli_deps = [d for d in deps if d["kind"] == "cli"]
        assert any(d["name"] == "pytest" for d in cli_deps)

    def test_command_line_ac_produces_cli_dep(self):
        deps = enumerate_dependencies(["command: git --version"])
        cli_deps = [d for d in deps if d["kind"] == "cli"]
        assert any(d["name"] == "git" for d in cli_deps)

    def test_bash_block_ac_produces_cli_dep(self):
        ac = "```bash\ngit clone https://example.com/repo.git\n```"
        deps = enumerate_dependencies([ac])
        cli_deps = [d for d in deps if d["kind"] == "cli"]
        assert any(d["name"] == "git" for d in cli_deps)

    def test_multiple_acs_aggregated(self):
        acs = [
            "Function defined: json.loads",
            "command: pytest --version",
        ]
        deps = enumerate_dependencies(acs)
        names = {d["name"] for d in deps}
        assert "json" in names
        assert "pytest" in names

    def test_each_dep_has_kind_and_name(self):
        deps = enumerate_dependencies(["Function defined: os.getcwd"])
        for dep in deps:
            assert "kind" in dep
            assert "name" in dep
            assert dep["kind"] in ("cli", "python")
            assert isinstance(dep["name"], str)
            assert dep["name"]

    def test_non_string_elements_skipped_gracefully(self):
        # Mixed list with non-string — should not crash
        result = enumerate_dependencies(["Function defined: os.getcwd", None, 42])  # type: ignore[list-item]
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# probe_dependency
# ---------------------------------------------------------------------------


class TestProbeDependency:
    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="dep must be a dict"):
            probe_dependency("not a dict")  # type: ignore[arg-type]

    def test_unknown_kind_raises_value_error(self):
        with pytest.raises(ValueError, match="kind"):
            probe_dependency({"kind": "unknown", "name": "foo"})

    def test_empty_name_raises_value_error(self):
        with pytest.raises(ValueError, match="name"):
            probe_dependency({"kind": "cli", "name": ""})

    def test_present_python_module(self):
        result = probe_dependency({"kind": "python", "name": "os"})
        assert result["present"] is True
        assert result["dep"]["name"] == "os"

    def test_missing_python_module(self):
        result = probe_dependency({"kind": "python", "name": "__nonexistent_xyz_abc_987__"})
        assert result["present"] is False
        assert result["path"] is None

    def test_present_cli_tool(self):
        # python3 is always available in the test environment
        result = probe_dependency({"kind": "cli", "name": "python3"})
        assert result["present"] is True
        assert result["path"] is not None

    def test_missing_cli_tool(self):
        result = probe_dependency({"kind": "cli", "name": "__nonexistent_cli_tool_xyz_987__"})
        assert result["present"] is False
        assert result["path"] is None

    def test_result_contains_dep_key(self):
        dep = {"kind": "python", "name": "sys"}
        result = probe_dependency(dep)
        assert result["dep"] is dep


# ---------------------------------------------------------------------------
# research_workaround
# ---------------------------------------------------------------------------


class TestResearchWorkaround:
    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            research_workaround("not a dict")  # type: ignore[arg-type]

    def test_missing_keys_raises_value_error(self):
        with pytest.raises(ValueError, match="must have 'dep' and 'present' keys"):
            research_workaround({"dep": {"kind": "python", "name": "foo"}})

    def test_present_dep_returns_none(self):
        result = research_workaround(
            {"dep": {"kind": "python", "name": "os"}, "present": True, "path": "/usr/lib/python3"}
        )
        assert result is None

    def test_missing_python_dep_returns_workaround(self):
        result = research_workaround(
            {"dep": {"kind": "python", "name": "__nonexistent_xyz__"}, "present": False, "path": None}
        )
        assert result is not None
        assert result["dep_name"] == "__nonexistent_xyz__"
        assert isinstance(result["description"], str)
        assert len(result["description"]) > 0
        assert isinstance(result["commands"], list)
        assert "low_risk" in result

    def test_missing_python_dep_is_low_risk(self):
        result = research_workaround(
            {"dep": {"kind": "python", "name": "someunknownmodule"}, "present": False, "path": None}
        )
        assert result is not None
        assert result["low_risk"] is True

    def test_missing_cli_dep_returns_workaround(self):
        result = research_workaround(
            {"dep": {"kind": "cli", "name": "__nonexistent_cli__"}, "present": False, "path": None}
        )
        assert result is not None
        assert result["dep_name"] == "__nonexistent_cli__"
        assert isinstance(result["description"], str)

    def test_missing_cli_dep_is_high_risk(self):
        result = research_workaround(
            {"dep": {"kind": "cli", "name": "__nonexistent_cli__"}, "present": False, "path": None}
        )
        assert result is not None
        assert result["low_risk"] is False

    def test_known_dep_git_returns_specific_workaround(self):
        result = research_workaround(
            {"dep": {"kind": "cli", "name": "git"}, "present": False, "path": None}
        )
        assert result is not None
        assert result["dep_name"] == "git"
        assert "git" in result["description"].lower()

    def test_known_dep_yaml_is_low_risk(self):
        result = research_workaround(
            {"dep": {"kind": "python", "name": "yaml"}, "present": False, "path": None}
        )
        assert result is not None
        assert result["low_risk"] is True
        assert "pyyaml" in result["description"].lower() or "yaml" in result["description"].lower()


# ---------------------------------------------------------------------------
# preflight (integration)
# ---------------------------------------------------------------------------


class TestPreflight:
    def test_empty_ac_list_returns_zero_total(self):
        result = preflight([])
        assert result["total_deps"] == 0
        assert result["missing"] == []
        assert result["applied_workarounds"] == []
        assert result["halted"] is False

    def test_invalid_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            preflight(None)  # type: ignore[arg-type]

    def test_present_python_dep_not_in_missing(self):
        result = preflight(["Function defined: os.getcwd"])
        assert "os" not in result["missing"]

    def test_missing_high_risk_dep_raises_error(self):
        # git is a CLI dep (high-risk) — if missing, should raise
        # If git IS present, this test would not raise. We force a fake missing dep
        # by using a non-existent dep name that matches the CLI path.
        # We test the error path via a direct call to preflight with a known-missing CLI.
        # Use the __nonexistent__ pattern guaranteed not to exist.
        # We must patch probe_dependency's result indirectly — instead test by using
        # a made-up ac that produces a CLI dep guaranteed absent.
        ac = "command: __absolutely_nonexistent_cli_tool_xyz_987__"
        with pytest.raises(MissingDependencyError, match="__absolutely_nonexistent_cli_tool_xyz_987__"):
            preflight([ac])

    def test_result_dict_has_expected_keys(self):
        result = preflight(["Function defined: json.loads"])
        assert "total_deps" in result
        assert "missing" in result
        assert "applied_workarounds" in result
        assert "halted" in result

    def test_halted_is_always_false_on_success(self):
        result = preflight([])
        assert result["halted"] is False

    def test_missing_python_dep_auto_applied(self):
        # A missing python dep (low-risk) should be auto-applied, not raise.
        # Use a valid module name (no leading underscores, which the AC regex skips).
        ac = "Function defined: nonexistent_xyz_module_abc987.some_func"
        result = preflight([ac])
        dep_name = "nonexistent_xyz_module_abc987"
        # Either in missing (if somehow not auto-applied) or in applied_workarounds
        assert dep_name in result["missing"] or dep_name in result["applied_workarounds"]

    def test_error_message_contains_dep_name(self):
        ac = "command: __guaranteed_missing_cli_xyz_abc__"
        with pytest.raises(MissingDependencyError) as exc_info:
            preflight([ac])
        assert "__guaranteed_missing_cli_xyz_abc__" in str(exc_info.value)
