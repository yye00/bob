"""
Task Decomposer — Evaluates, decomposes, and plans coding tasks.
================================================================

Handles WorkUnits of kind="task". These represent coding tasks that
will eventually be sent to Claude Code for implementation.

Evaluation:
- implementation confidence from task clarity, scope, acceptance criteria
- verification confidence from test coverage (are tests generated?)
- context_fit from token estimation

Decomposition:
- If implementation is weak: break into sub-tasks via Claude Opus
- If verification is weak: spawn verification WorkUnit children
- If context is too large: split description into smaller tasks

Execution:
- Store the finalized task in the plan output (not Claude Code — that's
  the orchestrator engine's job, not the planner's)
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from bob.orchestrator.decomposer import Decomposer
from bob.orchestrator.work_unit import (
    WorkUnit,
    WorkUnitKind,
    WorkUnitStatus,
    ConfidenceScore,
)
from bob.orchestrator.claude_executor import execute_task_with_claude

# Prefer SDK executor when available
try:
    from bob.orchestrator.claude_sdk_executor import execute_task_with_sdk as _sdk_execute
    _USE_SDK = True
except ImportError:
    _USE_SDK = False


# Prompt for task decomposition (breaking big tasks into sub-tasks)
TASK_DECOMPOSE_PROMPT = """\
You are a senior software architect. Break this task into 2-4 smaller,
more atomic sub-tasks that can each be completed in a single agent session.

## Task to Decompose
**Title:** {title}
**Description:**
{description}

**Acceptance Criteria:**
{acceptance_criteria}

**Why it needs decomposition:** {reason}

## Workspace
{workspace_dir}

## Output Format
Output ONLY valid JSON:
```
{{
  "sub_tasks": [
    {{
      "id": "{task_id}a",
      "title": "Sub-task title",
      "description": "Detailed description",
      "depends_on": [],
      "priority": "critical",
      "acceptance_criteria": ["Criterion 1", "Criterion 2"],
      "expected_outputs": [
        {{"path": "src/module.py", "min_lines": 50, "must_contain": ["class X"]}}
      ],
      "verify_script": "cd {workspace_dir} && python -c \\"...\\""
    }}
  ]
}}
```
"""


class TaskDecomposer(Decomposer):
    """Decomposes coding tasks based on confidence scores.

    When implementation confidence is low: breaks task into sub-tasks.
    When verification confidence is low: spawns verification work units.
    """

    def __init__(
        self,
        workspace_dir: str,
        project_dir: Path,
        model: str = "claude-opus-4-5-20251101",
        timeout_seconds: int = 300,
    ):
        self.workspace_dir = workspace_dir
        self.project_dir = project_dir
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def evaluate(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> ConfidenceScore:
        """Evaluate a task's confidence.

        Implementation confidence based on:
        - Description length and clarity
        - Acceptance criteria specificity
        - Expected outputs defined
        - Scope (estimated size)

        Verification confidence based on:
        - verify_script exists and isn't trivial
        - numerical/algorithmic/convergence tests exist
        - expected_outputs have must_contain patterns
        """
        content = unit.content
        impl_score = 0.5  # Start at neutral
        ver_score = 0.3   # Start low — assume verification is weak

        # --- Implementation confidence ---
        desc = content.get("description", "")
        criteria = content.get("acceptance_criteria", [])
        steps = content.get("steps", [])
        outputs = content.get("expected_outputs", [])

        # Description quality
        if len(desc) > 200:
            impl_score += 0.15
        if len(desc) > 500:
            impl_score += 0.1

        # Acceptance criteria
        if criteria:
            impl_score += min(0.15, len(criteria) * 0.05)

        # Steps defined
        if steps:
            impl_score += min(0.1, len(steps) * 0.03)

        # Expected outputs
        if outputs:
            impl_score += 0.1

        # Use planner's confidence if available (from Phase 1)
        if "implementation_confidence" in content:
            # Blend: 60% planner's assessment, 40% structural
            planner_conf = content["implementation_confidence"]
            impl_score = 0.6 * planner_conf + 0.4 * impl_score

        impl_score = min(1.0, impl_score)

        # --- Verification confidence ---
        verify_script = content.get("verify_script", "")
        numerical = content.get("numerical_tests", [])
        algorithmic = content.get("algorithmic_tests", [])
        convergence = content.get("convergence_tests", [])

        # verify_script quality
        if verify_script and verify_script.strip():
            if self._is_trivial_check(verify_script):
                ver_score += 0.05  # Barely better than nothing
            else:
                ver_score += 0.25

        # Semantic tests
        if numerical:
            ver_score += min(0.2, len(numerical) * 0.1)
        if algorithmic:
            ver_score += min(0.15, len(algorithmic) * 0.1)
        if convergence:
            ver_score += min(0.15, len(convergence) * 0.1)

        # Expected outputs with must_contain
        for output in outputs:
            if isinstance(output, dict) and output.get("must_contain"):
                ver_score += 0.05

        # Use planner's confidence if available
        if "verification_confidence" in content:
            planner_conf = content["verification_confidence"]
            ver_score = 0.6 * planner_conf + 0.4 * ver_score

        ver_score = min(1.0, ver_score)

        reason = ""
        if impl_score < 0.9:
            reason += f"impl={impl_score:.2f} (task may need decomposition). "
        if ver_score < 0.9:
            reason += f"ver={ver_score:.2f} (needs stronger verification). "

        return ConfidenceScore(
            implementation=impl_score,
            verification=ver_score,
            context_fit=1.0,  # Engine overrides this
            reason=reason.strip(),
        )

    async def decompose(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> list[WorkUnit]:
        """Decompose a task based on its weakest dimension.

        If implementation is weakest → break into sub-tasks.
        If verification is weakest → spawn verification work unit.
        """
        weakest = unit.confidence.weakest_dimension

        if weakest == "context_fit":
            # Context too large — split task into smaller tasks
            return await self._decompose_for_context(unit)

        elif weakest == "verification":
            # Verification weak — spawn verification work unit
            return self._spawn_verification_unit(unit)

        else:
            # Implementation weak — break into sub-tasks
            return await self._decompose_into_subtasks(unit)

    async def execute(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> dict[str, Any]:
        """'Execute' a task means finalizing it in the plan output.

        This doesn't run Claude Code — that's the orchestrator's job.
        Here we just mark the task as ready for execution and collect
        any verification tests from child work units.
        """
        content = unit.content

        # Collect verification results from children
        for child_id in unit.children:
            child = tree.get(child_id)
            if child and child.kind == WorkUnitKind.VERIFICATION and child.result:
                # Merge verification tests into task
                for cat in ("numerical_tests", "algorithmic_tests", "convergence_tests"):
                    if cat in child.result:
                        existing = content.get(cat, [])
                        existing.extend(child.result[cat])
                        content[cat] = existing

        return {"status": "ready", "task": content}

    def estimate_context_tokens(self, unit: WorkUnit) -> int:
        """Estimate tokens for a task's full context.

        Includes: task description + acceptance criteria + steps +
        expected outputs + verify script + any research findings.
        """
        content = unit.content
        total_chars = 0

        total_chars += len(content.get("description", ""))
        total_chars += sum(len(c) for c in content.get("acceptance_criteria", []))
        total_chars += sum(len(s) for s in content.get("steps", []))
        total_chars += len(content.get("verify_script", ""))

        # Expected outputs
        for o in content.get("expected_outputs", []):
            total_chars += len(json.dumps(o, default=str))

        # Tests
        for cat in ("numerical_tests", "algorithmic_tests", "convergence_tests"):
            for t in content.get(cat, []):
                total_chars += len(json.dumps(t, default=str))

        # Overhead: prompt template, system prompt, etc.
        overhead = 8000  # ~2K tokens of prompt overhead
        return (total_chars + overhead) // 4

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _spawn_verification_unit(self, unit: WorkUnit) -> list[WorkUnit]:
        """Create a verification work unit for a task."""
        return [
            WorkUnit(
                kind=WorkUnitKind.VERIFICATION,
                content={
                    "task_id": unit.content.get("id", unit.id),
                    "task_title": unit.content.get("title", ""),
                    "task_description": unit.content.get("description", ""),
                    "acceptance_criteria": unit.content.get("acceptance_criteria", []),
                    "expected_outputs": unit.content.get("expected_outputs", []),
                    "constraints": self._extract_constraints(unit.content),
                    "verification_level": unit.content.get(
                        "verification_level",
                        self._infer_verification_level(unit.content),
                    ),
                },
            )
        ]

    async def _decompose_into_subtasks(self, unit: WorkUnit) -> list[WorkUnit]:
        """Break a task into sub-tasks via Claude Opus."""
        content = unit.content
        prompt = TASK_DECOMPOSE_PROMPT.format(
            title=content.get("title", ""),
            description=content.get("description", ""),
            acceptance_criteria="\n".join(
                f"- {c}" for c in content.get("acceptance_criteria", [])
            ),
            reason=unit.confidence.reason,
            workspace_dir=self.workspace_dir,
            task_id=content.get("id", "T"),
        )

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
                enable_thinking=True,
                stall_timeout=0,
            )

        if not result.success:
            return []  # Can't decompose — engine will execute as-is

        # Parse sub-tasks
        try:
            data = _parse_json(result.output)
            sub_tasks = data.get("sub_tasks", [])
        except (ValueError, KeyError):
            return []

        children = []
        for st in sub_tasks:
            child = WorkUnit(
                kind=WorkUnitKind.TASK,
                content=st,
            )
            children.append(child)

        return children

    async def _decompose_for_context(self, unit: WorkUnit) -> list[WorkUnit]:
        """Split a task that's too large for the context window.

        Strategy: break description into logical sections, each becomes
        a sub-task. Simpler than full LLM decomposition.
        """
        # For now, delegate to the same LLM decomposition
        # but with explicit context-reduction instruction
        unit.confidence.reason = (
            f"Context too large ({unit.context_tokens:,} tokens, "
            f"budget is {unit.context_tokens:,}). Must split."
        )
        return await self._decompose_into_subtasks(unit)

    @staticmethod
    def _is_trivial_check(script: str) -> bool:
        """Detect trivial verify_scripts that prove nothing."""
        if not script or not script.strip():
            return True
        lines = [
            l.strip() for l in script.strip().splitlines()
            if l.strip() and not l.strip().startswith('#')
        ]
        if not lines:
            return True
        trivial_patterns = [
            r'^test\s+-[fedsrwx]\s+', r'^ls\s+', r'^\[\s+-[fedsrwx]\s+',
            r'^echo\s+', r'^true$', r'^exit\s+0$', r'^wc\s+-l\s+',
        ]
        return all(
            any(re.match(p, line) for p in trivial_patterns)
            for line in lines
        )

    @staticmethod
    def _extract_constraints(content: dict) -> list[str]:
        """Extract constraints from task content."""
        constraints = []
        for output in content.get("expected_outputs", []):
            if isinstance(output, dict):
                for p in output.get("must_not_contain", []):
                    constraints.append(f"Code must NOT contain: {p}")
        desc = content.get("description", "")
        for sentence in desc.split("."):
            if any(kw in sentence.lower() for kw in ["must not", "do not", "forbidden"]):
                constraints.append(sentence.strip())
        return constraints

    @staticmethod
    def _infer_verification_level(content: dict) -> str:
        """Infer scientific vs standard from task content."""
        text = (
            content.get("title", "") + " " +
            content.get("description", "") + " " +
            " ".join(content.get("acceptance_criteria", []))
        ).lower()
        keywords = [
            "energy", "eigenvalue", "convergence", "hamiltonian",
            "variational", "ground state", "tensor", "dmrg",
            "mps", "mpo", "svd", "numerical", "simulation",
            "algorithm", "contraction", "diagonalization",
        ]
        return "scientific" if sum(1 for kw in keywords if kw in text) >= 3 else "standard"


def _parse_json(text: str) -> dict:
    """Parse JSON from Claude output, stripping markdown fences."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise
