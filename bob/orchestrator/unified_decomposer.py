"""
Unified Decomposer — Tests generated per-feature during decomposition.
=======================================================================

Replaces the old split between TaskDecomposer and VerificationDecomposer
with a single decomposer that handles both in one pass.

Key differences from the old approach:
1. When a task is decomposed into sub-tasks, verification contracts
   are generated IMMEDIATELY for each sub-task (not in a separate phase)
2. Parent tasks keep integration-level contracts; children get unit-level
3. Tests are written as .py files (via ContractWriter), not JSON strings
4. Convergence-based stopping: re-evaluate after children, stop when
   confidence delta < 0.05 for 2 consecutive evaluations

The hierarchy:
    Root Task (system-level contracts)
    ├── Sub-task A (unit-level contracts)
    ├── Sub-task B (unit-level contracts)
    └── Integration contracts (from parent)
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
    WorkUnitStatus,
    ConfidenceScore,
)
from bob.orchestrator.contract_writer import (
    ContractWriter,
    CONTRACT_GENERATION_PROMPT,
    CATEGORY_GUIDANCE,
)
from bob.orchestrator.verification_level import VerificationLevel
from bob.observability.logger import EventType, create_logger

# Prefer SDK executor
try:
    from bob.orchestrator.claude_sdk_executor import execute_task_with_sdk as _sdk_execute
    _USE_SDK = True
except ImportError:
    _USE_SDK = False

from bob.orchestrator.claude_executor import execute_task_with_claude


# ---------------------------------------------------------------------------
# Prompt for task decomposition (sub-task generation)
# ---------------------------------------------------------------------------

UNIFIED_DECOMPOSE_PROMPT = """\
You are a senior software architect. Break this task into 2-4 smaller,
more atomic sub-tasks that can each be completed in a single agent session.

## Task to Decompose
**ID:** {task_id}
**Title:** {title}
**Description:**
{description}

**Acceptance Criteria:**
{acceptance_criteria}

**Why it needs decomposition:** {reason}

## Workspace
{workspace_dir}

## Rules
1. Each sub-task must be completable in a single session (~200-500 LOC)
2. Sub-tasks inherit the parent's workspace and environment
3. Each sub-task needs its OWN acceptance criteria (specific, testable)
4. Dependencies between sub-tasks should be explicit
5. The parent task becomes an integration task (verifies sub-tasks work together)

## Output Format
Output ONLY valid JSON (no markdown fences):
{{
  "sub_tasks": [
    {{
      "id": "{task_id}a",
      "title": "Sub-task title",
      "description": "Detailed description of what to implement",
      "depends_on": [],
      "priority": "critical",
      "acceptance_criteria": ["Specific criterion 1", "Specific criterion 2"],
      "expected_outputs": [
        {{"path": "src/module.py", "min_lines": 50, "must_contain": ["class X"]}}
      ]
    }}
  ],
  "integration_criteria": [
    "Integration criterion 1 (tests sub-tasks work together)",
    "Integration criterion 2"
  ]
}}
"""


class UnifiedDecomposer(Decomposer):
    """Unified task + verification decomposer.

    Generates verification contracts per-feature during decomposition,
    maintaining a hierarchy of unit/integration/system tests.

    Attributes:
        workspace_dir: Project workspace path
        project_dir: Project directory for Claude execution
        contract_writer: Writes and validates .py contract files
        model: LLM model for generation
        references: Reference documents from spec
    """

    def __init__(
        self,
        workspace_dir: str,
        project_dir: Path,
        model: str = "claude-opus-4-5-20251101",
        timeout_seconds: int = 0,
        references: list[dict] | None = None,
        forbidden_imports: set[str] | None = None,
    ):
        self.workspace_dir = workspace_dir
        self.project_dir = project_dir
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.references = references or []
        self.contract_writer = ContractWriter(
            workspace_dir=workspace_dir,
            forbidden_imports=forbidden_imports,
        )
        self.logger = create_logger(
            "unified_decomposer",
            project_workspace=Path(workspace_dir),
        )

    async def evaluate(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> ConfidenceScore:
        """Evaluate a task's confidence with contract awareness.

        Implementation confidence: based on description quality, scope, criteria.
        Verification confidence: based on whether validated .py contracts exist.

        The key innovation: verification confidence checks for actual .py files
        in .bob/contracts/, not just whether JSON test dicts exist.
        """
        content = unit.content
        impl_score = 0.5
        ver_score = 0.3

        # ─── Implementation confidence ──────────────────────────
        desc = content.get("description", "")
        criteria = content.get("acceptance_criteria", [])
        outputs = content.get("expected_outputs", [])

        if len(desc) > 200:
            impl_score += 0.15
        if len(desc) > 500:
            impl_score += 0.1
        if criteria:
            impl_score += min(0.15, len(criteria) * 0.05)
        if outputs:
            impl_score += 0.1

        # Blend with planner's assessment if available
        if "implementation_confidence" in content:
            planner_conf = content["implementation_confidence"]
            impl_score = 0.6 * planner_conf + 0.4 * impl_score

        impl_score = min(1.0, impl_score)

        # ─── Verification confidence ────────────────────────────
        task_id = content.get("id", unit.id)

        # Check for .py contract files
        contracts = self.contract_writer.list_contracts(task_id)
        validated_contracts = 0

        for contract_path in contracts:
            is_valid, errors = self.contract_writer.validate_contract(contract_path)
            if is_valid:
                validated_contracts += 1

        if validated_contracts >= 3:
            # All 3 categories have validated contracts
            ver_score = 0.95
        elif validated_contracts >= 2:
            ver_score = 0.8
        elif validated_contracts >= 1:
            ver_score = 0.6
        else:
            # Fall back to checking old-style tests
            verify_script = content.get("verify_script", "")
            numerical = content.get("numerical_tests", [])
            algorithmic = content.get("algorithmic_tests", [])
            convergence = content.get("convergence_tests", [])

            if verify_script and verify_script.strip():
                if not self._is_trivial_check(verify_script):
                    ver_score += 0.15
            if numerical:
                ver_score += min(0.15, len(numerical) * 0.07)
            if algorithmic:
                ver_score += min(0.1, len(algorithmic) * 0.07)
            if convergence:
                ver_score += min(0.1, len(convergence) * 0.07)

        # Blend with planner's assessment if available
        if "verification_confidence" in content and validated_contracts == 0:
            planner_conf = content["verification_confidence"]
            ver_score = 0.6 * planner_conf + 0.4 * ver_score

        ver_score = min(1.0, ver_score)

        reason = ""
        if impl_score < 0.9:
            reason += f"impl={impl_score:.2f} (needs decomposition). "
        if ver_score < 0.9:
            reason += f"ver={ver_score:.2f} ({validated_contracts} validated contracts). "

        return ConfidenceScore(
            implementation=impl_score,
            verification=ver_score,
            context_fit=1.0,  # Engine overrides this
            reason=reason.strip(),
        )

    async def decompose(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> list[WorkUnit]:
        """Decompose based on weakest dimension, generating contracts immediately.

        If implementation is weakest → break into sub-tasks + generate
            unit-level contracts for each + promote parent to integration.
        If verification is weakest → generate contracts for this task.
        If context_fit is weakest → split into smaller tasks.
        """
        weakest = unit.confidence.weakest_dimension

        if weakest == "verification":
            # Verification weak → generate contracts (no sub-tasks)
            await self._generate_contracts_for_task(unit)
            # Return empty — no new children, just updated contracts
            # The engine will re-evaluate and see improved verification
            return []

        elif weakest == "context_fit":
            # Context too large → decompose into sub-tasks
            unit.confidence.reason = (
                f"Context too large ({unit.context_tokens:,} tokens). Splitting."
            )
            return await self._decompose_into_subtasks(unit, tree)

        else:
            # Implementation weak → decompose into sub-tasks
            return await self._decompose_into_subtasks(unit, tree)

    async def execute(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> dict[str, Any]:
        """Finalize a task: collect contracts, merge child results.

        When a task is "executed" during planning, it means:
        1. Collect contract paths from all child tasks
        2. If this is a parent (has children), write integration contracts
        3. Return the finalized task content with contract references
        """
        content = unit.content
        task_id = content.get("id", unit.id)

        # Collect contract paths
        contract_paths = [str(p) for p in self.contract_writer.list_contracts(task_id)]

        # Collect verification results from child work units
        for child_id in unit.children:
            child = tree.get(child_id)
            if not child:
                continue

            if child.kind == WorkUnitKind.VERIFICATION and child.result:
                # Merge old-style verification tests
                for cat in ("numerical_tests", "algorithmic_tests", "convergence_tests"):
                    if cat in child.result:
                        existing = content.get(cat, [])
                        existing.extend(child.result[cat])
                        content[cat] = existing

            elif child.kind == WorkUnitKind.TASK and child.result:
                # Collect child task's contracts
                child_task = child.result.get("task", {})
                child_contracts = child_task.get("contract_paths", [])
                contract_paths.extend(child_contracts)

        # Convert any remaining old-style tests to contracts
        await self._convert_old_tests_to_contracts(unit)

        # Collect integration contract paths (from parent decomposition)
        integration_paths = content.get("_integration_contract_paths", [])

        # Update contract paths
        content["contract_paths"] = contract_paths
        content["integration_contract_paths"] = integration_paths
        content["contracts_dir"] = str(self.contract_writer.contracts_dir)

        # Classify contracts by level
        level_counts = {"unit": 0, "integration": 0, "system": 0}
        for cp in contract_paths:
            cp_path = Path(cp) if not isinstance(cp, Path) else cp
            if cp_path.exists():
                level = self.contract_writer.get_contract_level(cp_path)
                if level:
                    level_counts[level.value] += 1

        content["contract_level_counts"] = level_counts

        return {"status": "ready", "task": content}

    def estimate_context_tokens(self, unit: WorkUnit) -> int:
        """Estimate tokens for a task's full context."""
        content = unit.content
        total_chars = 0

        total_chars += len(content.get("description", ""))
        total_chars += sum(len(c) for c in content.get("acceptance_criteria", []))
        total_chars += len(content.get("verify_script", ""))

        for o in content.get("expected_outputs", []):
            total_chars += len(json.dumps(o, default=str))

        # Contract files are NOT part of the coding context
        # (they're run separately), so don't count them

        overhead = 8000
        return (total_chars + overhead) // 4

    # ------------------------------------------------------------------
    # Contract generation
    # ------------------------------------------------------------------

    async def _generate_contracts_for_task(self, unit: WorkUnit) -> None:
        """Generate verification contracts for a task.

        Calls Claude to generate pytest-style test code for each category.
        Writes to .bob/contracts/ as .py files.
        Validates with static analysis + meta-test execution (B+C hybrid).
        Retries up to 3x if validation fails.

        Verification level is inferred from the unit's position in the tree:
        - Root tasks (no parent) → SYSTEM
        - Intermediate tasks → INTEGRATION
        - Leaf tasks → UNIT
        """
        content = unit.content
        task_id = content.get("id", unit.id)
        task_title = content.get("title", "")

        # Infer verification level from tree position
        is_root = unit.parent_id is None
        verification_level = VerificationLevel.infer_from_depth(
            unit.depth, is_root=is_root
        )

        # Build research context from references
        research_context = self._build_research_context(content)

        # Format task metadata
        criteria_str = "\n".join(
            f"- {c}" for c in content.get("acceptance_criteria", [])
        ) or "(none)"

        outputs = content.get("expected_outputs", [])
        outputs_str = "\n".join(
            f"- {o.get('path', o) if isinstance(o, dict) else o}"
            for o in outputs
        ) or "(none)"

        categories = ["numerical", "algorithmic", "convergence"]
        verification_level = content.get(
            "verification_level",
            self._infer_verification_level(content),
        )

        # Only generate scientific tests for scientific tasks
        if verification_level != "scientific":
            categories = ["numerical", "algorithmic"]

        for category in categories:
            # Skip if already has a valid contract
            existing = [
                p for p in self.contract_writer.list_contracts(task_id)
                if category in p.name
            ]
            if existing:
                is_valid, _ = self.contract_writer.validate_contract(existing[0])
                if is_valid:
                    continue

            guidance = CATEGORY_GUIDANCE.get(category, "")
            prompt = CONTRACT_GENERATION_PROMPT.format(
                task_id=task_id,
                task_title=task_title,
                task_description=content.get("description", ""),
                acceptance_criteria=criteria_str,
                expected_outputs=outputs_str,
                research_context=research_context,
                workspace_dir=self.workspace_dir,
                category=category,
                category_guidance=guidance,
            )

            # Retry loop for contract generation
            for attempt in range(1, 4):
                test_code = await self._call_claude(prompt)
                if not test_code:
                    self.logger.info(
                        f"Contract generation failed for {task_id}/{category} "
                        f"(attempt {attempt}/3): no output",
                        event_type=EventType.DECOMPOSITION_COMPLETED,
                    )
                    continue

                # Clean up the output
                test_code = self._clean_test_code(test_code)

                # Write contract file with verification level
                contract_path = self.contract_writer.write_contract(
                    task_id=task_id,
                    category=category,
                    test_code=test_code,
                    source=f"Generated for {task_title}",
                    verification_level=verification_level,
                )

                # Full validation: static analysis + meta-test execution
                # Meta-tests verify the contract structure is non-trivial
                # (from C's self-checking contracts design)
                is_valid, errors = self.contract_writer.validate_with_meta_tests(
                    contract_path
                )

                if is_valid:
                    print(
                        f"    ✓ Contract {task_id}/{category} "
                        f"[{verification_level.value}]: "
                        f"validated + meta-tests passed (attempt {attempt})"
                    )
                    break
                else:
                    print(
                        f"    ⚠ Contract {task_id}/{category}: "
                        f"validation failed (attempt {attempt}): "
                        f"{'; '.join(errors[:2])}"
                    )
                    # Add error context to prompt for next attempt
                    prompt += (
                        f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION:\n"
                        f"{chr(10).join(errors)}\n"
                        f"Fix these issues in your next attempt."
                    )
            else:
                print(
                    f"    ✗ Contract {task_id}/{category}: "
                    f"all 3 attempts failed"
                )

    async def _decompose_into_subtasks(
        self, unit: WorkUnit, tree: dict[str, WorkUnit]
    ) -> list[WorkUnit]:
        """Break a task into sub-tasks and generate contracts for each.

        1. Call Claude to decompose the task
        2. Create WorkUnit children
        3. Generate unit-level contracts for each child
        4. Promote parent's contracts to integration level
        """
        content = unit.content
        task_id = content.get("id", "T")
        prompt = UNIFIED_DECOMPOSE_PROMPT.format(
            task_id=task_id,
            title=content.get("title", ""),
            description=content.get("description", ""),
            acceptance_criteria="\n".join(
                f"- {c}" for c in content.get("acceptance_criteria", [])
            ),
            reason=unit.confidence.reason,
            workspace_dir=self.workspace_dir,
        )

        output = await self._call_claude(prompt)
        if not output:
            return []

        # Parse sub-tasks
        try:
            data = _parse_json(output)
            sub_tasks = data.get("sub_tasks", [])
            integration_criteria = data.get("integration_criteria", [])
        except (ValueError, KeyError):
            return []

        if not sub_tasks:
            return []

        # Store integration criteria on the parent
        content["integration_criteria"] = integration_criteria

        # ─── Hierarchical contract distribution (C element) ─────
        # Promote parent's existing contracts from UNIT → INTEGRATION.
        # When children complete, the parent's integration contracts
        # verify they all work together correctly.
        existing_contracts = self.contract_writer.list_contracts(task_id)
        promoted_count = 0
        for contract_path in existing_contracts:
            current_level = self.contract_writer.get_contract_level(contract_path)
            if current_level == VerificationLevel.UNIT:
                self.contract_writer.promote_to_integration(contract_path)
                promoted_count += 1

        if promoted_count > 0:
            print(
                f"    ↑ Promoted {promoted_count} contracts to INTEGRATION "
                f"for {task_id}"
            )

        # Store promoted contract paths for post-child verification
        content["_integration_contract_paths"] = [
            str(p) for p in existing_contracts
        ]

        # Create children
        children = []
        for st in sub_tasks:
            child = WorkUnit(
                kind=WorkUnitKind.TASK,
                content=st,
            )
            children.append(child)

        # Children will get UNIT-level contracts during their own
        # processing cycle (the engine evaluates and generates contracts
        # for each child independently)

        self.logger.info(
            f"Decomposed {task_id} into {len(children)} sub-tasks "
            f"(promoted {promoted_count} contracts to integration)",
            event_type=EventType.DECOMPOSITION_STARTED,
            task_id=task_id,
            sub_tasks=[st.get("id", "?") for st in sub_tasks],
            integration_criteria=integration_criteria,
            promoted_contracts=promoted_count,
        )

        return children

    async def _convert_old_tests_to_contracts(self, unit: WorkUnit) -> None:
        """Convert old-style embedded tests to .py contract files.

        Takes numerical_tests, algorithmic_tests, convergence_tests from
        the task content (JSON command strings) and converts them to
        proper pytest contract files.
        """
        content = unit.content
        task_id = content.get("id", unit.id)

        for category in ("numerical", "algorithmic", "convergence"):
            key = f"{category}_tests"
            tests = content.get(key, [])
            if not tests:
                continue

            # Check if contract already exists
            existing = [
                p for p in self.contract_writer.list_contracts(task_id)
                if category in p.name
            ]
            if existing:
                is_valid, _ = self.contract_writer.validate_contract(existing[0])
                if is_valid:
                    continue  # Already have a good contract

            # Convert old tests to Python code
            test_code = ContractWriter.convert_old_tests_to_contract_code(
                tests, category
            )
            if not test_code.strip():
                continue

            # Write contract
            contract_path = self.contract_writer.write_contract(
                task_id=task_id,
                category=category,
                test_code=test_code,
                source=f"Converted from {key} (legacy format)",
            )

            # Validate (best-effort — converted tests may not be perfect)
            is_valid, errors = self.contract_writer.validate_contract(contract_path)
            if not is_valid:
                self.logger.info(
                    f"Converted contract {contract_path.name} has issues: "
                    f"{'; '.join(errors[:2])}",
                    event_type=EventType.DECOMPOSITION_COMPLETED,
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_research_context(self, content: dict) -> str:
        """Build research context from references and task content."""
        parts = []

        # From task's research findings
        findings = content.get("research_findings", "")
        if findings:
            if isinstance(findings, dict):
                findings = json.dumps(findings, indent=2)
            parts.append(f"### Previous Research\n{findings}")

        # From reference papers (just labels — full text is too much)
        if self.references:
            ref_list = "\n".join(
                f"- {r.get('label', r.get('path', 'unknown'))}"
                for r in self.references
            )
            parts.append(f"### Available References\n{ref_list}")

        return "\n\n".join(parts) if parts else "(no research context available)"

    async def _call_claude(self, prompt: str) -> str | None:
        """Call Claude and return the raw output text."""
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
            return None
        return result.output

    @staticmethod
    def _clean_test_code(code: str) -> str:
        """Clean up Claude's test code output.

        Strips markdown fences, removes file-level imports that
        conflict with the template, etc.
        """
        code = code.strip()

        # Strip markdown fences
        code = re.sub(r'^```(?:python)?\s*\n', '', code)
        code = re.sub(r'\n```\s*$', '', code)
        code = code.strip()

        # Remove file-level duplicate imports that the template already has
        # (pytest, ast, sys, Path are in the template)
        lines = code.split("\n")
        filtered = []
        template_imports = {"import pytest", "import ast", "import sys", "from pathlib import Path"}
        for line in lines:
            stripped = line.strip()
            if stripped in template_imports:
                continue
            filtered.append(line)

        return "\n".join(filtered)

    @staticmethod
    def _is_trivial_check(script: str) -> bool:
        """Detect trivial verify_scripts."""
        if not script or not script.strip():
            return True
        lines = [
            l.strip()
            for l in script.strip().splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        if not lines:
            return True
        trivial_patterns = [
            r'^test\s+-[fedsrwx]\s+',
            r'^ls\s+',
            r'^\[\s+-[fedsrwx]\s+',
            r'^echo\s+',
            r'^true$',
            r'^exit\s+0$',
            r'^wc\s+-l\s+',
        ]
        return all(
            any(re.match(p, line) for p in trivial_patterns) for line in lines
        )

    @staticmethod
    def _infer_verification_level(content: dict) -> str:
        """Infer scientific vs standard from task content."""
        text = (
            content.get("title", "")
            + " "
            + content.get("description", "")
            + " "
            + " ".join(content.get("acceptance_criteria", []))
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
