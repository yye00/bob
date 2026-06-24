"""Tests for R7: arXiv literature scan research agent.

Verifies:
- Module is importable and run() is defined
- run() accepts round_num and returns list[Proposal]
- Proposals conform to MASTER_PLAN Phase-4 YAML schema fields
- Agent targets the required arXiv categories
- Filters for new methods, benchmarks, and open implementations
- Emits Proposals for both framework features and application specs
- Integrates with bob.research.harness
"""

from __future__ import annotations

import inspect
import pathlib

import pytest
import yaml


# ===================================================================
# Basic import and interface checks
# ===================================================================


class TestImports:
    def test_module_importable(self):
        from bob.research import r7_literature
        assert r7_literature is not None

    def test_run_callable(self):
        from bob.research import r7_literature
        assert callable(r7_literature.run)

    def test_run_accepts_round_num(self):
        from bob.research import r7_literature
        sig = inspect.signature(r7_literature.run)
        assert "round_num" in sig.parameters

    def test_run_returns_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        result = r7_literature.run(1)
        assert isinstance(result, list)

    def test_run_returns_nonempty_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        result = r7_literature.run(1)
        assert len(result) >= 1, "r7_literature.run() must return at least one Proposal"


# ===================================================================
# Proposal schema conformance
# ===================================================================


class TestProposalSchema:
    REQUIRED_FIELDS = {
        "id", "domain", "title", "rationale",
        "acceptance_criteria", "estimated_effort",
        "estimated_impact", "blocked_by", "evidence",
    }

    def test_proposals_have_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        for proposal in proposals:
            d = proposal.to_dict()
            for field in self.REQUIRED_FIELDS:
                assert field in d, f"r7_literature proposal missing field '{field}'"

    def test_proposals_have_non_empty_id(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        for p in proposals:
            assert p.id, "Proposal from r7_literature has empty id"

    def test_proposals_acceptance_criteria_is_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        for p in proposals:
            assert isinstance(p.acceptance_criteria, list)

    def test_proposals_blocked_by_is_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        for p in proposals:
            assert isinstance(p.blocked_by, list)

    def test_proposals_evidence_is_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        for p in proposals:
            assert isinstance(p.evidence, list)

    def test_proposals_have_non_empty_title(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        for p in proposals:
            assert p.title, "Proposal from r7_literature has empty title"

    def test_proposals_have_non_empty_rationale(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        for p in proposals:
            assert p.rationale, "Proposal from r7_literature has empty rationale"

    def test_proposals_serializable_to_yaml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        serialized = yaml.dump([p.to_dict() for p in proposals], default_flow_style=False)
        loaded = yaml.safe_load(serialized)
        assert isinstance(loaded, list)
        assert len(loaded) == len(proposals)


# ===================================================================
# Domain and category requirements
# ===================================================================


class TestDomainAndCategories:
    REQUIRED_ARXIV_CATEGORIES = [
        "cs.MS",
        "physics.comp-ph",
        "astro-ph.IM",
        "nucl-th",
        "physics.plasm-ph",
    ]

    def test_domain_is_literature(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        domains = {p.domain for p in proposals}
        assert "literature" in domains, (
            f"Expected at least one proposal with domain='literature', got {domains}"
        )

    def test_categories_referenced_in_evidence_or_rationale(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        # At least one proposal should reference the arXiv categories being scanned
        all_text = " ".join(
            " ".join(p.evidence) + " " + p.rationale
            for p in proposals
        )
        found_any = any(cat in all_text for cat in self.REQUIRED_ARXIV_CATEGORIES)
        assert found_any, (
            "Expected at least one proposal to reference arXiv categories "
            f"{self.REQUIRED_ARXIV_CATEGORIES}"
        )

    def test_categories_constant_exists(self):
        from bob.research import r7_literature
        assert hasattr(r7_literature, "ARXIV_CATEGORIES"), (
            "r7_literature must define ARXIV_CATEGORIES constant"
        )

    def test_categories_constant_contains_all_required(self):
        from bob.research import r7_literature
        cats = r7_literature.ARXIV_CATEGORIES
        for required in self.REQUIRED_ARXIV_CATEGORIES:
            assert required in cats, (
                f"ARXIV_CATEGORIES missing required category '{required}'"
            )

    def test_filter_keywords_defined(self):
        """Agent must define filter keywords for new methods, benchmarks, open implementations."""
        from bob.research import r7_literature
        assert hasattr(r7_literature, "FILTER_KEYWORDS"), (
            "r7_literature must define FILTER_KEYWORDS constant"
        )
        keywords = r7_literature.FILTER_KEYWORDS
        assert isinstance(keywords, (list, tuple, set))
        assert len(keywords) >= 3, "FILTER_KEYWORDS must have at least 3 keywords"


# ===================================================================
# Proposal type coverage: framework features and application specs
# ===================================================================


class TestProposalTypeCoverage:
    def test_proposals_include_framework_or_app_suggestion(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        proposals = r7_literature.run(1)
        # At least one proposal should suggest a feature or application
        all_text = " ".join(p.title + " " + p.rationale for p in proposals).lower()
        has_framework_or_app = (
            "feature" in all_text or
            "application" in all_text or
            "implement" in all_text or
            "benchmark" in all_text or
            "method" in all_text
        )
        assert has_framework_or_app, (
            "Expected proposals to mention framework features, applications, "
            "benchmarks, or methods"
        )

    def test_run_stable_across_multiple_calls(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        result1 = r7_literature.run(1)
        result2 = r7_literature.run(1)
        assert len(result1) == len(result2), (
            "run() should return consistent number of proposals across calls"
        )

    def test_different_round_num_works(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from bob.research import r7_literature
        result1 = r7_literature.run(1)
        result5 = r7_literature.run(5)
        assert isinstance(result1, list)
        assert isinstance(result5, list)


# ===================================================================
# Harness integration
# ===================================================================


class TestHarnessIntegration:
    def test_r7_importable_from_research_package(self):
        from bob.research import r7_literature
        assert callable(r7_literature.run)

    def test_harness_includes_r7(self):
        """The harness must include r7_literature in its agent list."""
        import inspect
        from bob.research import harness
        source = inspect.getsource(harness)
        assert "r7_literature" in source, (
            "harness.py must include r7_literature in the _AGENTS list"
        )

    def test_r7_listed_in_research_init(self):
        """The research __init__.py must export r7_literature."""
        from bob.research import r7_literature as r7
        assert r7 is not None

    @pytest.mark.asyncio
    async def test_harness_run_all_includes_r7(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        results = await run_all_research_agents(round_num=1, output_dir=out_dir)

        assert "r7_literature" in results, (
            f"run_all_research_agents must return 'r7_literature' key; got {set(results.keys())}"
        )

    @pytest.mark.asyncio
    async def test_harness_writes_r7_yaml(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        await run_all_research_agents(round_num=1, output_dir=out_dir)

        r7_yaml = out_dir / "r7_literature.yaml"
        assert r7_yaml.exists(), f"Expected {r7_yaml} to exist after harness run"

    @pytest.mark.asyncio
    async def test_harness_r7_yaml_is_valid(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        await run_all_research_agents(round_num=1, output_dir=out_dir)

        r7_yaml = out_dir / "r7_literature.yaml"
        content = r7_yaml.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_harness_total_agent_count(self, tmp_path):
        from bob.research.harness import run_all_research_agents

        out_dir = tmp_path / "research"
        results = await run_all_research_agents(round_num=1, output_dir=out_dir)
        assert len(results) >= 7, (
            f"Harness should include at least 7 agents (R1-R7); got {len(results)}"
        )


# ===================================================================
# Fetch and filter logic (unit tests with no network calls)
# ===================================================================


class TestFetchAndFilterLogic:
    def test_filter_paper_by_keyword(self):
        """Papers with matching keywords should pass the filter."""
        from bob.research.r7_literature import _paper_matches_filter

        abstract_new_method = (
            "We propose a new numerical method for solving PDEs "
            "with improved convergence properties."
        )
        assert _paper_matches_filter(abstract_new_method), (
            "Paper proposing a new method should match filter"
        )

    def test_filter_paper_benchmark(self):
        from bob.research.r7_literature import _paper_matches_filter

        abstract_benchmark = (
            "We present a benchmark suite for evaluating plasma simulation codes."
        )
        assert _paper_matches_filter(abstract_benchmark), (
            "Paper proposing a benchmark should match filter"
        )

    def test_filter_paper_open_implementation(self):
        from bob.research.r7_literature import _paper_matches_filter

        abstract_open_impl = (
            "We release an open-source implementation of our algorithm "
            "available on GitHub."
        )
        assert _paper_matches_filter(abstract_open_impl), (
            "Paper with open implementation should match filter"
        )

    def test_filter_rejects_review_paper(self):
        from bob.research.r7_literature import _paper_matches_filter

        abstract_review = (
            "In this review, we survey the literature on computational methods "
            "in nuclear theory from 2010 to 2024."
        )
        assert not _paper_matches_filter(abstract_review), (
            "Pure review/survey paper (no new method/benchmark/implementation) "
            "should not match filter"
        )

    def test_paper_to_proposal_returns_proposal(self):
        """_paper_to_proposal converts a paper dict to a Proposal."""
        from bob.research.r7_literature import _paper_to_proposal

        paper = {
            "id": "2401.12345",
            "title": "A New Solver for Plasma Equations",
            "abstract": (
                "We propose a novel method for plasma equation solving "
                "with open-source implementation."
            ),
            "categories": ["physics.plasm-ph"],
            "authors": ["Smith, J.", "Doe, A."],
        }
        proposal = _paper_to_proposal(paper)
        from bob.research.proposal import Proposal
        assert isinstance(proposal, Proposal)
        assert proposal.title
        assert proposal.rationale
        assert proposal.domain == "literature"
        assert len(proposal.evidence) >= 1

    def test_paper_to_proposal_evidence_includes_arxiv_id(self):
        from bob.research.r7_literature import _paper_to_proposal

        paper = {
            "id": "2401.99999",
            "title": "Open Benchmark for Nuclear Theory",
            "abstract": "We provide a benchmark for nuclear theory codes.",
            "categories": ["nucl-th"],
            "authors": ["Jones, R."],
        }
        proposal = _paper_to_proposal(paper)
        assert any("2401.99999" in ev for ev in proposal.evidence), (
            "Evidence must contain the arXiv paper ID"
        )
