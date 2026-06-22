"""Tests for CLI dependency enumeration from acceptance criteria text."""
from bob3.orchestrator.env_preflight import (
    enumerate_cli_deps_from_bash_blocks,
    enumerate_cli_deps_from_command_lines,
    enumerate_cli_deps_from_run_verbs,
    enumerate_deps,
    DepInventory,
)


class TestEnumerateCliDepsFromBashBlocks:
    def test_finds_tool_in_bash_block(self):
        ac = "```bash\nxxd input.bin > output.hex\n```"
        result = enumerate_cli_deps_from_bash_blocks([ac])
        assert "xxd" in result

    def test_finds_tool_in_sh_block(self):
        ac = "```sh\ngit clone https://example.com\n```"
        result = enumerate_cli_deps_from_bash_blocks([ac])
        assert "git" in result

    def test_skips_comment_lines(self):
        ac = "```bash\n# This is a comment\necho hello\n```"
        result = enumerate_cli_deps_from_bash_blocks([ac])
        assert "echo" in result
        assert result == {"echo"}

    def test_empty_ac_list(self):
        result = enumerate_cli_deps_from_bash_blocks([])
        assert result == set()

    def test_no_bash_blocks(self):
        result = enumerate_cli_deps_from_bash_blocks(["No shell here"])
        assert result == set()

    def test_multiple_blocks(self):
        acs = [
            "```bash\nxxd file.bin\n```",
            "```sh\njq '.key' data.json\n```",
        ]
        result = enumerate_cli_deps_from_bash_blocks(acs)
        assert "xxd" in result
        assert "jq" in result


class TestEnumerateCliDepsFromCommandLines:
    def test_finds_command_line(self):
        ac = "command: pytest tests/"
        result = enumerate_cli_deps_from_command_lines([ac])
        assert "pytest" in result

    def test_case_insensitive_prefix(self):
        ac = "Command: git status"
        result = enumerate_cli_deps_from_command_lines([ac])
        assert "git" in result

    def test_multiline_ac_with_command(self):
        ac = "Do something.\ncommand: mytools validate\nEnd."
        result = enumerate_cli_deps_from_command_lines([ac])
        assert "mytools" in result

    def test_empty_list(self):
        result = enumerate_cli_deps_from_command_lines([])
        assert result == set()

    def test_no_command_lines(self):
        result = enumerate_cli_deps_from_command_lines(["No command here"])
        assert result == set()


class TestEnumerateCliDepsFromRunVerbs:
    def test_finds_run_verb(self):
        ac = "Run pytest: tests/test_foo.py"
        result = enumerate_cli_deps_from_run_verbs([ac])
        assert "pytest" in result

    def test_pytest_prefix_pattern(self):
        ac = "pytest: tests/test_something.py"
        result = enumerate_cli_deps_from_run_verbs([ac])
        assert "pytest" in result

    def test_run_with_space(self):
        ac = "Run myapp with --flag"
        result = enumerate_cli_deps_from_run_verbs([ac])
        assert "myapp" in result

    def test_empty_list(self):
        result = enumerate_cli_deps_from_run_verbs([])
        assert result == set()


class TestEnumerateDeps:
    def test_returns_dep_inventory(self):
        acs = ["command: xxd", "Run pytest: tests/"]
        result = enumerate_deps(acs)
        assert isinstance(result, DepInventory)

    def test_empty_acs_returns_empty_inventory(self):
        result = enumerate_deps([])
        assert len(result) == 0

    def test_collects_cli_entries(self):
        acs = ["command: xxd --version"]
        result = enumerate_deps(acs)
        names = [e.name for e in result.entries if e.kind == "cli"]
        assert "xxd" in names

    def test_dep_inventory_length(self):
        acs = ["command: git", "command: pytest"]
        result = enumerate_deps(acs)
        assert len(result) >= 2
