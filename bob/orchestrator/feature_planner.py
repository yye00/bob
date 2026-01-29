"""
Feature Planner — Confidence-Driven 3-Phase Planning Pipeline
=============================================================

Uses Claude Opus with extended thinking and research to generate
high-confidence implementation plans through three phases:

  Phase 1: PLAN    — Generate tasks with dual confidence scores
  Phase 2: REFINE  — Loop until all confidence > threshold
  Phase 3: VALIDATE — Syntax-check scripts, reject trivial tests

Each task gets TWO confidence scores:
  - implementation_confidence (0.0-1.0): "Can an agent build this atomically?"
  - verification_confidence  (0.0-1.0): "Will verify_script catch real failures?"

The pipeline loops refinement until both scores exceed the threshold
(default 0.9) or max iterations are reached.
"""

import json
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Optional

import yaml

from bob.orchestrator.claude_executor import execute_task_with_claude


# ---------------------------------------------------------------------------
# Phase 1 prompt — initial plan generation
# ---------------------------------------------------------------------------

PHASE1_PLAN_PROMPT = """\
You are a senior software architect creating an implementation plan.

## Application Spec

{spec_content}

## Workspace

The project workspace is: {workspace_dir}

## Your Task

Analyze this spec and produce a DETAILED implementation plan as structured JSON.

For EACH task you generate, include TWO confidence scores:

### Confidence Scores (CRITICAL — think carefully about these)

1. **implementation_confidence** (0.0-1.0):
   "How confident am I that a coding agent can implement this task atomically \
in a single session without ambiguity?"
   - 0.9-1.0: Crystal clear, well-defined, no ambiguity
   - 0.7-0.8: Mostly clear but some details need research
   - 0.5-0.6: Vague requirements, multiple valid approaches
   - <0.5: Too big, too ambiguous, needs decomposition

2. **verification_confidence** (0.0-1.0):
   "How confident am I that the verify_script will actually catch real \
failures vs just checking superficial things?"
   - 0.9-1.0: Tests real behavior, imports & runs code, checks outputs
   - 0.7-0.8: Tests some behavior but misses edge cases
   - 0.5-0.6: Only checks file existence or basic structure
   - <0.5: No meaningful verification possible yet

If EITHER confidence score is below 0.8, you MUST include a \
"confidence_reason" field explaining exactly WHY and WHAT would raise it.

### Verify Script Requirements

**GOOD verify_scripts** (these catch real failures):
```bash
cd {workspace_dir} && python -c "
from src.module import MyClass
obj = MyClass()
result = obj.process('test_input')
assert result is not None, 'process() returned None'
assert len(result) > 0, 'empty result'
assert 'expected_key' in result, 'missing expected_key'
print('PASS: MyClass.process works correctly')
"
```

```bash
cd {workspace_dir} && python -c "
import json
with open('output.json') as f:
    data = json.load(f)
assert 'version' in data, 'missing version field'
assert len(data['items']) >= 3, 'expected at least 3 items'
print('PASS: output.json has correct structure')
"
```

**BAD verify_scripts** (these prove NOTHING — NEVER use these):
```bash
test -f output.json             # File can be empty!
ls src/module.py                # File can have syntax errors!
wc -l src/module.py | grep -q 100  # Line count says nothing about correctness!
echo "done"                     # This always passes!
```

### Expected Outputs
For each file a task should produce, specify:
- `path`: file path relative to workspace
- `min_lines`: realistic minimum line count
- `must_contain`: list of strings that MUST appear (class names, function signatures, imports)
- `must_not_contain`: list of strings that must NOT appear (optional)

## Output Format

Output ONLY valid JSON (no markdown fences, no explanation outside JSON).

```
{{
  "name": "Project Name",
  "description": "Project description",
  "tasks": [
    {{
      "id": "T001",
      "title": "Task title",
      "description": "Detailed description of what to implement",
      "depends_on": [],
      "priority": "critical",
      "labels": ["core"],
      "implementation_confidence": 0.95,
      "verification_confidence": 0.90,
      "confidence_reason": null,
      "acceptance_criteria": [
        "Specific testable criterion 1",
        "Specific testable criterion 2"
      ],
      "expected_outputs": [
        {{
          "path": "src/module.py",
          "min_lines": 100,
          "must_contain": ["class MyClass", "def process"],
          "must_not_contain": ["TODO", "pass  # placeholder"]
        }}
      ],
      "verify_script": "cd {workspace_dir} && python -c \\"\\nimport src.module\\nprint('PASS')\\n\\""
    }}
  ]
}}
```

IMPORTANT:
- Output raw JSON only. No ```json fences. No text before or after.
- Every task MUST have both confidence scores.
- verify_script must be a real behavioral test, not file existence checks.
- Be thorough — missing a task is worse than having too many.
- Think carefully about task ordering and dependencies.

Generate the plan now.
"""


# ---------------------------------------------------------------------------
# Phase 2 prompt — refinement of low-confidence tasks
# ---------------------------------------------------------------------------

PHASE2_REFINE_PROMPT = """\
You are refining an implementation plan to raise confidence scores.

## Workspace
{workspace_dir}

## Current Plan (tasks needing refinement)
{tasks_json}

## Refinement Rules

For each task provided, you must improve it:

### Low implementation_confidence (< {threshold}):
- Break the task into 2-4 smaller, more atomic sub-tasks
- Each sub-task must be completable in a single agent session
- Add specific technical details (exact APIs, patterns, constraints)
- Re-score each sub-task's confidence

### Low verification_confidence (< {threshold}):
- Research: what does correct output actually look like?
- Replace trivial checks (test -f, ls, wc) with real behavioral tests
- Add expected_outputs with specific must_contain patterns
- The verify_script must import code, run it, and assert on results

### For ALL tasks:
- If confidence_reason exists, address the specific concern
- verify_script must reference real paths under {workspace_dir}
- Every critical/high priority task MUST have expected_outputs

## Output Format

Return JSON with the refined tasks. If a task was broken into sub-tasks,
return the sub-tasks (NOT the original). Keep the original task ID as a
prefix (e.g., T001 → T001a, T001b, T001c).

```
{{
  "refined_tasks": [
    {{
      "id": "T001a",
      "parent_id": "T001",
      "title": "...",
      "description": "...",
      "depends_on": [],
      "priority": "critical",
      "labels": ["core"],
      "implementation_confidence": 0.95,
      "verification_confidence": 0.92,
      "confidence_reason": null,
      "acceptance_criteria": ["..."],
      "expected_outputs": [
        {{
          "path": "...",
          "min_lines": 50,
          "must_contain": ["..."]
        }}
      ],
      "verify_script": "cd {workspace_dir} && python -c \\"...\\""
    }}
  ],
  "refinement_notes": "Summary of what was changed and why"
}}
```

Output raw JSON only. No markdown fences. No text outside JSON.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_or_yaml(text: str) -> dict:
    """Parse text as JSON or YAML, stripping markdown fences if present."""
    # Strip markdown code fences
    text = text.strip()
    text = re.sub(r'^```(?:json|yaml|yml)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    text = text.strip()

    # Try JSON first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try YAML
    try:
        result = yaml.safe_load(text)
        if isinstance(result, dict):
            return result
    except yaml.YAMLError:
        pass

    # Try to extract JSON from within larger text
    # Look for the outermost { ... } block
    brace_start = text.find('{')
    brace_end = text.rfind('}')
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(
        f"Could not parse output as JSON or YAML. First 500 chars:\n{text[:500]}"
    )


def _get_low_confidence_tasks(
    tasks: list[dict], threshold: float
) -> list[dict]:
    """Return tasks where either confidence score is below threshold."""
    low = []
    for t in tasks:
        impl_conf = t.get("implementation_confidence", 0.0)
        ver_conf = t.get("verification_confidence", 0.0)
        if impl_conf < threshold or ver_conf < threshold:
            low.append(t)
    return low


def _validate_verify_script_syntax(script: str) -> tuple[bool, str]:
    """Check bash syntax of a verify_script using bash -n."""
    try:
        result = subprocess.run(
            ["bash", "-n"],
            input=script,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def _is_trivial_check(script: str) -> bool:
    """Detect trivial verify_scripts that prove nothing."""
    if not script or not script.strip():
        return True

    stripped = script.strip()
    lines = [l.strip() for l in stripped.splitlines() if l.strip() and not l.strip().startswith('#')]

    if not lines:
        return True

    # Single-line trivial patterns
    trivial_patterns = [
        r'^test\s+-[fedsrwx]\s+',      # test -f, test -e, test -d, etc.
        r'^ls\s+',                       # ls file
        r'^\[\s+-[fedsrwx]\s+',         # [ -f file ]
        r'^echo\s+',                     # echo "done"
        r'^true$',                       # true
        r'^exit\s+0$',                   # exit 0
        r'^wc\s+-l\s+',                 # wc -l file
        r'^cat\s+',                      # cat file
        r'^stat\s+',                     # stat file
        r'^file\s+',                     # file path
    ]

    # If ALL non-comment lines match trivial patterns, it's trivial
    all_trivial = True
    for line in lines:
        is_trivial_line = False
        for pattern in trivial_patterns:
            if re.match(pattern, line):
                is_trivial_line = True
                break
        if not is_trivial_line:
            all_trivial = False
            break

    return all_trivial


def _tasks_to_yaml_spec(plan_data: dict) -> str:
    """Convert plan data dict to YAML spec format for bob sync."""
    spec = {
        "name": plan_data.get("name", "Generated Plan"),
        "description": plan_data.get("description", "Auto-generated by BOB planner"),
        "defaults": {"priority": "critical"},
        "tasks": [],
    }

    for task in plan_data.get("tasks", []):
        yaml_task = {
            "id": task["id"],
            "title": task["title"],
            "description": task.get("description", ""),
            "depends_on": task.get("depends_on", []),
            "priority": task.get("priority", "medium"),
            "labels": task.get("labels", []),
            "acceptance_criteria": task.get("acceptance_criteria", []),
            "expected_outputs": task.get("expected_outputs", []),
            "verify_script": task.get("verify_script", ""),
        }
        # Include confidence metadata as comments won't work,
        # so store as fields that bob sync can ignore or use
        yaml_task["implementation_confidence"] = task.get(
            "implementation_confidence", 0.0
        )
        yaml_task["verification_confidence"] = task.get(
            "verification_confidence", 0.0
        )
        if task.get("confidence_reason"):
            yaml_task["confidence_reason"] = task["confidence_reason"]

        spec["tasks"].append(yaml_task)

    return yaml.dump(spec, default_flow_style=False, sort_keys=False, width=120)


# ---------------------------------------------------------------------------
# Main Planner Class
# ---------------------------------------------------------------------------

class FeaturePlanner:
    """
    Confidence-driven 3-phase feature planning pipeline.

    Phase 1: PLAN    — Opus generates tasks with confidence scores
    Phase 2: REFINE  — Loop until confidence > threshold
    Phase 3: VALIDATE — Syntax-check scripts, reject trivial tests
    """

    def __init__(
        self,
        workspace_dir: str,
        project_dir: Path,
        model: str = "claude-opus-4-5-20251101",
        thinking_budget: int = 16000,
        confidence_threshold: float = 0.9,
        max_refinement_iterations: int = 3,
        enable_research: bool = True,
        timeout_seconds: int = 600,
    ):
        self.workspace_dir = workspace_dir
        self.project_dir = project_dir
        self.model = model
        self.thinking_budget = thinking_budget
        self.confidence_threshold = confidence_threshold
        self.max_refinement_iterations = max_refinement_iterations
        self.enable_research = enable_research
        self.timeout_seconds = timeout_seconds

        # Intermediate output directory
        self.output_dir = Path(workspace_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Phase 1: PLAN
    # ------------------------------------------------------------------

    async def phase1_plan(self, spec_content: str) -> dict:
        """
        Generate initial plan with confidence scores.

        Returns:
            Plan dict with tasks, each having confidence scores.
        """
        print("\n" + "=" * 60)
        print("  PHASE 1: PLAN — Generating tasks with confidence scores")
        print("=" * 60)
        print(f"  Model: {self.model}")
        print(f"  Thinking budget: {self.thinking_budget} tokens")
        print(f"  Research enabled: {self.enable_research}")
        print()

        prompt = PHASE1_PLAN_PROMPT.format(
            spec_content=spec_content,
            workspace_dir=self.workspace_dir,
        )

        # Ask Claude to also write the plan to a file for persistence
        plan_file = self.output_dir / "plan.json"
        prompt += (
            f"\n\nAlso write your JSON output to: {plan_file}\n"
        )

        result = await execute_task_with_claude(
            project_dir=self.project_dir,
            prompt=prompt,
            model=self.model,
            timeout_seconds=self.timeout_seconds,
            non_interactive=True,
            enable_thinking=True,
            thinking_budget=self.thinking_budget,
        )

        if not result.success:
            raise RuntimeError(
                f"Phase 1 (PLAN) failed: {result.error or 'Unknown error'}\n"
                f"Output: {result.output[:1000] if result.output else 'none'}"
            )

        # Try reading from file first, then parse output
        plan_data = None
        if plan_file.exists():
            try:
                plan_data = _parse_json_or_yaml(plan_file.read_text())
            except ValueError:
                pass

        if plan_data is None:
            plan_data = _parse_json_or_yaml(result.output)

        # Persist intermediate result
        plan_file.write_text(json.dumps(plan_data, indent=2))

        tasks = plan_data.get("tasks", [])
        print(f"  ✓ Generated {len(tasks)} tasks")

        for t in tasks:
            impl = t.get("implementation_confidence", 0.0)
            ver = t.get("verification_confidence", 0.0)
            status = "✓" if (impl >= self.confidence_threshold and ver >= self.confidence_threshold) else "⚠"
            print(
                f"    {status} {t['id']}: impl={impl:.2f} ver={ver:.2f}"
                f"  — {t['title'][:60]}"
            )

        return plan_data

    # ------------------------------------------------------------------
    # Phase 2: REFINE
    # ------------------------------------------------------------------

    async def phase2_refine(self, plan_data: dict) -> dict:
        """
        Iteratively refine low-confidence tasks.

        Loops until all tasks exceed the confidence threshold or
        max iterations are reached. Sub-tasks can be recursively
        refined up to depth 2.

        Returns:
            Refined plan dict.
        """
        print("\n" + "=" * 60)
        print("  PHASE 2: REFINE — Raising confidence scores")
        print("=" * 60)
        print(f"  Threshold: {self.confidence_threshold}")
        print(f"  Max iterations: {self.max_refinement_iterations}")
        print()

        all_tasks = list(plan_data.get("tasks", []))

        for iteration in range(1, self.max_refinement_iterations + 1):
            low_tasks = _get_low_confidence_tasks(all_tasks, self.confidence_threshold)

            if not low_tasks:
                print(f"  ✓ All tasks above threshold ({self.confidence_threshold}) — no refinement needed")
                break

            print(f"  Iteration {iteration}/{self.max_refinement_iterations}: "
                  f"{len(low_tasks)} tasks below threshold")

            for t in low_tasks:
                impl = t.get("implementation_confidence", 0.0)
                ver = t.get("verification_confidence", 0.0)
                reason = t.get("confidence_reason", "no reason given")
                print(
                    f"    ⚠ {t['id']}: impl={impl:.2f} ver={ver:.2f}"
                    f"  — {reason[:80] if reason else 'no reason'}"
                )

            # Call Claude to refine
            prompt = PHASE2_REFINE_PROMPT.format(
                workspace_dir=self.workspace_dir,
                tasks_json=json.dumps(low_tasks, indent=2),
                threshold=self.confidence_threshold,
            )

            refined_file = self.output_dir / f"refined_plan_iter{iteration}.json"
            prompt += f"\n\nAlso write your JSON output to: {refined_file}\n"

            result = await execute_task_with_claude(
                project_dir=self.project_dir,
                prompt=prompt,
                model=self.model,
                timeout_seconds=self.timeout_seconds,
                non_interactive=True,
                enable_thinking=True,
                thinking_budget=self.thinking_budget,
            )

            if not result.success:
                print(f"  ✗ Refinement iteration {iteration} failed: "
                      f"{result.error or 'unknown'}")
                print("    Continuing with current tasks...")
                break

            # Parse refinement result
            refined_data = None
            if refined_file.exists():
                try:
                    refined_data = _parse_json_or_yaml(refined_file.read_text())
                except ValueError:
                    pass

            if refined_data is None:
                try:
                    refined_data = _parse_json_or_yaml(result.output)
                except ValueError as e:
                    print(f"  ✗ Could not parse refinement output: {e}")
                    print("    Continuing with current tasks...")
                    break

            refined_tasks = refined_data.get("refined_tasks", [])
            notes = refined_data.get("refinement_notes", "")

            if not refined_tasks:
                print("  ⚠ Refinement returned no tasks — keeping originals")
                break

            if notes:
                print(f"  📝 {notes[:120]}")

            # Replace low-confidence tasks with refined versions
            low_ids = {t["id"] for t in low_tasks}
            # Keep tasks that weren't refined
            kept_tasks = [t for t in all_tasks if t["id"] not in low_ids]
            # Also remove tasks whose parent_id was refined (sub-tasks replace parent)
            parent_ids = {t.get("parent_id") for t in refined_tasks if t.get("parent_id")}
            kept_tasks = [t for t in kept_tasks if t["id"] not in parent_ids]
            # Add refined tasks
            all_tasks = kept_tasks + refined_tasks

            # Show new confidence scores
            for t in refined_tasks:
                impl = t.get("implementation_confidence", 0.0)
                ver = t.get("verification_confidence", 0.0)
                status = "✓" if (impl >= self.confidence_threshold and ver >= self.confidence_threshold) else "⚠"
                print(
                    f"    {status} {t['id']}: impl={impl:.2f} ver={ver:.2f}"
                    f"  — {t['title'][:60]}"
                )

            # Persist
            refined_file.write_text(json.dumps(
                {"tasks": all_tasks, "iteration": iteration, "notes": notes},
                indent=2,
            ))

        # Check for recursive refinement (depth 2)
        still_low = _get_low_confidence_tasks(all_tasks, self.confidence_threshold)
        if still_low:
            print(f"\n  ⚠ {len(still_low)} tasks still below threshold after all iterations")
            for t in still_low:
                impl = t.get("implementation_confidence", 0.0)
                ver = t.get("verification_confidence", 0.0)
                print(f"    ⚠ {t['id']}: impl={impl:.2f} ver={ver:.2f}")

        plan_data["tasks"] = all_tasks
        return plan_data

    # ------------------------------------------------------------------
    # Phase 3: VALIDATE
    # ------------------------------------------------------------------

    async def phase3_validate(self, plan_data: dict) -> tuple[dict, list[str]]:
        """
        Validate the plan:
        - Syntax-check all verify_scripts (bash -n)
        - Flag trivial checks as failures
        - Ensure critical/high tasks have expected_outputs

        Returns:
            Tuple of (validated plan dict, list of warnings).
        """
        print("\n" + "=" * 60)
        print("  PHASE 3: VALIDATE — Checking plan quality")
        print("=" * 60 + "\n")

        warnings: list[str] = []
        tasks = plan_data.get("tasks", [])

        for task in tasks:
            task_id = task.get("id", "???")
            script = task.get("verify_script", "")
            priority = task.get("priority", "medium")

            # --- Check 1: Syntax-check verify_script ---
            if script and script.strip():
                valid, err = _validate_verify_script_syntax(script)
                if not valid:
                    msg = f"{task_id}: verify_script has syntax error: {err}"
                    warnings.append(msg)
                    print(f"  ✗ {msg}")
            else:
                msg = f"{task_id}: missing verify_script"
                warnings.append(msg)
                print(f"  ⚠ {msg}")

            # --- Check 2: Detect trivial checks ---
            if script and _is_trivial_check(script):
                msg = (
                    f"{task_id}: verify_script is trivial "
                    f"(only file-existence or echo checks)"
                )
                warnings.append(msg)
                print(f"  ✗ {msg}")
                # Mark verification confidence as low
                task["verification_confidence"] = min(
                    task.get("verification_confidence", 0.0), 0.3
                )

            # --- Check 3: critical/high tasks need expected_outputs ---
            if priority in ("critical", "high"):
                outputs = task.get("expected_outputs", [])
                if not outputs:
                    msg = f"{task_id}: {priority} priority but no expected_outputs"
                    warnings.append(msg)
                    print(f"  ⚠ {msg}")

        # Summary
        total = len(tasks)
        above = len([
            t for t in tasks
            if t.get("implementation_confidence", 0.0) >= self.confidence_threshold
            and t.get("verification_confidence", 0.0) >= self.confidence_threshold
        ])
        print(f"\n  Summary: {above}/{total} tasks at or above "
              f"confidence threshold ({self.confidence_threshold})")
        if warnings:
            print(f"  ⚠ {len(warnings)} warning(s) found")
        else:
            print("  ✓ No warnings — plan looks solid")

        return plan_data, warnings

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    async def run(self, spec_content: str) -> tuple[str, dict, list[str]]:
        """
        Run the full 3-phase planning pipeline.

        Args:
            spec_content: Raw application spec text.

        Returns:
            Tuple of (yaml_output_path, plan_data, warnings).
        """
        # Phase 1: PLAN
        plan_data = await self.phase1_plan(spec_content)

        # Phase 2: REFINE
        plan_data = await self.phase2_refine(plan_data)

        # Phase 3: VALIDATE
        plan_data, warnings = await self.phase3_validate(plan_data)

        # Write final YAML spec
        yaml_output = _tasks_to_yaml_spec(plan_data)
        output_path = self.output_dir / "generated_spec.yaml"
        output_path.write_text(yaml_output)

        # Also persist final JSON
        final_json = self.output_dir / "final_plan.json"
        final_json.write_text(json.dumps(plan_data, indent=2))

        print(f"\n  📄 YAML spec written to: {output_path}")
        print(f"  📄 JSON plan written to: {final_json}")

        return str(output_path), plan_data, warnings


# ---------------------------------------------------------------------------
# Convenience functions (backward-compatible API)
# ---------------------------------------------------------------------------

async def generate_feature_plan(
    spec_content: str,
    workspace_dir: str,
    project_dir: Path,
    model: str = "claude-opus-4-5-20251101",
    enable_thinking: bool = True,
    thinking_budget: int = 16000,
    timeout_seconds: int = 600,
    confidence_threshold: float = 0.9,
    max_refinement_iterations: int = 3,
    enable_research: bool = True,
) -> tuple[bool, str, Optional[str]]:
    """
    Use the 3-phase pipeline to generate a feature plan.

    Returns:
        Tuple of (success, yaml_content_or_error, output_path).
    """
    try:
        planner = FeaturePlanner(
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            model=model,
            thinking_budget=thinking_budget,
            confidence_threshold=confidence_threshold,
            max_refinement_iterations=max_refinement_iterations,
            enable_research=enable_research,
            timeout_seconds=timeout_seconds,
        )
        output_path, plan_data, warnings = await planner.run(spec_content)
        content = Path(output_path).read_text()
        return True, content, output_path
    except Exception as e:
        return False, str(e), None


async def enhance_existing_spec(
    spec_path: str,
    workspace_dir: str,
    project_dir: Path,
    model: str = "claude-opus-4-5-20251101",
    enable_thinking: bool = True,
    thinking_budget: int = 16000,
    confidence_threshold: float = 0.9,
    max_refinement_iterations: int = 3,
    enable_research: bool = True,
) -> tuple[bool, str]:
    """
    Enhance an existing spec by running it through the refinement pipeline.

    Reads the existing spec, treats each task as a plan, then runs Phase 2
    (REFINE) and Phase 3 (VALIDATE) to improve confidence.

    Returns:
        Tuple of (success, enhanced_yaml_or_error).
    """
    try:
        spec_content = Path(spec_path).read_text()
        # Parse existing spec
        try:
            existing = yaml.safe_load(spec_content)
        except yaml.YAMLError:
            existing = None

        if existing and isinstance(existing, dict) and "tasks" in existing:
            # Existing spec has tasks — run refinement on them
            # Add default confidence scores if missing
            for task in existing["tasks"]:
                if "implementation_confidence" not in task:
                    task["implementation_confidence"] = 0.5
                if "verification_confidence" not in task:
                    task["verification_confidence"] = 0.3

            planner = FeaturePlanner(
                workspace_dir=workspace_dir,
                project_dir=project_dir,
                model=model,
                thinking_budget=thinking_budget,
                confidence_threshold=confidence_threshold,
                max_refinement_iterations=max_refinement_iterations,
                enable_research=enable_research,
            )

            # Run Phase 2 + Phase 3
            print("\n🔄 Enhancing existing spec through refinement pipeline...")
            existing = await planner.phase2_refine(existing)
            existing, warnings = await planner.phase3_validate(existing)

            yaml_output = _tasks_to_yaml_spec(existing)
            output_path = Path(workspace_dir) / "enhanced_spec.yaml"
            output_path.write_text(yaml_output)
            return True, yaml_output
        else:
            # Treat the entire file as a spec and generate from scratch
            return await _enhance_from_scratch(
                spec_content, workspace_dir, project_dir,
                model, thinking_budget, confidence_threshold,
                max_refinement_iterations, enable_research,
            )
    except Exception as e:
        return False, str(e)


async def _enhance_from_scratch(
    spec_content: str,
    workspace_dir: str,
    project_dir: Path,
    model: str,
    thinking_budget: int,
    confidence_threshold: float,
    max_refinement_iterations: int,
    enable_research: bool,
) -> tuple[bool, str]:
    """Fallback: generate a full plan from spec content."""
    success, content, path = await generate_feature_plan(
        spec_content=spec_content,
        workspace_dir=workspace_dir,
        project_dir=project_dir,
        model=model,
        thinking_budget=thinking_budget,
        confidence_threshold=confidence_threshold,
        max_refinement_iterations=max_refinement_iterations,
        enable_research=enable_research,
    )
    return success, content
