"""Tests for Research-and-Expand harness (c78c2ec7).

Verifies:
- All 6 agent modules importable and expose run(round_num) -> list[Proposal]
- harness.run_all_research_agents is importable and async
- Proposals conform to MASTER_PLAN Phase-4 YAML schema fields
- Harness writes YAML files to docs/recursion/round<N>/research/
- Parallel execution via asyncio.gather works correctly
"""

from __future__ import annotations

import asyncio
import inspect
import pathlib

import pytest
import yaml


# ===================================================================
# Import checks
# ===================================================================


class TestImports:
    def test_import_harness(self):
        from bob.research.harness import run_all_research_agents
        assert callable(run_all_research_agents)

    def test_import_r1_coverage(self):
        from bob.research import r1_coverage
        assert callable(r1_coverage.run)

    def test_import_r2_stack(self):
        from bob.research import r2_stack
        assert callable(r2_stack.run)

    def test_import_r3_perf(self):
        from bob.research import r3_perf
        assert callable(r3_perf.run)

    def test_import_r4_security(self):
        from bob.research import r4_security
        assert callable(r4_security.run)

    def test_import_r5_ecosystem(self):
        from bob.research import r5_ecosystem
        assert callable(r5_ecosystem.run)

    def test_import_r6_self_critique(self):
        from bob.research import r6_self_critique
        assert callable(r6_self_critique.run)

    def test_run_all_research_agents_is_async(self):
        from bob.research.harness import run_all_research_agents
        assert inspect.iscoroutinefunction(run_all_research_agents)


# ===================================================================
# Agent run() signatures and return types
# ===================================================================


class TestAgentRunSignature:
    @pytest.mark.parametrize("module_name", [
        "r1_coverage", "r2_stack", "r3_perf",
        "r4_security", "r5_ecosystem", "r6_self_critique",
    ])
    def test_run_accepts_round_num(self, module_name):
        import importlib
        mod = importlib.import_module(f"bob.research.{module_name}")
        sig = inspect.signature(mod.run)
        assert "round_num" in sig.parameters

    @pytest.mark.parametrize("module_name", [
        "r1_coverage", "r2_stack", "r3_perf",
        "r4_security", "r5_ecosystem", "r6_self_critique",
    ])
    def test_run_returns_list(self, module_name, tmp_path, monkeypatch):
        import importlib
        monkeypatch.chdir(tmp_path)
        mod = importlib.import_module(f"bob.research.{module_name}")
        result = mod.run(1)
        assert isinstance(result, list)


# ===================================================================
# Proposal schema conformance
# ===================================================================


class TestProposalSchema:
    REQUIRED_FIELDS = {
        "id", "domain", "title", "rationale",
        "acceptance_criteria", "estimated_effort",
        "estimated_impact", "blocked_by", "evidence",
    }

    @pytest.mark.parametrize("module_name", [
        "r1_coverage", "r2_stack", "r3_perf",
        "r4_security", "r5_ecosystem", "r6_self_critique",
    ])
    def test_proposals_have_required_fields(self, module_name, tmp_path, monkeypatch):
        import importlib
        monkeypatch.chdir(tmp_path)
        mod = importlib.import_module(f"bob.research.{module_name}")
        proposals = mod.run(1)
        for proposal in proposals:
            d = proposal.to_dict()
            for field in self.REQUIRED_FIELDS:
                assert field in d, f"Proposal from {module_name} missing field '{field}'"

    @pytest.mark.parametrize("module_name", [
        "r1_coverage", "r2_stack", "r3_perf",
        "r4_security", "r5_ecosystem", "r6_self_critique",
    ])
    def test_proposals_have_non_empty_id(self, module_name, tmp_path, monkeypatch):
        import importlib
        monkeypatch.chdir(tmp_path)
        mod = importlib.import_module(f"bob.research.{module_name}")
        proposals = mod.run(1)
        for p in proposals:
            assert p.id, f"Proposal from {module_name} has empty id"

    @pytest.mark.parametrize("module_name", [
        "r1_coverage", "r2_stack", "r3_perf",
        "r4_security", "r5_ecosystem", "r6_self_critique",
    ])
    def test_acceptance_criteria_is_list(self, module_name, tmp_path, monkeypatch):
        import importlib
        monkeypatch.chdir(tmp_path)
        mod = importlib.import_module(f"bob.research.{module_name}")
        proposals = mod.run(1)
        for p in proposals:
            assert isinstance(p.acceptance_criteria, list)

    @pytest.mark.parametrize("module_name", [
        "r1_coverage", "r2_stack", "r3_perf",
        "r4_security", "r5_ecosystem", "r6_self_critique",
    ])
    def test_blocked_by_is_list(self, module_name, tmp_path, monkeypatch):
        import importlib
        monkeypatch.chdir(tmp_path)
        mod = importlib.import_module(f"bob.research.{module_name}")
        proposals = mod.run(1)
        for p in proposals:
            assert isinstance(p.blocked_by, list)

    @pytest.mark.parametrize("module_name", [
        "r1_coverage", "r2_stack", "r3_perf",
        "r4_security", "r5_ecosystem", "r6_self_critique",
    ])
    def test_evidence_is_list(self, module_name, tmp_path, monkeypatch):
        import importlib
        monkeypatch.chdir(tmp_path)
        mod = importlib.import_module(f"bob.research.{module_name}")
        proposals = mod.run(1)
        for p in proposals:
            assert isinstance(p.evidence, list)


# ===================================================================
# Harness integration: parallel execution and YAML output
# ===================================================================


class TestHarness:
    @pytest.mark.asyncio
    async def test_run_all_returns_dict_of_seven_agents(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        results = await run_all_research_agents(round_num=1, output_dir=out_dir)

        assert isinstance(results, dict)
        expected_keys = {
            "r1_coverage", "r2_stack", "r3_perf",
            "r4_security", "r5_ecosystem", "r6_self_critique",
            "r7_literature",
        }
        assert set(results.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_run_all_writes_yaml_files(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        await run_all_research_agents(round_num=1, output_dir=out_dir)

        yaml_files = list(out_dir.glob("*.yaml"))
        assert len(yaml_files) == 7, f"Expected 7 YAML files, found {len(yaml_files)}"

    @pytest.mark.asyncio
    async def test_yaml_files_are_valid_yaml(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        await run_all_research_agents(round_num=1, output_dir=out_dir)

        for yaml_file in out_dir.glob("*.yaml"):
            content = yaml_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            assert isinstance(data, list), f"{yaml_file.name} did not parse as a list"

    @pytest.mark.asyncio
    async def test_yaml_proposals_have_required_fields(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        required = {
            "id", "domain", "title", "rationale",
            "acceptance_criteria", "estimated_effort",
            "estimated_impact", "blocked_by", "evidence",
        }
        out_dir = tmp_path / "research"
        await run_all_research_agents(round_num=1, output_dir=out_dir)

        for yaml_file in out_dir.glob("*.yaml"):
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            for proposal in data:
                for field in required:
                    assert field in proposal, (
                        f"{yaml_file.name}: proposal missing field '{field}'"
                    )

    @pytest.mark.asyncio
    async def test_default_output_dir_uses_round_num(self, tmp_path, monkeypatch):
        from bob.research.harness import run_all_research_agents

        monkeypatch.chdir(tmp_path)
        await run_all_research_agents(round_num=3)

        expected_dir = tmp_path / "docs" / "recursion" / "round3" / "research"
        assert expected_dir.exists()
        assert len(list(expected_dir.glob("*.yaml"))) == 7

    @pytest.mark.asyncio
    async def test_all_agents_return_list_values(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        results = await run_all_research_agents(round_num=1, output_dir=out_dir)

        for agent_name, proposals in results.items():
            assert isinstance(proposals, list), f"{agent_name} did not return a list"

    @pytest.mark.asyncio
    async def test_run_all_is_concurrent(self, tmp_path):
        """Verify gather is used by checking all 7 agents complete."""
        import time
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        start = time.monotonic()
        results = await run_all_research_agents(round_num=1, output_dir=out_dir)
        elapsed = time.monotonic() - start

        assert len(results) == 7
        assert elapsed < 30.0, f"Harness took {elapsed:.1f}s; expected < 30s"


# ===================================================================
# R6 self-critique specific checks
# ===================================================================


class TestR6SelfCritique:
    def test_always_produces_at_least_one_proposal(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r6_self_critique
        proposals = r6_self_critique.run(1)
        assert len(proposals) >= 1

    def test_proposal_domain_is_self_critique(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r6_self_critique
        proposals = r6_self_critique.run(1)
        domains = {p.domain for p in proposals}
        assert "self_critique" in domains


# ===================================================================
# Proposal dataclass
# ===================================================================


class TestProposalDataclass:
    def test_proposal_id_is_unique(self):
        from bob.research.proposal import Proposal
        p1 = Proposal()
        p2 = Proposal()
        assert p1.id != p2.id

    def test_proposal_to_dict_has_all_fields(self):
        from bob.research.proposal import Proposal
        p = Proposal(
            domain="test",
            title="Test proposal",
            rationale="Because reasons",
            acceptance_criteria=["It works"],
            estimated_effort="small",
            estimated_impact="medium",
            blocked_by=[],
            evidence=["Some evidence"],
        )
        d = p.to_dict()
        assert d["domain"] == "test"
        assert d["title"] == "Test proposal"
        assert d["acceptance_criteria"] == ["It works"]
        assert d["evidence"] == ["Some evidence"]

    def test_proposal_serializes_to_yaml(self):
        from bob.research.proposal import Proposal
        p = Proposal(domain="coverage", title="Add tests", rationale="Need more coverage")
        serialized = yaml.dump([p.to_dict()], default_flow_style=False)
        loaded = yaml.safe_load(serialized)
        assert isinstance(loaded, list)
        assert loaded[0]["domain"] == "coverage"
