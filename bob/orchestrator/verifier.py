"""
Output Verification
===================

Verifies that task outputs actually exist, meet requirements,
and aren't faked with mocks, stubs, or trivial implementations.
"""

import re
import subprocess
from pathlib import Path
from typing import Optional

from bob.models.base import Task, ExpectedOutput, VerificationTest


# ============================================================================
# Anti-gaming patterns
# ============================================================================

# Patterns in implementation files that indicate mocking/faking
MOCK_PATTERNS = [
    r'\bunittest\.mock\b',
    r'\bfrom\s+unittest\s+import\s+mock\b',
    r'\bMagicMock\b',
    r'\b@patch\b',
    r'\b@mock\b',
    r'\bmonkeypatch\b',
    r'\bmock\.patch\b',
    r'\bMock\(\)',
]

# Patterns that indicate stub/placeholder implementations
STUB_PATTERNS = [
    r'class\s+\w+:\s*\n\s+pass\s*$',          # class Foo:\n    pass
    r'def\s+\w+\([^)]*\):\s*\n\s+pass\s*$',    # def foo(): pass
    r'def\s+\w+\([^)]*\):\s*\n\s+return None\s*$',  # def foo(): return None
    r'def\s+\w+\([^)]*\):\s*\n\s+\.\.\.\s*$',  # def foo(): ...
    r'raise\s+NotImplementedError',              # raise NotImplementedError
    r'#\s*TODO',                                  # TODO comments
    r'#\s*FIXME',                                 # FIXME comments
    r'#\s*STUB',                                  # STUB markers
    r'#\s*PLACEHOLDER',                           # PLACEHOLDER markers
]

# Trivial test patterns that always pass
TRIVIAL_TEST_PATTERNS = [
    r'assert\s+True\b',
    r'assert\s+1\b',
    r'assert\s+not\s+False\b',
    r'self\.assertTrue\(True\)',
    r'assertEqual\(1,\s*1\)',
]


def count_lines(file_path: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def count_real_code_lines(file_path: Path) -> int:
    """Count lines that are actual code (not blank, comments, or docstrings)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return 0
    
    real_lines = 0
    in_docstring = False
    docstring_char = None
    
    for line in lines:
        stripped = line.strip()
        
        # Skip blank lines
        if not stripped:
            continue
        
        # Track docstrings
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                docstring_char = stripped[:3]
                if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                    # Single-line docstring
                    continue
                in_docstring = True
                continue
            # Skip comments
            if stripped.startswith('#'):
                continue
            real_lines += 1
        else:
            if docstring_char in stripped:
                in_docstring = False
            continue
    
    return real_lines


def detect_mocks(file_path: Path) -> list[str]:
    """Detect mock/patch usage in a file. Returns list of violations."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []
    
    violations = []
    for pattern in MOCK_PATTERNS:
        matches = re.findall(pattern, content, re.MULTILINE)
        if matches:
            violations.append(f"Mock/patch detected in {file_path.name}: '{matches[0]}'")
    
    return violations


def detect_stubs(file_path: Path) -> list[str]:
    """Detect stub/placeholder implementations. Returns list of violations."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []
    
    violations = []
    for pattern in STUB_PATTERNS:
        matches = re.findall(pattern, content, re.MULTILINE)
        if matches:
            # NotImplementedError is OK if it's in a small minority of methods
            if 'NotImplementedError' in pattern:
                count = len(matches)
                # Count total methods
                total_methods = len(re.findall(r'def\s+\w+', content))
                if total_methods > 0 and count / total_methods > 0.3:
                    violations.append(
                        f"Too many NotImplementedError in {file_path.name}: "
                        f"{count}/{total_methods} methods ({count/total_methods:.0%})"
                    )
            else:
                violations.append(f"Stub/placeholder in {file_path.name}: '{matches[0].strip()}'")
    
    return violations


def detect_trivial_tests(file_path: Path) -> list[str]:
    """Detect trivial test patterns that always pass."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []
    
    violations = []
    for pattern in TRIVIAL_TEST_PATTERNS:
        matches = re.findall(pattern, content, re.MULTILINE)
        if matches:
            violations.append(f"Trivial test in {file_path.name}: '{matches[0]}'")
    
    return violations


def check_class_not_empty(content: str, class_name: str) -> tuple[bool, str]:
    """
    Verify a class has real methods with real implementations,
    not just 'pass' or empty bodies.
    """
    # Find the class definition
    pattern = rf'class\s+{re.escape(class_name)}\b.*?(?=\nclass\s|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return False, f"Class '{class_name}' not found"
    
    class_body = match.group()
    
    # Count methods with real bodies (more than just pass/...)
    methods = re.findall(r'def\s+(\w+)\s*\(', class_body)
    if len(methods) < 2:
        return False, f"Class '{class_name}' has only {len(methods)} methods — likely a stub"
    
    # Check that methods have actual code (not just pass/return None)
    stub_methods = 0
    for method in methods:
        method_pattern = rf'def\s+{re.escape(method)}\s*\([^)]*\).*?(?=\n    def\s|\n    @|\nclass\s|\Z)'
        method_match = re.search(method_pattern, class_body, re.DOTALL)
        if method_match:
            body = method_match.group()
            body_lines = [l.strip() for l in body.split('\n')[1:] if l.strip() and not l.strip().startswith('#') and not l.strip().startswith('"""') and not l.strip().startswith("'''")]
            if all(l in ('pass', '...', 'return None', 'return', 'raise NotImplementedError', 'raise NotImplementedError()') for l in body_lines):
                stub_methods += 1
    
    if stub_methods > 0 and len(methods) > 0:
        ratio = stub_methods / len(methods)
        if ratio > 0.3:
            return False, f"Class '{class_name}' has {stub_methods}/{len(methods)} stub methods ({ratio:.0%})"
    
    return True, f"Class '{class_name}' looks real ({len(methods)} methods)"


def verify_output(output: ExpectedOutput, workspace: Path) -> tuple[bool, str]:
    """
    Verify a single expected output.
    
    Checks:
    1. File exists
    2. Minimum line count (real code lines, not blanks/comments)
    3. Must-contain patterns present
    4. Must-not-contain patterns absent
    5. No mock/patch imports in implementation files
    6. No stub/placeholder implementations
    7. Classes in must_contain are real (not empty stubs)
    
    Returns:
        Tuple of (success, message)
    """
    file_path = workspace / output.path
    
    # Check file exists
    if not file_path.exists():
        return False, f"Missing file: {output.path}"
    
    # Check minimum lines (using real code lines, not just any non-empty line)
    if output.min_lines > 0:
        actual_lines = count_lines(file_path)
        real_lines = count_real_code_lines(file_path)
        if actual_lines < output.min_lines:
            return False, f"File too short: {output.path} has {actual_lines} lines (real code: {real_lines}), need {output.min_lines}"
    
    # Check must_contain patterns
    content = None
    if output.must_contain or output.must_not_contain:
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            return False, f"Error reading {output.path}: {e}"
    
    if output.must_contain and content is not None:
        for pattern in output.must_contain:
            if pattern not in content:
                return False, f"Missing pattern in {output.path}: '{pattern}'"
            
            # If the pattern defines a class, verify it's not a stub
            class_match = re.match(r'class\s+(\w+)', pattern)
            if class_match:
                class_name = class_match.group(1)
                is_real, class_msg = check_class_not_empty(content, class_name)
                if not is_real:
                    return False, f"Anti-gaming: {class_msg}"
    
    # Check must_not_contain patterns
    if output.must_not_contain and content is not None:
        for pattern in output.must_not_contain:
            if pattern in content:
                return False, f"Forbidden pattern in {output.path}: '{pattern}'"
    
    # Anti-gaming: Check for mocks in .py implementation files
    if file_path.suffix == '.py':
        mock_violations = detect_mocks(file_path)
        if mock_violations:
            return False, f"Anti-gaming: {'; '.join(mock_violations)}"
        
        stub_violations = detect_stubs(file_path)
        if stub_violations:
            return False, f"Anti-gaming: {'; '.join(stub_violations)}"
    
    return True, f"Verified: {output.path}"


def check_for_gaming_in_workspace(workspace: Path, task: Task) -> list[str]:
    """
    Check if the agent tried to game the verification by modifying
    the environment rather than writing real code.
    
    Detects:
    - conftest.py files that mock imports
    - __init__.py files that fake modules
    - sitecustomize.py or .pth files that redirect imports
    - Test files that always pass
    """
    violations = []
    
    # Check for conftest.py that patches/mocks
    for conftest in workspace.rglob('conftest.py'):
        mock_hits = detect_mocks(conftest)
        if mock_hits:
            violations.append(f"Gaming: conftest.py contains mocks: {conftest}")
    
    # Check for sitecustomize.py (import hook gaming)
    sitecustomize = workspace / 'sitecustomize.py'
    if sitecustomize.exists():
        violations.append(f"Gaming: sitecustomize.py found — possible import hook")
    
    # Check for .pth files (module path gaming)
    for pth in workspace.rglob('*.pth'):
        violations.append(f"Gaming: .pth file found: {pth}")
    
    return violations


def run_verify_script(script: str, workspace: Path, timeout: int = 120) -> tuple[bool, str]:
    """
    Run a verification script.
    
    The script is defined in the spec (stored in DB), NOT in the workspace.
    Claude cannot edit it. But Claude could game the environment to make
    it pass — we check for that separately.
    
    Returns:
        Tuple of (success, output/error)
    """
    try:
        # Run with a clean-ish environment to prevent LD_PRELOAD gaming
        env_overrides = {
            'LD_PRELOAD': '',  # Prevent shared library injection
        }
        
        import os
        env = os.environ.copy()
        env.update(env_overrides)
        
        result = subprocess.run(
            ['bash', '-c', script],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        
        if result.returncode == 0:
            output = result.stdout.strip() if result.stdout else ""
            
            # Anti-gaming: verify the script produced meaningful output
            # A trivial pass would produce no output or just "OK"
            # Real verification should print something about what was verified
            if not output:
                return False, (
                    "Verify script passed but produced no output. "
                    "Real verification should print what was verified."
                )
            
            return True, output
        else:
            error = result.stderr.strip() if result.stderr else f"Exit code {result.returncode}"
            stdout = result.stdout.strip() if result.stdout else ""
            # Include both stdout and stderr for debugging context
            full_output = f"Verify script failed: {error}"
            if stdout:
                full_output += f"\nStdout: {stdout}"
            return False, full_output
    
    except subprocess.TimeoutExpired:
        return False, f"Verify script timed out after {timeout}s"
    except Exception as e:
        return False, f"Verify script error: {e}"


def run_verification_test(test: VerificationTest, workspace: Path) -> tuple[bool, str]:
    """
    Run a single verification test (numerical, algorithmic, or convergence).

    These tests are defined in the spec and stored in the DB. The coding
    agent cannot modify them — it must write code that actually passes.

    Returns:
        Tuple of (success, message)
    """
    try:
        import os
        env = os.environ.copy()
        env['LD_PRELOAD'] = ''  # prevent injection

        result = subprocess.run(
            ['bash', '-c', test.command],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=test.timeout,
            env=env,
        )

        if result.returncode == test.expected_exit_code:
            stdout = result.stdout.strip()
            if not stdout:
                # Tests must produce output explaining what was verified
                return False, (
                    f"[{test.name}] Passed but produced no output. "
                    "Tests must print what was verified."
                )
            return True, f"[{test.name}] PASS: {stdout[-200:]}"
        else:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            detail = stderr if stderr else stdout if stdout else f"exit code {result.returncode}"
            return False, f"[{test.name}] FAIL: {detail[-300:]}"

    except subprocess.TimeoutExpired:
        return False, f"[{test.name}] TIMEOUT after {test.timeout}s"
    except Exception as e:
        return False, f"[{test.name}] ERROR: {e}"


def run_verification_suite(
    suite_name: str,
    tests: list[VerificationTest],
    workspace: Path,
) -> tuple[bool, list[str]]:
    """
    Run a suite of verification tests (numerical, algorithmic, or convergence).

    All tests in the suite must pass for the suite to pass.

    Returns:
        Tuple of (all_passed, list_of_messages)
    """
    if not tests:
        return True, []

    messages = [f"--- {suite_name} ({len(tests)} tests) ---"]
    all_passed = True

    for test in tests:
        passed, msg = run_verification_test(test, workspace)
        messages.append(msg)
        if not passed:
            all_passed = False

    return all_passed, messages


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
    
    # Warn when no verification criteria are defined.
    # For critical/high priority tasks, this is a failure — specs MUST
    # define expected_outputs or verify_script for important tasks.
    if not task.expected_outputs and not task.verify_script:
        if task.priority in ("critical", "high"):
            return False, (
                f"No verification criteria defined for {task.priority}-priority task "
                f"'{task.spec_id}'. Add expected_outputs or verify_script to the spec."
            )
        return True, "⚠️ No verification criteria defined — skipping verification"
    
    # Anti-gaming: Check for environment manipulation
    gaming_violations = check_for_gaming_in_workspace(workspace, task)
    if gaming_violations:
        for v in gaming_violations:
            messages.append(v)
        all_passed = False
    
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

    # --- Semantic verification layers ---
    # These run AFTER structural checks pass. They are defined in the spec
    # and stored in the DB — the coding agent cannot modify them.

    # Layer 1: Numerical tests (known answers, tight tolerances)
    if task.numerical_tests:
        passed, suite_msgs = run_verification_suite(
            "Numerical Tests", task.numerical_tests, workspace
        )
        messages.extend(suite_msgs)
        if not passed:
            all_passed = False

    # Layer 2: Algorithmic tests (method verification, differential tests)
    if task.algorithmic_tests:
        passed, suite_msgs = run_verification_suite(
            "Algorithmic Tests", task.algorithmic_tests, workspace
        )
        messages.extend(suite_msgs)
        if not passed:
            all_passed = False

    # Layer 3: Convergence tests (process behavior, parameter sensitivity)
    if task.convergence_tests:
        passed, suite_msgs = run_verification_suite(
            "Convergence Tests", task.convergence_tests, workspace
        )
        messages.extend(suite_msgs)
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
