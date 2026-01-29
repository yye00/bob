"""
Feature Planner — Opus-Powered Task Generation
================================================

Uses Claude Opus to read an application spec and generate a detailed
feature list with:
- Meaningful acceptance criteria
- Proper expected_outputs with must_contain patterns
- Real verify_scripts that test actual behavior (not just file existence)
- Correct dependency ordering
- Complexity assessment

This is the "planning phase" of BOB. Implementation uses Sonnet (with
escalation to Opus on failure), but planning ALWAYS uses Opus for
better reasoning about what needs to be built and how to verify it.
"""

import json
from pathlib import Path
from typing import Optional

from bob.orchestrator.claude_executor import execute_task_with_claude


PLANNING_PROMPT_TEMPLATE = """You are a senior software architect planning the implementation of a project.

## Application Spec

{spec_content}

## Your Task

Read this application spec carefully and generate a DETAILED implementation plan as a YAML task list.

For EACH task you generate, you MUST include:

### 1. Clear Description
- What exactly needs to be implemented
- Key technical decisions and constraints
- What NOT to do (anti-patterns, forbidden approaches)

### 2. Acceptance Criteria
- Specific, testable criteria (not vague "it works")
- Include numeric thresholds where applicable
- Include edge cases

### 3. Expected Outputs (expected_outputs)
For each file the task should produce:
```yaml
expected_outputs:
  - path: src/module/file.py
    min_lines: 100  # Real estimate, not 1
    must_contain:
      - "class ClassName"  # Key classes/functions that MUST exist
      - "def method_name"
    must_not_contain:
      - "import forbidden_thing"  # Things that should NOT appear
```

### 4. Verify Script (verify_script)
Write a REAL verification script that tests the actual behavior, not just file existence.

BAD (do NOT do this):
```yaml
verify_script: test -f output.json
```

GOOD:
```yaml
verify_script: |
  cd {{{{workspace}}}} && python -c "
  from src.module import MyClass
  obj = MyClass()
  result = obj.compute(test_input)
  assert result is not None, 'compute returned None'
  assert len(result) > 0, 'empty result'
  print('Verification passed')
  "
```

For MPI/parallel tasks:
```yaml
verify_script: |
  cd {{{{workspace}}}} && source /etc/profile.d/modules.sh && module load mpi/openmpi-x86_64
  # Run with multiple ranks and verify results
  mpirun -np 2 python -c "
  from mpi4py import MPI
  from src.distributed import DistributedMPS
  comm = MPI.COMM_WORLD
  # ... actual test
  if comm.rank == 0:
    assert memory_2rank < memory_1rank, 'Memory should decrease'
    print('Multi-rank verification passed')
  "
```

### 5. Dependencies
- Correct ordering (don't depend on things that don't exist)
- Group logically (data structures → algorithms → verification → docs)

### 6. Priority
- critical: Core functionality that blocks everything else
- high: Important but not blocking
- medium: Nice to have
- low: Polish/cleanup

## Output Format

Output ONLY valid YAML (no markdown fences, no explanation outside YAML).
The YAML must have this structure:

name: Project Name
description: |
  Project description

defaults:
  priority: critical

tasks:
  - id: T001
    title: ...
    description: |
      ...
    depends_on: []
    acceptance_criteria:
      - ...
    expected_outputs:
      - path: ...
        min_lines: ...
        must_contain: [...]
    verify_script: |
      ...
    priority: critical
    labels: [...]

## Workspace

The project workspace is: {workspace_dir}

Generate the complete task YAML now. Be thorough — the verify_scripts are
the most important part. They must actually TEST the implementation, not
just check if files exist.
"""


async def generate_feature_plan(
    spec_content: str,
    workspace_dir: str,
    project_dir: Path,
    model: str = "claude-opus-4-5-20251101",
    enable_thinking: bool = True,
    thinking_budget: int = 16000,
    timeout_seconds: int = 600,
) -> tuple[bool, str, Optional[str]]:
    """
    Use Claude Opus to generate a detailed feature plan from a spec.

    Args:
        spec_content: Raw content of the application spec
        workspace_dir: Project workspace directory
        project_dir: Directory to run Claude in
        model: Model to use (default: Opus)
        enable_thinking: Enable extended thinking
        thinking_budget: Thinking token budget
        timeout_seconds: Timeout for planning

    Returns:
        Tuple of (success, generated_yaml_or_error, output_path)
    """
    prompt = PLANNING_PROMPT_TEMPLATE.format(
        spec_content=spec_content,
        workspace_dir=workspace_dir,
    )

    # Add instruction to write to file
    output_path = str(Path(workspace_dir) / "generated_spec.yaml")
    prompt += f"\n\nWrite the YAML output to: {output_path}\n"

    result = await execute_task_with_claude(
        project_dir=project_dir,
        prompt=prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        non_interactive=True,
        enable_thinking=enable_thinking,
        thinking_budget=thinking_budget,
    )

    if result.success:
        # Check if the file was written
        if Path(output_path).exists():
            content = Path(output_path).read_text()
            return True, content, output_path
        else:
            # Claude might have output the YAML directly
            return True, result.output, None
    else:
        return False, result.error or "Planning failed", None


async def enhance_existing_spec(
    spec_path: str,
    workspace_dir: str,
    project_dir: Path,
    model: str = "claude-opus-4-5-20251101",
    enable_thinking: bool = True,
    thinking_budget: int = 16000,
) -> tuple[bool, str]:
    """
    Use Claude Opus to enhance an existing spec with better verification.

    Reads the existing spec and generates improved:
    - verify_scripts (real tests, not file existence)
    - expected_outputs (with proper must_contain)
    - acceptance_criteria (specific and testable)

    Args:
        spec_path: Path to existing spec YAML
        workspace_dir: Project workspace directory
        project_dir: Directory to run Claude in
        model: Model to use
        enable_thinking: Enable extended thinking
        thinking_budget: Thinking token budget

    Returns:
        Tuple of (success, enhanced_yaml_or_error)
    """
    spec_content = Path(spec_path).read_text()

    prompt = f"""You are enhancing an existing project spec with better verification.

## Current Spec
{spec_content}

## Your Task

The spec above has tasks with weak or missing verify_scripts. Many just check
if a file exists (`test -f output.json`) which is useless — Claude can create
an empty file and "pass".

Rewrite the spec with the SAME tasks but BETTER:

1. **verify_script**: Must actually TEST the implementation works
   - For code: import and run it
   - For MPI: run with multiple ranks
   - For data: validate structure and values
   - NEVER just `test -f`

2. **expected_outputs**: Add must_contain patterns that prove real work
   - Classes/functions that must exist
   - Minimum line counts based on actual complexity

3. **acceptance_criteria**: Make them specific and measurable

Keep task IDs, titles, dependencies, and descriptions the same.
Only improve verification.

Write the enhanced YAML to: {workspace_dir}/enhanced_spec.yaml
"""

    result = await execute_task_with_claude(
        project_dir=project_dir,
        prompt=prompt,
        model=model,
        timeout_seconds=600,
        non_interactive=True,
        enable_thinking=enable_thinking,
        thinking_budget=thinking_budget,
    )

    enhanced_path = Path(workspace_dir) / "enhanced_spec.yaml"
    if result.success and enhanced_path.exists():
        return True, enhanced_path.read_text()
    elif result.success:
        return True, result.output
    else:
        return False, result.error or "Enhancement failed"
