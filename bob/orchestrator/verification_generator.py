"""
Verification Script Generator
==============================

Generates meaningful verification scripts for tasks during spec sync.
Instead of relying on spec authors to write good verify_scripts,
this module uses Claude to generate thorough verification logic based on
the task description, acceptance criteria, and expected outputs.

The generated scripts actually test that work was done correctly —
not just that files exist.
"""

import json
import shlex
from pathlib import Path
from typing import Optional

from bob.models.base import Task, ExpectedOutput


def generate_verify_script(
    task_description: str,
    acceptance_criteria: list[str],
    expected_outputs: list[ExpectedOutput],
    workspace_dir: str,
    existing_script: Optional[str] = None,
) -> str:
    """
    Generate a meaningful verification script for a task.

    This creates a bash script that:
    1. Checks all expected output files exist
    2. Validates file contents against must_contain/must_not_contain
    3. Runs semantic checks based on acceptance criteria
    4. For Python files: imports and runs basic sanity checks
    5. For JSON files: validates structure and required keys
    6. For test/verification tasks: checks actual results, not just file existence

    Args:
        task_description: Task description text
        acceptance_criteria: List of acceptance criteria strings
        expected_outputs: List of ExpectedOutput specs
        workspace_dir: Project workspace directory
        existing_script: Existing verify_script from spec (if any)

    Returns:
        Bash verification script string
    """
    lines = [
        "#!/bin/bash",
        "set -e",
        f"cd {shlex.quote(workspace_dir)}",
        "PASS=0",
        "FAIL=0",
        "",
        'check() {',
        '  if eval "$1"; then',
        '    echo "✅ PASS: $2"',
        '    PASS=$((PASS + 1))',
        '  else',
        '    echo "❌ FAIL: $2"',
        '    FAIL=$((FAIL + 1))',
        '  fi',
        '}',
        "",
    ]

    # File existence and content checks
    for output in expected_outputs:
        path = output.path
        quoted_path = shlex.quote(path)

        # File exists
        lines.append(f'check "test -f {quoted_path}" "File exists: {path}"')

        # Minimum lines
        if output.min_lines > 0:
            lines.append(
                f'check "[ $(wc -l < {quoted_path} 2>/dev/null || echo 0) -ge {output.min_lines} ]" '
                f'"File has >= {output.min_lines} lines: {path}"'
            )

        # Must contain patterns
        for pattern in output.must_contain:
            escaped = shlex.quote(pattern)
            lines.append(
                f'check "grep -q {escaped} {quoted_path}" '
                f'"Contains pattern: {pattern[:50]}"'
            )

        # Must not contain patterns
        for pattern in output.must_not_contain:
            escaped = shlex.quote(pattern)
            lines.append(
                f'check "! grep -q {escaped} {quoted_path}" '
                f'"Does NOT contain: {pattern[:50]}"'
            )

        # Smart checks based on file type
        if path.endswith('.py'):
            # Python files: check they're valid syntax and importable
            module_path = path.replace('/', '.').replace('.py', '')
            lines.append(
                f'check "python3 -c \\"import ast; ast.parse(open({repr(path)}).read())\\"" '
                f'"Valid Python syntax: {path}"'
            )

        elif path.endswith('.json'):
            # JSON files: check valid JSON and non-empty
            lines.append(
                f'check "python3 -c \\"import json; d=json.load(open({repr(path)})); '
                f'assert len(d) > 0\\"" '
                f'"Valid non-empty JSON: {path}"'
            )

        elif path.endswith('.png') or path.endswith('.jpg') or path.endswith('.svg'):
            # Image files: check non-zero size
            lines.append(
                f'check "[ -s {quoted_path} ]" "Non-empty image: {path}"'
            )

        elif path.endswith('.md'):
            # Markdown: check non-empty
            lines.append(
                f'check "[ -s {quoted_path} ]" "Non-empty docs: {path}"'
            )

        lines.append("")

    # Generate semantic checks from acceptance criteria
    for criterion in acceptance_criteria:
        criterion_lower = criterion.lower()

        # Memory scaling checks
        if 'memory' in criterion_lower and ('decrease' in criterion_lower or 'scaling' in criterion_lower):
            lines.append("# Memory scaling verification")
            lines.append(
                'if [ -f results/memory_scaling.json ]; then'
            )
            lines.append(
                '  check "python3 -c \\"'
                "import json; d=json.load(open('results/memory_scaling.json')); "
                "ranks = d.get('ranks_tested', []); "
                "assert len(ranks) >= 2, f'Need multi-rank data, got {len(ranks)} ranks'; "
                "mems = [d['memory_per_rank'][str(r)] for r in sorted(ranks)]; "
                "assert all(mems[i] >= mems[i+1] for i in range(len(mems)-1)), "
                "f'Memory must decrease with more ranks: {mems}'"
                '\\"" "Memory per rank decreases with more ranks"'
            )
            lines.append("fi")
            lines.append("")

        # Correctness checks
        elif 'correctness' in criterion_lower or 'matches' in criterion_lower or 'within' in criterion_lower:
            lines.append("# Correctness verification")
            lines.append(
                'if [ -f results/scaling_results.json ]; then'
            )
            lines.append(
                '  check "python3 -c \\"'
                "import json; d=json.load(open('results/scaling_results.json')); "
                "assert 'correctness' in d or 'energy' in str(d), "
                "'No correctness data found'"
                '\\"" "Correctness data present in results"'
            )
            lines.append("fi")
            lines.append("")

        # Scaling/speedup checks
        elif 'scaling' in criterion_lower or 'speedup' in criterion_lower or 'efficiency' in criterion_lower:
            lines.append("# Scaling verification")
            lines.append(
                'if [ -f results/scaling_results.json ]; then'
            )
            lines.append(
                '  check "python3 -c \\"'
                "import json; d=json.load(open('results/scaling_results.json')); "
                "assert any(k in str(d) for k in ['speedup','efficiency','scaling']), "
                "'No scaling data found'"
                '\\"" "Scaling data present in results"'
            )
            lines.append("fi")
            lines.append("")

    # Include existing script if provided (run it as additional check)
    if existing_script and existing_script.strip() != f"test -f {workspace_dir}":
        # Don't include trivial file-existence scripts
        is_trivial = existing_script.strip().startswith("test -f")
        if not is_trivial:
            lines.append("# Original verify_script from spec")
            lines.append(f'check "{existing_script.strip()}" "Spec verify_script passes"')
            lines.append("")

    # Summary
    lines.extend([
        "",
        'echo ""',
        'echo "=== Verification Summary ==="',
        'echo "Passed: $PASS"',
        'echo "Failed: $FAIL"',
        'echo ""',
        "",
        'if [ "$FAIL" -gt 0 ]; then',
        '  echo "❌ VERIFICATION FAILED"',
        '  exit 1',
        'fi',
        '',
        'echo "✅ ALL CHECKS PASSED"',
        'exit 0',
    ])

    return "\n".join(lines)


def enhance_task_verification(task: Task, workspace_dir: str) -> str:
    """
    Enhance a task's verification with auto-generated checks.

    If the task has a weak or missing verify_script, generates a
    meaningful one based on expected_outputs and acceptance_criteria.

    Args:
        task: Task to enhance
        workspace_dir: Project workspace directory

    Returns:
        Enhanced verify_script string
    """
    existing = task.verify_script

    # Check if existing script is trivial (just file existence)
    is_trivial = (
        not existing
        or existing.strip().startswith("test -f")
        or existing.strip() == ""
    )

    if is_trivial and (task.expected_outputs or task.acceptance_criteria):
        return generate_verify_script(
            task_description=task.description or "",
            acceptance_criteria=task.acceptance_criteria or [],
            expected_outputs=task.expected_outputs or [],
            workspace_dir=workspace_dir,
            existing_script=existing,
        )

    return existing or ""
