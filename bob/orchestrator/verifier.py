"""
Output Verification (Ralph Wiggum Loop)
=======================================

Verifies that task outputs actually exist and meet requirements
before marking a task as complete.

"I'm helping!" - Ralph Wiggum
"""

import subprocess
from pathlib import Path
from typing import Optional

from bob.models.base import Task, ExpectedOutput


def count_lines(file_path: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def verify_output(output: ExpectedOutput, workspace: Path) -> tuple[bool, str]:
    """
    Verify a single expected output.
    
    Returns:
        Tuple of (success, message)
    """
    file_path = workspace / output.path
    
    # Check file exists
    if not file_path.exists():
        return False, f"Missing file: {output.path}"
    
    # Check minimum lines
    if output.min_lines > 0:
        actual_lines = count_lines(file_path)
        if actual_lines < output.min_lines:
            return False, f"File too short: {output.path} has {actual_lines} lines, need {output.min_lines}"
    
    # Check must_contain patterns
    if output.must_contain:
        try:
            content = file_path.read_text(encoding='utf-8')
            for pattern in output.must_contain:
                if pattern not in content:
                    return False, f"Missing pattern in {output.path}: '{pattern}'"
        except Exception as e:
            return False, f"Error reading {output.path}: {e}"
    
    # Check must_not_contain patterns
    if output.must_not_contain:
        try:
            content = file_path.read_text(encoding='utf-8')
            for pattern in output.must_not_contain:
                if pattern in content:
                    return False, f"Forbidden pattern in {output.path}: '{pattern}'"
        except Exception as e:
            return False, f"Error reading {output.path}: {e}"
    
    return True, f"Verified: {output.path}"


def run_verify_script(script: str, workspace: Path, timeout: int = 60) -> tuple[bool, str]:
    """
    Run a verification script.
    
    Returns:
        Tuple of (success, output/error)
    """
    try:
        result = subprocess.run(
            ['bash', '-c', script],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            return True, result.stdout.strip() if result.stdout else "Script passed"
        else:
            error = result.stderr.strip() if result.stderr else f"Exit code {result.returncode}"
            return False, f"Verify script failed: {error}"
    
    except subprocess.TimeoutExpired:
        return False, f"Verify script timed out after {timeout}s"
    except Exception as e:
        return False, f"Verify script error: {e}"


def verify_task_outputs(task: Task, workspace: Path) -> tuple[bool, str]:
    """
    Verify all expected outputs for a task.
    
    This is the "Ralph Wiggum loop" - we actually check that work was done
    before claiming victory.
    
    Args:
        task: Task to verify
        workspace: Project workspace directory
    
    Returns:
        Tuple of (all_passed, combined_message)
    """
    messages = []
    all_passed = True
    
    # Skip verification if no outputs defined
    if not task.expected_outputs and not task.verify_script:
        return True, "No verification criteria defined"
    
    # Verify each expected output
    for output in task.expected_outputs:
        passed, msg = verify_output(output, workspace)
        messages.append(msg)
        if not passed:
            all_passed = False
    
    # Run verify script if defined
    if task.verify_script:
        passed, msg = run_verify_script(task.verify_script, workspace)
        messages.append(msg)
        if not passed:
            all_passed = False
    
    combined = "\n".join(messages)
    
    if all_passed:
        return True, f"✅ All verifications passed:\n{combined}"
    else:
        return False, f"❌ Verification failed:\n{combined}"


def parse_expected_outputs(outputs_data: list) -> list[ExpectedOutput]:
    """Parse expected_outputs from spec YAML into ExpectedOutput objects."""
    result = []
    for item in outputs_data or []:
        if isinstance(item, str):
            # Simple string path
            result.append(ExpectedOutput(path=item))
        elif isinstance(item, dict):
            # Full specification
            result.append(ExpectedOutput(
                path=item.get('path', ''),
                min_lines=item.get('min_lines', 0),
                must_contain=item.get('must_contain', []),
                must_not_contain=item.get('must_not_contain', []),
            ))
    return result
