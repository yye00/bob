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

# Prefer SDK executor when available
try:
    from bob.orchestrator.claude_sdk_executor import execute_task_with_sdk as _sdk_execute
    _USE_SDK = True
except ImportError:
    _USE_SDK = False


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

IMPORTANT: Output ONLY the raw JSON object below. No markdown fences. No explanation. No commentary.
Do NOT write to files. Do NOT use any tools. Just output the JSON directly.
Every category MUST have at least 2 tests — never return empty arrays.

{{
  "numerical_tests": [
    {{"name": "descriptive_snake_case_name", "command": "cd {workspace_dir} && python -c \\"import numpy as np; ...; assert ...; print('PASS')\\"", "timeout": 60, "source": "description of reference value source"}}
  ],
  "algorithmic_tests": [
    {{"name": "descriptive_snake_case_name", "command": "cd {workspace_dir} && python -c \\"...; assert ...; print('PASS')\\"", "timeout": 120, "source": "what this tests"}}
  ],
  "convergence_tests": [
    {{"name": "descriptive_snake_case_name", "command": "cd {workspace_dir} && python -c \\"...; assert ...; print('PASS')\\"", "timeout": 180, "source": "what convergence property this verifies"}}
  ]
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
        timeout_seconds: int = 0,
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
        If we don't → spawn research units:
          1. A reference prioritization unit (ranks references by relevance to task)
          2. Paper reading units for each reference (processed in priority order)
          3. A web search unit for supplementary data
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

        if self.references:
            # Step 1: Prioritize references for this specific task
            # This is itself a research unit — Bob figures out which
            # papers matter most for verifying THIS task
            ref_summary = "\n".join(
                f"- {r.get('label', r.get('path', 'unknown'))}"
                + (f" (priority: {r['priority']})" if 'priority' in r else "")
                for r in self.references
            )
            children.append(WorkUnit(
                kind=WorkUnitKind.RESEARCH,
                content={
                    "query": (
                        f"Rank these references by relevance to verifying: {task_title}\n\n"
                        f"Task description: {task_desc[:300]}\n\n"
                        f"References:\n{ref_summary}\n\n"
                        f"Output a JSON list of reference labels in priority order, "
                        f"with a relevance score (0-1) and what to look for in each."
                    ),
                    "source_type": "prioritization",
                    "references": self.references,
                    "task_context": task_title,
                },
            ))

            # Step 2: Paper research units for each reference
            # These will be processed after prioritization results are available
            for ref in self.references:
                # Use explicit priority if provided, otherwise Bob will figure it out
                children.append(WorkUnit(
                    kind=WorkUnitKind.RESEARCH,
                    content={
                        "query": f"Extract reference values from: {ref.get('label', ref.get('path', ''))}",
                        "source_type": "paper",
                        "paper_path": ref.get("path", ""),
                        "paper_url": ref.get("url", ""),
                        "paper_sections": ref.get("sections"),
                        "paper_label": ref.get("label", ""),
                        "priority": ref.get("priority"),  # None if not provided
                        "task_context": task_title,
                    },
                ))
        else:
            # No references at all — web search only
            pass

        # Step 3: Web search for supplementary reference values
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

        # Collect research findings from children, organized by type
        prioritization = None
        paper_findings = []
        web_findings = []

        for child_id in unit.children:
            child = tree.get(child_id)
            if not child or child.kind != WorkUnitKind.RESEARCH or not child.result:
                continue
            source_type = child.content.get("source_type", "unknown")
            finding = child.result.get("finding", "")
            source = child.result.get("source", source_type)

            if source_type == "prioritization":
                prioritization = child.result
            elif source_type == "paper":
                label = child.content.get("paper_label", source)
                if finding:
                    paper_findings.append({
                        "label": label,
                        "finding": finding,
                        "priority": child.content.get("priority"),
                    })
            elif source_type == "web":
                if finding:
                    web_findings.append(f"[web]: {finding}")

        # Sort paper findings by priority if prioritization result is available
        if prioritization and isinstance(prioritization.get("priority_order"), list):
            priority_order = {label: i for i, label in enumerate(prioritization["priority_order"])}
            paper_findings.sort(
                key=lambda f: (
                    f.get("priority") if f.get("priority") is not None
                    else priority_order.get(f["label"], 999)
                )
            )
        elif paper_findings:
            # Sort by explicit priority field if present
            paper_findings.sort(key=lambda f: f.get("priority") or 999)

        # Also collect from content (if research was done before decomposition)
        if content.get("research_findings"):
            web_findings.append(content["research_findings"])

        # Read reference papers directly (fallback if children didn't extract)
        paper_texts = []
        if not paper_findings:
            for ref in self.references:
                path = ref.get("path")
                if path:
                    paper_path = Path(self.workspace_dir) / path
                    if paper_path.exists():
                        from bob.orchestrator.verification_researcher import _extract_paper_text
                        text = _extract_paper_text(paper_path, ref.get("sections"))
                        label = ref.get("label", path)
                        paper_texts.append(f"### {label}\n{text}")

        # Build research context — papers first (in priority order), then web
        research_parts = []
        if paper_findings:
            research_parts.append("### From Papers (priority order)")
            for pf in paper_findings:
                research_parts.append(f"#### {pf['label']}\n{pf['finding']}")
        if paper_texts:
            research_parts.append("### From Papers (direct extraction)")
            research_parts.extend(paper_texts)
        if web_findings:
            research_parts.append("### From Web Search")
            research_parts.extend(web_findings)
        if prioritization:
            # Include prioritization rationale
            rationale = prioritization.get("finding", "")
            if rationale:
                research_parts.insert(0, f"### Reference Priority Analysis\n{rationale}")

        research_context = "\n\n".join(research_parts)

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

        # Include verify_script as additional context for test generation
        verify_script = content.get("verify_script", "")
        verify_script_section = ""
        if verify_script and verify_script.strip():
            verify_script_section = (
                f"\n## Existing Verify Script (use as inspiration)\n"
                f"```bash\n{verify_script}\n```\n"
            )

        # Call Claude to generate tests — with retry on empty results
        task_title = content.get("task_title", "")
        max_attempts = 3
        empty = {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}

        for attempt in range(1, max_attempts + 1):
            prompt = VERIFICATION_GEN_PROMPT.format(
                task_title=task_title,
                task_description=content.get("task_description", ""),
                acceptance_criteria=criteria_str,
                constraints=constraints_str,
                expected_outputs=outputs_str,
                research_findings=research_context,
                workspace_dir=self.workspace_dir,
            )
            # Append verify script context
            if verify_script_section:
                prompt += verify_script_section

            if _USE_SDK:
                result = await _sdk_execute(
                    project_dir=self.project_dir,
                    prompt=prompt,
                    model=self.model,
                    timeout_seconds=self.timeout_seconds,
                )
            else:
                result = await execute_task_with_claude(
                    project_dir=self.project_dir,
                    prompt=prompt,
                    model=self.model,
                    timeout_seconds=self.timeout_seconds,
                    non_interactive=True,
                    stall_timeout=0,
                )

            if not result.success:
                print(f"    ⚠ Verification generation failed for '{task_title}' "
                      f"(attempt {attempt}/{max_attempts}): Claude returned error")
                if attempt < max_attempts:
                    continue
                return empty

            # Parse tests
            tests = _parse_tests(result.output)
            total = sum(len(tests[cat]) for cat in tests)

            if total > 0:
                print(f"    ✓ Generated {total} tests for '{task_title}' "
                      f"(attempt {attempt})")
                return tests

            # Zero tests — log raw output for debugging
            output_preview = (result.output or "")[:500]
            print(f"    ⚠ Zero tests parsed for '{task_title}' "
                  f"(attempt {attempt}/{max_attempts})")
            print(f"      Raw output preview: {output_preview!r}")

            if attempt < max_attempts:
                print(f"      Retrying...")

        print(f"    ✗ All {max_attempts} attempts failed for '{task_title}'")
        return empty

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
    """Parse Claude's JSON output into test categories.

    Lenient parser: handles markdown fences, extra commentary,
    and tests with missing 'name' field (auto-generates name).
    """
    text = output.strip()

    # Strip markdown fences (multiple patterns)
    text = re.sub(r'^```(?:json)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    # Also handle fences in the middle of output
    text = re.sub(r'```(?:json)?\s*\n', '', text)
    text = re.sub(r'\n```', '', text)

    data = None

    # Try 1: Direct parse
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try 2: Find outermost JSON object
    if data is None:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    # Try 3: Find JSON between specific markers
    if data is None:
        # Claude sometimes wraps JSON in explanation
        for pattern in [
            r'\{[^{}]*"numerical_tests"[^{}]*\[.*?\].*?\}',
        ]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

    if data is None:
        return {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}

    result = {"numerical_tests": [], "algorithmic_tests": [], "convergence_tests": []}
    for cat_idx, cat in enumerate(result):
        for test_idx, test in enumerate(data.get(cat, [])):
            if not isinstance(test, dict):
                continue

            # Accept test if it has at least a 'command'
            command = test.get("command", test.get("cmd", test.get("script", "")))
            if not command:
                continue

            name = test.get("name", test.get("title", f"{cat}_{test_idx}"))

            result[cat].append({
                "name": name,
                "command": command,
                "timeout": test.get("timeout", 120),
                "source": test.get("source", "auto-generated"),
            })
    return result
