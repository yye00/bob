"""
Verification Decomposer — Generates verification tests from papers + search.
=============================================================================

Handles WorkUnits of kind="verification". These represent the need
to generate verification tests for a coding task.

Evaluation:
- Are tests already generated? How many per category?
- Do numerical tests have reference values?
- Do algorithmic tests block forbidden dependencies?

Decomposition:
- If no reference values → spawn research work units (paper, web)
- If reference values exist but no tests → generate tests directly

Execution:
- Use research findings + task context to generate tests via Claude
- Store tests in unit.result for parent task to collect
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bob.orchestrator.decomposer import Decomposer
from bob.orchestrator.work_unit import (
    WorkUnit,
    WorkUnitKind,
    ConfidenceScore,
)
from bob.orchestrator.claude_executor import execute_task_with_claude


# Prompt for generating verification tests from research findings
VERIFICATION_GEN_PROMPT = """\
You are a verification test engineer for scientific computing software.

Your job: Generate tests that will CATCH fake or incorrect implementations.
These tests are stored in a database — the coding agent CANNOT modify them.

## Task Under Test
**Title:** {task_title}
**Description:** {task_description}

**Acceptance Criteria:**
{acceptance_criteria}

**Constraints:**
{constraints}

**Expected Outputs:**
{expected_outputs}

## Research Findings
{research_findings}

## Workspace
Working directory: {workspace_dir}

## Generate THREE categories:

### 1. numerical_tests — Known-answer tests
- Use reference values from research findings
- Tight tolerances (1e-4 for energies, 1e-6 for norms)
- At least 2 different parameter sets per test
- Include inline computation of reference values where possible

### 2. algorithmic_tests — Method verification
- Block forbidden dependencies (monkey-patch to raise, code must still work)
- Different inputs must give different outputs
- At least 1 dependency-blocking test

### 3. convergence_tests — Process behavior
- Energy/metric improves with more iterations
- Better parameters give better results
- Algorithm reaches stable fixed point

Output ONLY valid JSON:
{{
  "numerical_tests": [{{"name": "...", "command": "cd {workspace_dir} && python -c \\"...\\"", "timeout": 60, "source": "..."}}],
  "algorithmic_tests": [{{"name": "...", "command": "...", "timeout": 120, "source": "..."}}],
  "convergence_tests": [{{"name": "...", "command": "...", "timeout": 180, "source": "..."}}]
}}
"""


class VerificationDecomposer(Decomposer):
    """Generates verification tests by reading papers and research findings.

    When research is incomplete → decomposes into research work units.
    When research is available → generates tests via Claude.
    """

    def __init__(
        self,
        workspace_dir: str,
        project_dir: Path,
        references: list[dict] | None = None,
        model: str = "claude-sonnet-4-5-20250929",
        timeout_seconds: int = 300,
    ):
        self.workspace_dir = workspace_dir
        self.project_dir = project_dir
        self.references = references or []
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def evaluate(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> ConfidenceScore:
        """Evaluate verification readiness.

        High confidence = tests are already generated.
        Low confidence = need research or test generation.
        """
        content = unit.content
        has_research = bool(content.get("research_findings"))
        has_references = bool(self.references)

        # Check if tests already exist (from a previous run or manual)
        has_numerical = bool(content.get("numerical_tests"))
        has_algorithmic = bool(content.get("algorithmic_tests"))
        has_convergence = bool(content.get("convergence_tests"))

        if has_numerical and has_algorithmic and has_convergence:
            # All test categories populated
            return ConfidenceScore(
                implementation=1.0,
                verification=0.95,
                reason="All verification test categories populated",
            )

        if has_research or has_references:
            # Have material to generate tests — medium confidence
            # (will be executed to generate tests)
            return ConfidenceScore(
                implementation=1.0,
                verification=0.6,
                reason="Research available but tests not yet generated",
            )

        # No research, no references — need to find material
        return ConfidenceScore(
            implementation=1.0,
            verification=0.1,
            reason="No research findings or references — need research first",
        )

    async def decompose(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> list[WorkUnit]:
        """Decompose into research work units if needed.

        If we have research/references → no decomposition needed (execute directly).
        If we don't → spawn research units for papers and web search.
        """
        content = unit.content
        has_research = bool(content.get("research_findings"))
        has_references = bool(self.references)

        if has_research or has_references:
            # We have enough to generate tests — execute directly
            # Return empty to signal "no decomposition, just execute"
            return []

        # No material — spawn research work units
        children = []
        task_title = content.get("task_title", "")
        task_desc = content.get("task_description", "")

        # Paper research (for each reference)
        for ref in self.references:
            children.append(WorkUnit(
                kind=WorkUnitKind.RESEARCH,
                content={
                    "query": f"Extract reference values from: {ref.get('label', ref.get('path', ''))}",
                    "source_type": "paper",
                    "paper_path": ref.get("path", ""),
                    "paper_sections": ref.get("sections"),
                    "task_context": task_title,
                },
            ))

        # Web search research
        children.append(WorkUnit(
            kind=WorkUnitKind.RESEARCH,
            content={
                "query": f"Reference values and properties for: {task_title}",
                "source_type": "web",
                "task_context": task_desc[:500],
            },
        ))

        return children

    async def execute(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> dict[str, Any]:
        """Generate verification tests using research findings + references.

        Collects research from child units, reads papers, and calls
        Claude to generate numerical/algorithmic/convergence tests.
        """
        content = unit.content

        # Collect research findings from children
        findings = []
        for child_id in unit.children:
            child = tree.get(child_id)
            if child and child.kind == WorkUnitKind.RESEARCH and child.result:
                finding = child.result.get("finding", "")
                source = child.result.get("source", "unknown")
                if finding:
                    findings.append(f"[{source}]: {finding}")

        # Also collect from content (if research was done before decomposition)
        if content.get("research_findings"):
            findings.append(content["research_findings"])

        # Read reference papers directly
        paper_texts = []
        for ref in self.references:
            path = ref.get("path")
            if path:
                paper_path = Path(self.workspace_dir) / path
                if paper_path.exists():
                    from bob.orchestrator.verification_researcher import _extract_paper_text
                    text = _extract_paper_text(paper_path, ref.get("sections"))
                    label = ref.get("label", path)
                    paper_texts.append(f"### {label}\n{text}")

        # Build research context
        research_context = "\n\n".join(findings)
        if paper_texts:
            research_context += "\n\n### From Papers\n" + "\n\n".join(paper_texts)

        if not research_context.strip():
            research_context = "(no research findings available — use domain knowledge)"

        # Format constraints
        constraints = content.get("constraints", [])
        constraints_str = "\n".join(f"- {c}" for c in constraints) if constraints else "(none)"

        # Format expected outputs
        outputs = content.get("expected_outputs", [])
        outputs_str = "\n".join(
            f"- {o.get('path', o) if isinstance(o, dict) else o}"
            for o in outputs
        ) if outputs else "(none)"

        # Format acceptance criteria
        criteria = content.get("acceptance_criteria", [])
        criteria_str = "\n".join(f"- {c}" for c in criteria) if criteria else "(none)"

        # Call Claude to generate tests
        prompt = VERIFICATION_GEN_PROMPT.format(
            task_title=content.get("task_title", ""),
            task_description=content.get("task_description", ""),
            acceptance_criteria=criteria_str,
            constraints=constraints_str,
            expected_outputs=outputs_str,
            research_findings=research_context,
            workspace_dir=self.workspace_dir,
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
            return {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}

        # Parse tests
        tests = _parse_tests(result.output)
        return tests

    def estimate_context_tokens(self, unit: WorkUnit) -> int:
        """Estimate tokens for verification generation context."""
        content = unit.content
        chars = 0
        chars += len(content.get("task_description", ""))
        chars += sum(len(c) for c in content.get("acceptance_criteria", []))
        chars += sum(len(c) for c in content.get("constraints", []))

        # Papers (biggest context consumer)
        for ref in self.references:
            path = ref.get("path")
            if path:
                paper_path = Path(self.workspace_dir) / path
                if paper_path.exists():
                    # Estimate: section-filtered extraction is ~8K chars
                    chars += 8000 if ref.get("sections") else 16000

        # Research findings from children
        chars += len(content.get("research_findings", ""))

        # Prompt overhead
        chars += 4000
        return chars // 4


def _parse_tests(output: str) -> dict:
    """Parse Claude's JSON output into test categories."""
    text = output.strip()
    text = re.sub(r'^```(?:json)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}
        else:
            return {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}

    result = {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}
    for cat in result:
        for test in data.get(cat, []):
            if isinstance(test, dict) and "name" in test and "command" in test:
                result[cat].append({
                    "name": test["name"],
                    "command": test["command"],
                    "timeout": test.get("timeout", 120),
                    "source": test.get("source", "auto-generated"),
                })
    return result
