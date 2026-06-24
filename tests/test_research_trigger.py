"""Tests for feature 79340d15: Auto-trigger research harness per round.

Verifies:
- fire_research_for_round is importable from bob3.orchestrator.research_trigger
- It returns a well-formed summary dict
- It writes YAML files to docs/recursion/round<N>/research/
- It integrates with bob3.research.harness
- CLI integration point exists in bob3.cli
"""

from __future__ import annotations

import inspect
import pathlib

import pytest
import yaml


# ===================================================================
# Import checks
# ===================================================================


class TestImport:
    def test_module_importable(self):
        import bob3.orchestrator.research_trigger  # noqa: F401

    def test_fire_research_for_round_importable(self):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        assert callable(fire_research_for_round)

    def test_fire_research_for_round_is_sync(self):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        assert not inspect.iscoroutinefunction(fire_research_for_round), (
            "fire_research_for_round should be synchronous (wraps asyncio.run internally)"
        )


# ===================================================================
# Return value shape
# ===================================================================


class TestReturnValue:
    REQUIRED_KEYS = {
        "round_num",
        "output_dir",
        "total_proposals",
        "agent_counts",
        "high_impact_proposals",
    }

    def test_returns_dict(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        assert isinstance(result, dict)

    def test_has_required_keys(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        for key in self.REQUIRED_KEYS:
            assert key in result, f"Result missing key '{key}'"

    def test_round_num_echoed(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=7, workspace=tmp_path)
        assert result["round_num"] == 7

    def test_output_dir_contains_round_num(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=3, workspace=tmp_path)
        assert "round3" in result["output_dir"]

    def test_total_proposals_is_non_negative_int(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        assert isinstance(result["total_proposals"], int)
        assert result["total_proposals"] >= 0

    def test_agent_counts_is_dict(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        assert isinstance(result["agent_counts"], dict)

    def test_agent_counts_has_core_agents(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        required_agents = {
            "r1_coverage", "r2_stack", "r3_perf",
            "r4_security", "r5_ecosystem", "r6_self_critique",
        }
        assert required_agents.issubset(set(result["agent_counts"].keys()))

    def test_total_proposals_matches_agent_counts_sum(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        expected_total = sum(result["agent_counts"].values())
        assert result["total_proposals"] == expected_total

    def test_high_impact_proposals_is_list(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        assert isinstance(result["high_impact_proposals"], list)


# ===================================================================
# File output
# ===================================================================


class TestFileOutput:
    def test_writes_yaml_files(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        fire_research_for_round(round_num=1, workspace=tmp_path)
        out_dir = tmp_path / "docs" / "recursion" / "round1" / "research"
        assert out_dir.exists()
        yaml_files = list(out_dir.glob("*.yaml"))
        assert len(yaml_files) >= 6

    def test_yaml_files_are_valid(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        fire_research_for_round(round_num=2, workspace=tmp_path)
        out_dir = tmp_path / "docs" / "recursion" / "round2" / "research"
        for yaml_file in out_dir.glob("*.yaml"):
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            assert isinstance(data, list), f"{yaml_file.name} did not parse as a list"

    def test_output_dir_path_matches_returned_output_dir(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=4, workspace=tmp_path)
        expected = tmp_path / "docs" / "recursion" / "round4" / "research"
        assert pathlib.Path(result["output_dir"]) == expected

    def test_default_workspace_uses_cwd(self, tmp_path, monkeypatch):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        monkeypatch.chdir(tmp_path)
        result = fire_research_for_round(round_num=1)
        expected = tmp_path / "docs" / "recursion" / "round1" / "research"
        assert pathlib.Path(result["output_dir"]) == expected
        assert expected.exists()


# ===================================================================
# Integration: bob3.research.harness
# ===================================================================


class TestHarnessIntegration:
    def test_uses_run_all_research_agents(self, tmp_path):
        """Confirm fire_research_for_round delegates to the harness."""
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        # If the harness ran, all core agent counts exist (>= 6 because r7+ may be present)
        assert len(result["agent_counts"]) >= 6

    def test_all_agent_counts_are_non_negative(self, tmp_path):
        from bob3.orchestrator.research_trigger import fire_research_for_round
        result = fire_research_for_round(round_num=1, workspace=tmp_path)
        for agent, count in result["agent_counts"].items():
            assert count >= 0, f"Agent {agent} returned negative count"


# ===================================================================
# Integration: bob3.cli
# ===================================================================


class TestCLIIntegration:
    def test_cli_module_importable(self):
        import bob3.cli  # noqa: F401

    def test_fire_research_for_round_importable_from_trigger(self):
        """Validate the integration point the CLI will use."""
        from bob3.orchestrator.research_trigger import fire_research_for_round
        assert fire_research_for_round is not None

    def test_plan_command_exists_in_cli(self):
        from bob3.cli import main
        command_names = [cmd.name for cmd in main.commands.values()]
        assert "plan" in command_names
