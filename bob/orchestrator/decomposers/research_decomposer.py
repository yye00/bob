"""
Research Decomposer — Reads papers, searches web, computes references.
======================================================================

Handles WorkUnits of kind="research". These represent queries for
domain-specific information needed by verification or task planning.

Source types:
- "paper"  — Extract text/values from a PDF
- "web"    — Search Perplexity for reference values
- "compute" — Run a computation to generate a reference value

Evaluation:
- Paper source: confidence = 1.0 if paper exists and is readable
- Web source: confidence = 1.0 (always can try searching)
- Compute: confidence based on whether script is provided

Decomposition:
- Paper too large → split into section-specific queries
- Web query too broad → split into specific sub-queries

Execution:
- Paper: extract text using pdftotext/pypdf
- Web: generate search prompt for Claude with Perplexity MCP
- Compute: run a Python script and capture output
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from bob.orchestrator.decomposer import Decomposer
from bob.orchestrator.work_unit import (
    WorkUnit,
    WorkUnitKind,
    ConfidenceScore,
)
from bob.orchestrator.claude_executor import execute_task_with_claude


REFERENCE_PRIORITIZATION_PROMPT = """\
You are helping prioritize reference materials for verifying a scientific computing task.

## Task to Verify
{query}

## Available References
{references}

## Instructions
Rank these references by relevance to generating VERIFICATION TESTS for the task above.

Consider:
- Which papers contain exact numerical values usable as test oracles?
- Which describe the algorithm being implemented?
- Which have benchmark results at the same scale?
- Which discuss convergence properties?

Output ONLY valid JSON:
{{
  "priority_order": ["label1", "label2", ...],
  "analysis": [
    {{"label": "...", "relevance": 0.95, "look_for": "Table 3: ground state energies for Heisenberg chain"}},
    ...
  ]
}}
"""


RESEARCH_SEARCH_PROMPT = """\
Search for reference values related to: {query}

Context: {task_context}

Find:
1. Exact numerical values (energies, eigenvalues, benchmarks)
2. Convergence properties (rates, monotonicity, fixed points)
3. Algorithmic requirements (what the method should/shouldn't do)

Report your findings as plain text. Include specific numbers with sources.
Be precise — these values will be used in automated verification tests.
"""


class ResearchDecomposer(Decomposer):
    """Executes research queries: paper extraction, web search, computation."""

    def __init__(
        self,
        workspace_dir: str,
        project_dir: Path,
        model: str = "claude-sonnet-4-5-20250929",
        timeout_seconds: int = 0,
    ):
        self.workspace_dir = workspace_dir
        self.project_dir = project_dir
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def evaluate(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> ConfidenceScore:
        """Evaluate research readiness.

        Most research units can be executed directly — they're leaf nodes.
        Only decompose if the source is too large (e.g., full paper
        without section hints).
        """
        content = unit.content
        source_type = content.get("source_type", "web")

        if source_type == "paper":
            paper_path = Path(self.workspace_dir) / content.get("paper_path", "")
            if not paper_path.exists():
                return ConfidenceScore(
                    implementation=1.0,
                    verification=0.3,
                    reason=f"Paper not found: {paper_path}",
                )
            # Check if sections are specified (focused extraction)
            if content.get("paper_sections"):
                return ConfidenceScore(
                    implementation=1.0,
                    verification=0.95,
                    reason="Paper with section filter — ready to extract",
                )
            else:
                # Full paper — might be too large, but try anyway
                return ConfidenceScore(
                    implementation=1.0,
                    verification=0.85,
                    reason="Full paper extraction (no section filter)",
                )

        elif source_type == "web":
            return ConfidenceScore(
                implementation=1.0,
                verification=0.92,
                reason="Web search ready",
            )

        elif source_type == "prioritization":
            # Reference prioritization is a lightweight task — always ready
            refs = content.get("references", [])
            if refs:
                return ConfidenceScore(
                    implementation=1.0,
                    verification=0.95,
                    reason=f"Reference prioritization ready ({len(refs)} refs)",
                )
            return ConfidenceScore(
                implementation=1.0,
                verification=0.3,
                reason="Prioritization requested but no references",
            )

        elif source_type == "compute":
            if content.get("script"):
                return ConfidenceScore(
                    implementation=1.0,
                    verification=0.95,
                    reason="Compute script provided",
                )
            return ConfidenceScore(
                implementation=1.0,
                verification=0.5,
                reason="Compute requested but no script",
            )

        return ConfidenceScore(
            implementation=1.0,
            verification=0.9,
            reason=f"Unknown source type: {source_type}",
        )

    async def decompose(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> list[WorkUnit]:
        """Decompose research into more specific queries.

        Rarely needed — most research units execute directly.
        Only splits if paper is too large without section hints.
        """
        content = unit.content
        source_type = content.get("source_type", "web")

        if source_type == "paper" and not content.get("paper_sections"):
            # Full paper without sections — split into common section queries
            paper_path = content.get("paper_path", "")
            label = content.get("query", paper_path)
            common_sections = [
                "Abstract",
                "Introduction",
                "Methods",
                "Results",
                "Algorithm",
            ]
            children = []
            for section in common_sections:
                children.append(WorkUnit(
                    kind=WorkUnitKind.RESEARCH,
                    content={
                        "query": f"Extract from {label}: {section}",
                        "source_type": "paper",
                        "paper_path": paper_path,
                        "paper_sections": [section],
                        "task_context": content.get("task_context", ""),
                    },
                ))
            return children

        # Web queries that are too broad — split by aspect
        if source_type == "web":
            task = content.get("task_context", "")
            return [
                WorkUnit(
                    kind=WorkUnitKind.RESEARCH,
                    content={
                        "query": f"Exact numerical values for: {task}",
                        "source_type": "web",
                        "task_context": task,
                    },
                ),
                WorkUnit(
                    kind=WorkUnitKind.RESEARCH,
                    content={
                        "query": f"Convergence properties of: {task}",
                        "source_type": "web",
                        "task_context": task,
                    },
                ),
            ]

        return []

    async def execute(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> dict[str, Any]:
        """Execute a research query.

        Paper → extract text using pdftotext.
        Web → use Claude with Perplexity MCP to search.
        Compute → run a Python script.
        """
        content = unit.content
        source_type = content.get("source_type", "web")

        if source_type == "paper":
            return self._execute_paper(content)
        elif source_type == "web":
            return await self._execute_web(content)
        elif source_type == "prioritization":
            return await self._execute_prioritization(content)
        elif source_type == "compute":
            return self._execute_compute(content)
        else:
            return {"finding": "", "source": f"unknown source type: {source_type}"}

    def estimate_context_tokens(self, unit: WorkUnit) -> int:
        """Estimate tokens for research context."""
        content = unit.content
        source_type = content.get("source_type", "web")

        if source_type == "paper":
            # Paper with sections: ~4K chars extracted, without: ~16K
            if content.get("paper_sections"):
                return 2000
            return 5000
        elif source_type == "web":
            # Search prompt + results
            return 3000
        elif source_type == "compute":
            return 1000
        return 2000

    # ------------------------------------------------------------------
    # Private execution methods
    # ------------------------------------------------------------------

    def _execute_paper(self, content: dict) -> dict[str, Any]:
        """Extract text from a PDF paper."""
        paper_path = Path(self.workspace_dir) / content.get("paper_path", "")
        sections = content.get("paper_sections")
        label = content.get("query", str(paper_path))

        if not paper_path.exists():
            return {"finding": "", "source": f"Paper not found: {paper_path}"}

        from bob.orchestrator.verification_researcher import _extract_paper_text
        text = _extract_paper_text(paper_path, sections)

        return {
            "finding": text,
            "source": f"Paper: {label}",
            "paper_path": str(paper_path),
        }

    async def _execute_web(self, content: dict) -> dict[str, Any]:
        """Search the web via Claude with Perplexity MCP."""
        query = content.get("query", "")
        task_context = content.get("task_context", "")

        prompt = RESEARCH_SEARCH_PROMPT.format(
            query=query,
            task_context=task_context,
        )

        result = await execute_task_with_claude(
            project_dir=self.project_dir,
            prompt=prompt,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
            non_interactive=True,
            stall_timeout=0,
        )

        if result.success:
            return {
                "finding": result.output[:4000],  # Truncate for context budget
                "source": f"Web search: {query[:100]}",
            }
        return {
            "finding": "",
            "source": f"Web search failed: {result.error or 'unknown'}",
        }

    async def _execute_prioritization(self, content: dict) -> dict[str, Any]:
        """Prioritize references for a specific task using Claude."""
        query = content.get("query", "")
        references = content.get("references", [])

        if not references:
            return {"finding": "", "source": "No references to prioritize", "priority_order": []}

        # Format references for the prompt
        ref_lines = []
        for i, ref in enumerate(references, 1):
            label = ref.get("label", ref.get("path", f"ref_{i}"))
            details = []
            if ref.get("path"):
                details.append(f"file: {ref['path']}")
            if ref.get("url"):
                details.append(f"url: {ref['url']}")
            if ref.get("sections"):
                details.append(f"sections: {', '.join(ref['sections'])}")
            if ref.get("focus"):
                details.append("PRIMARY")
            detail_str = f" ({', '.join(details)})" if details else ""
            ref_lines.append(f"{i}. {label}{detail_str}")

        prompt = REFERENCE_PRIORITIZATION_PROMPT.format(
            query=query,
            references="\n".join(ref_lines),
        )

        result = await execute_task_with_claude(
            project_dir=self.project_dir,
            prompt=prompt,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
            non_interactive=True,
            stall_timeout=0,
        )

        if not result.success:
            # Fallback: return references in original order
            labels = [r.get("label", f"ref_{i}") for i, r in enumerate(references, 1)]
            return {
                "finding": "Prioritization failed — using original order",
                "source": "prioritization (fallback)",
                "priority_order": labels,
            }

        # Parse the JSON response
        import re
        text = result.output.strip()
        text = re.sub(r'^```(?:json)?\s*\n', '', text)
        text = re.sub(r'\n```\s*$', '', text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end > start:
                try:
                    data = json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        priority_order = data.get("priority_order", [])
        analysis = data.get("analysis", [])
        analysis_text = "\n".join(
            f"- {a.get('label', '?')} (relevance={a.get('relevance', '?')}): {a.get('look_for', '')}"
            for a in analysis
        ) if analysis else "No detailed analysis"

        return {
            "finding": f"Reference priority analysis:\n{analysis_text}",
            "source": "prioritization",
            "priority_order": priority_order,
        }

    def _execute_compute(self, content: dict) -> dict[str, Any]:
        """Run a computation to generate a reference value."""
        script = content.get("script", "")
        if not script:
            return {"finding": "", "source": "No compute script provided"}

        try:
            result = subprocess.run(
                ["python", "-c", script],
                capture_output=True, text=True,
                timeout=120,
                cwd=self.workspace_dir,
            )
            if result.returncode == 0:
                return {
                    "finding": result.stdout.strip(),
                    "source": "Computed reference value",
                }
            return {
                "finding": "",
                "source": f"Compute failed: {result.stderr[:200]}",
            }
        except subprocess.TimeoutExpired:
            return {"finding": "", "source": "Compute timed out"}
        except Exception as e:
            return {"finding": "", "source": f"Compute error: {e}"}
