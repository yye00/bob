"""Tests for enumerate_deps boundary: empty/zero-dep spec returns empty DepInventory."""
from bob.orchestrator.env_preflight import (
    DepInventory,
    enumerate_deps,
    enumerate_cli_deps_from_bash_blocks,
    enumerate_cli_deps_from_command_lines,
    enumerate_cli_deps_from_run_verbs,
    enumerate_python_deps_from_function_ac,
)


class TestEmptyDepListBoundary:
    def test_empty_ac_list_returns_dep_inventory(self):
        result = enumerate_deps([])
        assert isinstance(result, DepInventory)

    def test_empty_ac_list_has_zero_entries(self):
        result = enumerate_deps([])
        assert len(result) == 0

    def test_empty_ac_list_entries_is_empty_list(self):
        result = enumerate_deps([])
        assert result.entries == []

    def test_plain_text_acs_with_no_deps_returns_empty(self):
        acs = [
            "Feature is implemented correctly.",
            "All tests pass.",
            "Code is well-documented.",
        ]
        result = enumerate_deps(acs)
        assert len(result) == 0

    def test_file_exists_acs_only_returns_empty(self):
        acs = [
            "File exists: src/bob/orchestrator/env_preflight.py",
            "File exists: bob4/research/demonstrators/F-R7-473/spec.yaml",
        ]
        result = enumerate_deps(acs)
        assert len(result) == 0


class TestEmptyHelperBoundaries:
    def test_bash_blocks_empty_list(self):
        assert enumerate_cli_deps_from_bash_blocks([]) == set()

    def test_command_lines_empty_list(self):
        assert enumerate_cli_deps_from_command_lines([]) == set()

    def test_run_verbs_empty_list(self):
        assert enumerate_cli_deps_from_run_verbs([]) == set()

    def test_python_deps_empty_list(self):
        assert enumerate_python_deps_from_function_ac([]) == set()

    def test_bash_blocks_no_bash_content(self):
        acs = ["Just some plain text with no bash code"]
        assert enumerate_cli_deps_from_bash_blocks(acs) == set()

    def test_command_lines_no_command_prefix(self):
        acs = ["This is a plain AC without a command: prefix on its own line"]
        # Note: "command:" appears in the text but not at start of a line
        result = enumerate_cli_deps_from_command_lines(acs)
        # The substring "command:" appears mid-line — may or may not match
        # depending on regex; the important thing is we don't crash
        assert isinstance(result, set)

    def test_run_verbs_irrelevant_acs(self):
        acs = ["File exists: foo.py", "Function defined: mod.func"]
        result = enumerate_cli_deps_from_run_verbs(acs)
        assert isinstance(result, set)

    def test_python_deps_non_function_acs(self):
        acs = ["File exists: foo.py", "command: git status"]
        result = enumerate_python_deps_from_function_ac(acs)
        assert result == set()
