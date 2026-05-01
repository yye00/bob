"""Superpowers skill integration for Bob3 (F113).

Integrates four Superpowers skills into the Bob3 workflow:

1. systematic-debugging - Already integrated in F106 (RCA system)
2. test-driven-development (TDD) - Write tests before implementation
3. verification-before-completion - Final checks before marking complete
4. subagent-driven-development - Parallel sub-agent tasks for complex features

This module provides:
- TDD mode prompt generation for feature execution
- Verification-before-completion checklist runner
- Sub-agent task splitting for parallel execution
- Orientation prompt sections documenting when each skill is used
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import sys

from bob3.ast_checks import verify_no_stubs_or_mocks
from bob3.enhanced_verification import (
    _run_with_pgroup_timeout,
    validate_acceptance_criteria,
    validate_integration,
)

logger = logging.getLogger(__name__)


DEFAULT_TEST_RUN_TIMEOUT_S = 300


def _test_run_timeout() -> int:
    """Return the per-run pytest timeout in seconds (BOB3_TEST_RUN_TIMEOUT)."""
    raw = os.environ.get("BOB3_TEST_RUN_TIMEOUT")
    if not raw:
        return DEFAULT_TEST_RUN_TIMEOUT_S
    try:
        value = int(raw)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return DEFAULT_TEST_RUN_TIMEOUT_S


def _tail(text: str, limit: int = 800) -> str:
    """Return the last ``limit`` characters of ``text`` (or all of it if shorter)."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return "..." + text[-limit:]


def _parse_pytest_counts(stdout: str) -> tuple[int, int]:
    """Parse ``N passed`` / ``N failed`` counts from pytest stdout.

    Returns a tuple ``(passed, failed)``. Missing values default to 0.
    """
    passed = 0
    failed = 0
    if not stdout:
        return passed, failed
    # pytest prints summary lines like ``=== 5 passed in 0.12s ===`` or
    # ``=== 1 failed, 4 passed in 0.12s ===``. Use regex per-token.
    passed_match = re.search(r"(\d+)\s+passed", stdout)
    if passed_match:
        try:
            passed = int(passed_match.group(1))
        except ValueError:
            passed = 0
    failed_match = re.search(r"(\d+)\s+failed", stdout)
    if failed_match:
        try:
            failed = int(failed_match.group(1))
        except ValueError:
            failed = 0
    return passed, failed


def _check_tests_pass(workspace: pathlib.Path, src_dir: str, test_dir: str) -> dict:
    """Run pytest in the workspace and return a verification check entry.

    Pass criteria:
        * exit code == 0
        * at least one test reported as passed in stdout

    Behavior:
        * Workspace doesn't exist -> warning (not failure).
        * No Python sources in src/ -> warning (non-Python project).
        * No test directory found -> warning ("no test directory found").
        * Test directory present but no test files collected by pytest ->
          treated as a hard failure (unless pytest itself isn't installed).
        * Python or pytest unavailable -> warning.
        * Timeout -> hard failure.
        * Failures parsed from output -> hard failure with tail of output.
    """
    check_name = "tests_pass"

    # Workspace existence check (non-fatal)
    if not workspace.exists() or not workspace.is_dir():
        return {
            "name": check_name,
            "passed": True,
            "severity": "warning",
            "details": f"workspace does not exist: {workspace}",
        }

    # Recursion guard: if the workspace resolves to bob3's own repository
    # tree (during self-development), running pytest there would re-enter
    # bob3's own test suite and may re-initialize memory backends or
    # contaminate parent state. Skip with a warning instead.
    #
    # parents[2] is the bob3 repo root, e.g. for
    #   /home/.../bob3.1/src/bob3/__init__.py
    # parents[0] = src/bob3, parents[1] = src/, parents[2] = bob3.1 (repo root).
    # Using parents[1] (src/) would incorrectly skip any unrelated project
    # whose workspace happened to be its own ``src/`` directory or a child
    # of bob3's ``src/`` (e.g. ``bob3/src/another_thing/``).
    try:
        import bob3  # local import to avoid circulars during module load.
        bob3_root = pathlib.Path(bob3.__file__).resolve().parents[2]  # repo root
        workspace_resolved = pathlib.Path(workspace).resolve()
        if workspace_resolved == bob3_root or bob3_root in workspace_resolved.parents:
            return {
                "name": check_name,
                "passed": True,
                "severity": "warning",
                "details": "Skipped: workspace is bob3 itself (self-test recursion guard)",
            }
    except Exception:
        # Defensive: if anything goes wrong in the guard we don't want to
        # block normal verification.
        logger.debug("self-test recursion guard check skipped", exc_info=True)

    # Skip for non-Python projects: no .py files under src/ means we shouldn't
    # gate the verification on pytest. Return a warning instead of failing.
    src_path = workspace / src_dir
    has_python_sources = False
    if src_path.exists() and src_path.is_dir():
        for f in src_path.rglob("*.py"):
            if "__pycache__" in str(f):
                continue
            has_python_sources = True
            break
    if not has_python_sources:
        return {
            "name": check_name,
            "passed": True,
            "severity": "warning",
            "details": "no Python source files found under src/; pytest run skipped",
        }

    # Locate test directory: prefer the configured ``test_dir`` if it exists,
    # then fall back to ``tests``. If neither is present, return a warning.
    candidate_dirs: list[pathlib.Path] = []
    primary = workspace / test_dir
    candidate_dirs.append(primary)
    if test_dir != "tests":
        candidate_dirs.append(workspace / "tests")
    target_dir: pathlib.Path | None = None
    for c in candidate_dirs:
        if c.exists() and c.is_dir():
            target_dir = c
            break
    if target_dir is None:
        return {
            "name": check_name,
            "passed": True,
            "severity": "warning",
            "details": "no test directory found",
        }

    # Run pytest as a subprocess (one of the legitimate subprocess uses in bob3).
    timeout_s = _test_run_timeout()
    target_rel = target_dir.relative_to(workspace).as_posix()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target_rel,
        "--tb=line",
        "-q",
        "--maxfail=20",
        # Force plain output. Without this, FORCE_COLOR=1 / PY_COLORS=1 or
        # third-party plugins (pytest-sugar, anyio, ...) emit ANSI escape
        # codes between the digit and ``passed`` token, breaking the
        # ``\d+\s+passed`` summary regex below.
        "--color=no",
    ]
    try:
        stdout, stderr, returncode, timed_out = _run_with_pgroup_timeout(
            cmd,
            cwd=str(workspace),
            timeout_s=timeout_s,
        )
    except FileNotFoundError as e:
        # Python interpreter not on PATH (extremely unlikely but defensive).
        return {
            "name": check_name,
            "passed": True,
            "severity": "warning",
            "details": f"python interpreter not available: {e}",
        }
    except (OSError, ValueError) as e:
        return {
            "name": check_name,
            "passed": True,
            "severity": "warning",
            "details": f"pytest invocation failed ({type(e).__name__}): {e}",
        }

    if timed_out:
        details = (
            f"pytest timed out after {timeout_s}s; "
            f"stdout_tail={_tail(stdout, 400)} "
            f"stderr_tail={_tail(stderr, 400)}"
        )
        return {
            "name": check_name,
            "passed": False,
            "severity": "error",
            "details": details,
        }

    # Detect "pytest not installed". When ``python -m pytest`` is run without
    # pytest installed, Python prints something like
    # ``No module named pytest`` to stderr and exits with a non-zero code.
    if "No module named pytest" in stderr or "No module named 'pytest'" in stderr:
        return {
            "name": check_name,
            "passed": True,
            "severity": "warning",
            "details": "pytest is not installed; tests_pass check skipped",
        }

    passed_count, failed_count = _parse_pytest_counts(stdout)

    # Pytest exit codes: 0 = ok, 1 = failures, 2 = interrupted, 3 = internal,
    # 4 = usage, 5 = no tests collected.
    if returncode == 0 and passed_count > 0:
        return {
            "name": check_name,
            "passed": True,
            "details": f"pytest passed: {passed_count} test(s) in {target_rel}",
        }

    # Hard failure: capture the tail of stdout/stderr for diagnostics.
    if returncode == 5 or (returncode == 0 and passed_count == 0):
        reason = "no tests collected (0 passed)"
    elif failed_count > 0:
        reason = f"{failed_count} failed, {passed_count} passed"
    else:
        reason = f"pytest exit={returncode}"

    details = (
        f"pytest failed in {target_rel}: {reason}; "
        f"stdout_tail={_tail(stdout, 400)} "
        f"stderr_tail={_tail(stderr, 400)}"
    )
    return {
        "name": check_name,
        "passed": False,
        "severity": "error",
        "details": details,
    }


# ============================================================
# TDD Mode (Test-Driven Development)
# ============================================================

TDD_PROMPT_SECTION = """\
## TDD Mode: Write Tests BEFORE Implementation

You MUST follow the red-green-refactor cycle:

### Step 1: RED - Write Failing Tests First
- Read the acceptance criteria carefully
- Write test file(s) that define expected behavior
- Run the tests and confirm they FAIL (this proves they test something real)
- Tests must contain real assertions, not just `assert True`

### Step 2: GREEN - Write Minimum Implementation
- Write the minimum code needed to make all tests pass
- Do NOT write more code than necessary to pass the tests
- Run tests again and confirm they PASS

### Step 3: REFACTOR - Clean Up
- Clean up code while keeping tests green
- Remove any duplication
- Run tests one final time to confirm they still pass

### TDD Rules:
- NEVER write implementation code before its corresponding test
- Each test must assert specific, meaningful behavior
- Tests must fail before implementation (proves they test real things)
- Implementation should be driven by what the tests require
"""


def get_tdd_prompt() -> str:
    """Return the TDD mode prompt section for sub-agent orientation.

    This prompt instructs the sub-agent to follow the red-green-refactor
    cycle when implementing features.

    Returns:
        A prompt string with TDD instructions.
    """
    return TDD_PROMPT_SECTION


def should_use_tdd(
    *,
    acceptance_criteria: str | None = None,
    description: str | None = None,
    tdd_mode_override: bool | None = None,
) -> bool:
    """Determine if TDD mode should be used for a feature.

    TDD is recommended when:
    - Feature explicitly sets tdd_mode=True in YAML (highest priority)
    - Feature has explicit acceptance criteria (clear what to test)
    - Feature description mentions tests, validation, or new modules
    - Feature is not a documentation-only or config-only change

    Args:
        acceptance_criteria: Feature acceptance criteria string.
        description: Feature description string.
        tdd_mode_override: Explicit TDD mode setting from feature (True/False/None).
                          None means auto-detect based on heuristics.

    Returns:
        True if TDD mode should be enabled.
    """
    # PRIORITY 1: Check explicit override from feature.tdd_mode field
    if tdd_mode_override is not None:
        return tdd_mode_override

    # PRIORITY 2: Auto-detect based on heuristics (legacy behavior)
    # If there are acceptance criteria, TDD is appropriate
    if acceptance_criteria and len(acceptance_criteria.strip()) > 10:
        return True

    # Check description for indicators
    if description:
        desc_lower = description.lower()
        tdd_indicators = [
            "implement", "create", "add", "build", "write",
            "new module", "new function", "new class",
            "test", "validate", "verify",
        ]
        for indicator in tdd_indicators:
            if indicator in desc_lower:
                return True

    return False


# ============================================================
# Verification Before Completion
# ============================================================

VERIFICATION_PROMPT_SECTION = """\
## Verification Before Completion Checklist

Before marking this feature as complete, you MUST verify ALL of these:

1. **Files exist:** All expected source and test files are present
2. **No stubs:** No `pass`, `...`, `raise NotImplementedError`, or `# TODO` in source
3. **No mocks in production:** Mock imports only in test files, never in src/
4. **Tests pass:** Run `python -m pytest tests/ -v` and confirm all tests pass
5. **Real tests:** Tests contain actual assertions (not just `assert True`)
6. **No regressions:** Existing tests still pass after your changes

If ANY check fails, fix the issue before claiming completion.
Do NOT mark the feature as complete if any verification step fails.
"""


def get_verification_prompt() -> str:
    """Return the verification-before-completion prompt section.

    This prompt instructs the sub-agent to run a verification checklist
    before claiming a feature is complete.

    Returns:
        A prompt string with verification instructions.
    """
    return VERIFICATION_PROMPT_SECTION


def run_verification_checklist(
    *,
    workspace: str,
    src_dir: str = "src",
    test_dir: str = "tests",
    acceptance_criteria: str | None = None,
    feature_description: str | None = None,
) -> dict:
    """Run the verification-before-completion checklist on the workspace.

    Checks:
    1. Source files exist (auto-detects project type)
    2. Test files exist (auto-detects test location)
    3. No stub functions in source files (Python only, via AST analysis)
    4. No mock imports in source files (Python only, via AST analysis)
    5. Code changes were made (not just existing files)
    6. Acceptance criteria validation (if provided)

    This is a static analysis check. Running tests (pytest) is left to the
    sub-agent since it requires process execution.

    Args:
        workspace: Path to the project workspace directory.
        src_dir: Relative path to source directory (default: "src", auto-detected if not found).
        test_dir: Relative path to test directory (default: "tests", auto-detected if not found).
        acceptance_criteria: Feature acceptance criteria for validation.
        feature_description: Feature description for context.

    Returns:
        Dict with keys:
        - passed: bool (True if all static checks pass)
        - checks: list of dicts, each with name/passed/details
        - summary: str (human-readable summary)
    """
    ws = pathlib.Path(workspace)
    checks: list[dict] = []

    # If the workspace doesn't exist, skip verification gracefully
    if not ws.exists():
        return {
            "passed": True,
            "checks": [],
            "summary": "Verification skipped: workspace directory does not exist",
        }

    # Auto-detect project type and source locations
    src_path = ws / src_dir
    is_python_project = src_path.exists()
    is_opm_project = (ws / "opm-simulators").exists()
    is_cmake_project = (ws / "CMakeLists.txt").exists()
    has_known_project_type = is_python_project or is_opm_project or is_cmake_project

    # Check 1: Source files exist (adaptive based on project type)
    src_files = []
    src_locations_checked = []

    if is_python_project:
        # Python project: check src/ for .py files
        src_files = list(src_path.rglob("*.py")) if src_path.exists() else []
        src_files = [f for f in src_files if f.name != "__init__.py" and "__pycache__" not in str(f)]
        src_locations_checked.append(f"{src_dir}/ (Python)")

    if is_opm_project:
        # OPM Flow project: check opm-simulators/opm/ for .hpp and .cpp files
        opm_src_paths = [
            ws / "opm-simulators" / "opm" / "simulators",
            ws / "opm-simulators" / "opm",
        ]
        for opm_path in opm_src_paths:
            if opm_path.exists():
                cpp_files = list(opm_path.rglob("*.cpp")) + list(opm_path.rglob("*.hpp"))
                src_files.extend(cpp_files)
                src_locations_checked.append(f"{opm_path.relative_to(ws)}/ (C++)")

    if is_cmake_project and not is_opm_project:
        # Generic CMake project: check for .cpp, .hpp, .h, .c files
        src_files = list(ws.rglob("*.cpp")) + list(ws.rglob("*.hpp")) + list(ws.rglob("*.h")) + list(ws.rglob("*.c"))
        # Exclude build directories
        src_files = [f for f in src_files if "build" not in str(f) and ".git" not in str(f)]
        src_locations_checked.append("CMake project (C/C++)")

    _src_check = {
        "name": "source_files_exist",
        "passed": len(src_files) > 0,
        "details": f"Found {len(src_files)} source file(s) in {', '.join(src_locations_checked) if src_locations_checked else 'workspace'}",
    }
    if not has_known_project_type:
        _src_check["severity"] = "warning"
    checks.append(_src_check)

    # Check 2: Test files exist (adaptive based on project type)
    test_files = []
    test_locations_checked = []

    if is_python_project:
        # Python project: check tests/ for test_*.py files
        test_path = ws / test_dir
        test_files = list(test_path.rglob("test_*.py")) if test_path.exists() else []
        test_files = [f for f in test_files if "__pycache__" not in str(f)]
        test_locations_checked.append(f"{test_dir}/ (pytest)")

    if is_cmake_project or is_opm_project:
        # CMake/OPM project: check for tests/ or test/ directories with any test files
        for test_dirname in ["tests", "test", "Testing"]:
            test_path = ws / test_dirname
            if test_path.exists():
                cmake_tests = list(test_path.rglob("*test*.cpp")) + list(test_path.rglob("*Test*.cpp"))
                test_files.extend(cmake_tests)
                test_locations_checked.append(f"{test_dirname}/ (CMake)")

    # For non-test projects (e.g., benchmark execution), test files are optional
    test_check_required = is_python_project or len(test_files) > 0

    checks.append({
        "name": "test_files_exist",
        "passed": len(test_files) > 0 if test_check_required else True,
        "details": (
            f"Found {len(test_files)} test file(s) in {', '.join(test_locations_checked) if test_locations_checked else 'workspace'}"
            if test_check_required
            else "Tests not required for this project type"
        ),
    })

    # Check 3 & 4: No stubs or mocks in source files (Python only, AST-based)
    if is_python_project:
        sources: dict[str, str] = {}
        python_src_files = [f for f in src_files if f.suffix == ".py"]
        for sf in python_src_files:
            try:
                rel_path = str(sf.relative_to(ws))
                sources[rel_path] = sf.read_text()
            except Exception:
                logger.debug("Could not read %s for verification", sf)

        ast_result = verify_no_stubs_or_mocks(sources)
        checks.append({
            "name": "no_stubs_in_source",
            "passed": len(ast_result["stub_findings"]) == 0,
            "details": (
                f"Found {len(ast_result['stub_findings'])} stub function(s)"
                if ast_result["stub_findings"]
                else "No stub functions detected"
            ),
        })
        checks.append({
            "name": "no_mocks_in_source",
            "passed": len(ast_result["mock_findings"]) == 0,
            "details": (
                f"Found {len(ast_result['mock_findings'])} mock usage(s) in source"
                if ast_result["mock_findings"]
                else "No mock imports in source files"
            ),
        })
    else:
        # Non-Python projects: skip AST checks
        checks.append({
            "name": "no_stubs_in_source",
            "passed": True,
            "details": "Stub detection skipped (non-Python project)",
        })
        checks.append({
            "name": "no_mocks_in_source",
            "passed": True,
            "details": "Mock detection skipped (non-Python project)",
        })

    # Check 4b: Run the test suite. This is the always-on default that
    # actually executes pytest in the workspace, so a sub-agent that only
    # writes always-passing tests still gets caught when the suite reports
    # zero meaningful results or fails. Placed after the static
    # no_stubs_in_source/no_mocks_in_source checks and before the acceptance
    # criteria checks (per F113 design).
    tests_pass_check = _check_tests_pass(ws, src_dir, test_dir)
    checks.append(tests_pass_check)

    # Check 5: Recent code changes (verify work was actually done)
    # Look for files modified in the last hour (feature execution time)
    import time
    one_hour_ago = time.time() - 3600
    recent_src_files = []
    recent_test_files = []

    for f in src_files:
        try:
            if f.stat().st_mtime > one_hour_ago:
                recent_src_files.append(f)
        except Exception:
            pass

    for f in test_files:
        try:
            if f.stat().st_mtime > one_hour_ago:
                recent_test_files.append(f)
        except Exception:
            pass

    recent_files_found = len(recent_src_files) + len(recent_test_files) > 0
    _changes_check = {
        "name": "code_changes_made",
        "passed": recent_files_found,
        "details": (
            f"Found {len(recent_src_files)} recently modified source file(s) and "
            f"{len(recent_test_files)} recently modified test file(s)"
            if recent_files_found
            else "No recently modified files found - feature may not have been implemented"
        ),
    }
    if not has_known_project_type:
        _changes_check["severity"] = "warning"
    checks.append(_changes_check)

    # Check 6: Acceptance criteria validation (enhanced, via enhanced_verification)
    if acceptance_criteria:
        ac_passed, ac_details = validate_acceptance_criteria(
            workspace=ws,
            acceptance_criteria=acceptance_criteria,
            is_python_project=is_python_project,
            is_cmake_project=is_cmake_project,
            is_opm_project=is_opm_project,
        )
        checks.append({
            "name": "acceptance_criteria_met",
            "passed": ac_passed,
            "details": ac_details,
        })

    # Check 7: Integration verification for "integrate" features (ENHANCED)
    if feature_description and "integrate" in feature_description.lower():
        integration_passed, integration_details = validate_integration(
            workspace=ws,
            feature_description=feature_description,
            src_files=src_files,
            is_python_project=is_python_project,
        )
        checks.append({
            "name": "integration_code_exists",
            "passed": integration_passed,
            "details": integration_details,
        })
    # Overall result: only non-warning checks are hard failures
    all_passed = all(
        c["passed"] for c in checks if c.get("severity") != "warning"
    )

    # Build summary
    summary_parts = []
    for c in checks:
        if c["passed"]:
            status = "PASS"
        elif c.get("severity") == "warning":
            status = "WARN"
        else:
            status = "FAIL"
        summary_parts.append(f"  [{status}] {c['name']}: {c['details']}")

    summary = "Verification checklist:\n" + "\n".join(summary_parts)
    if all_passed:
        warnings = [c["name"] for c in checks if not c["passed"] and c.get("severity") == "warning"]
        if warnings:
            summary += f"\n\nAll hard checks passed. Warnings: {', '.join(warnings)}"
        else:
            summary += "\n\nAll verification checks passed."
    else:
        failed = [c["name"] for c in checks if not c["passed"] and c.get("severity") != "warning"]
        summary += f"\n\nFailed checks: {', '.join(failed)}"

    return {
        "passed": all_passed,
        "checks": checks,
        "summary": summary,
    }


# ============================================================
# Sub-Agent Driven Development
# ============================================================

SUBAGENT_PROMPT_SECTION = """\
## Sub-Agent Driven Development

This feature has been identified as suitable for parallel sub-agent work.

When you encounter independent sub-tasks that can be worked on in parallel:

1. **Identify independent tasks** - tasks with no shared file dependencies
2. **Group dependent tasks** - tasks that must run sequentially
3. **Each sub-agent gets a focused task** - clear scope, clear deliverable
4. **Merge results** - after all parallel tasks complete, verify integration

Guidelines:
- Only parallelize tasks that don't modify the same files
- Each sub-task should be self-contained and testable
- Test integration after merging parallel results
"""


def get_subagent_prompt() -> str:
    """Return the subagent-driven-development prompt section.

    This prompt instructs the sub-agent on how to split work
    into parallel sub-agent tasks.

    Returns:
        A prompt string with sub-agent driven development instructions.
    """
    return SUBAGENT_PROMPT_SECTION


def should_use_subagents(
    *,
    acceptance_criteria: str | None = None,
    estimated_files_touched: int | None = None,
    estimated_complexity: int | None = None,
    sub_agent_mode_override: bool | None = None,
) -> bool:
    """Determine if a feature should use sub-agent driven development.

    Sub-agent mode is recommended when:
    - Feature explicitly sets sub_agent_mode=True in YAML (highest priority)
    - Feature has 3+ acceptance criteria steps
    - Feature touches 5+ files
    - Feature has complexity >= 8

    Args:
        acceptance_criteria: Feature acceptance criteria (JSON array string).
        estimated_files_touched: Estimated number of files the feature touches.
        estimated_complexity: Estimated complexity score.
        sub_agent_mode_override: Explicit sub-agent mode setting from feature (True/False/None).
                                 None means auto-detect based on heuristics.

    Returns:
        True if sub-agent mode should be enabled.
    """
    # PRIORITY 1: Check explicit override from feature.sub_agent_mode field
    if sub_agent_mode_override is not None:
        return sub_agent_mode_override

    # PRIORITY 2: Auto-detect based on heuristics (legacy behavior)
    # Check acceptance criteria count
    if acceptance_criteria:
        try:
            import json
            criteria = json.loads(acceptance_criteria)
            if isinstance(criteria, list) and len(criteria) >= 3:
                return True
        except (json.JSONDecodeError, ValueError):
            # Count lines or comma-separated items as a fallback
            items = [s.strip() for s in acceptance_criteria.split(",") if s.strip()]
            if len(items) >= 3:
                return True

    # Check file count
    if estimated_files_touched is not None and estimated_files_touched >= 5:
        return True

    # Check complexity
    if estimated_complexity is not None and estimated_complexity >= 8:
        return True

    return False


# ============================================================
# Orientation Prompt: Superpowers Skills Documentation
# ============================================================

SUPERPOWERS_ORIENTATION_SECTION = """\
## Superpowers Skills Available

The following Superpowers skills are integrated into your workflow:


### 1. Systematic Debugging Protocol (F106)

**IRON LAW: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST**

When you encounter ANY bug, test failure, or unexpected behavior:

**Phase 1: Root Cause Investigation (MANDATORY - Complete this first!)**
- What is the exact error message or unexpected behavior?
- What was the expected behavior vs. actual behavior?
- What code/component is involved in the failure?
- What inputs/state led to this failure?
- Is this reproducible? Under what conditions?
- What changed recently that might have caused this?

**Phase 2: Hypothesis Formation**
- Form a hypothesis about the root cause
- Identify evidence supporting this hypothesis

**Phase 3: Fix Implementation**
- Implement fix that addresses the root cause
- Ensure fix prevents recurrence

**Phase 4: Verification**
- Write/update tests to verify the fix
- Confirm no new issues introduced

**When to use:** ANY time you encounter a failure or bug. No exceptions.


### 2. Test-Driven Development (TDD) (F113)

**RULE: Write tests BEFORE implementation code.**

Follow the red-green-refactor cycle:

**Red:** Write tests that define expected behavior. Run them and confirm they fail.
**Green:** Write the minimum code needed to make the tests pass.
**Refactor:** Clean up code while keeping tests green.

**When to use:** When implementing new features, especially:
- New modules or functions
- Features with clear acceptance criteria
- Code that must meet specific correctness requirements
- Greenfield implementations where you control the test/code structure


### 3. Verification Before Completion (F113)

**RULE: Verify your work BEFORE claiming it is complete.**

Run this checklist before marking any feature as done:

1. **Files exist:** All expected source and test files are present
2. **No stubs:** No `pass`, `...`, `raise NotImplementedError`, or `# TODO` in source
3. **No mocks in production:** Mock imports only in test files, never in src/
4. **Tests pass:** Run `python -m pytest -v` and confirm all tests pass
5. **Real tests:** Tests contain actual assertions (not just `assert True`)

**When to use:** ALWAYS, before marking a feature as completed. No exceptions.


### 4. Sub-Agent Driven Development (F113)

**RULE: Split independent work into parallel sub-agent tasks.**

When a feature has multiple independent components:

1. Identify tasks that can be done in parallel (no shared dependencies)
2. Group dependent tasks into serial execution order
3. Each sub-agent gets a focused, independent task
4. Results are merged after all parallel tasks complete

**When to use:** When a feature has:
- 3+ independent sub-tasks
- Components that don't share state or files
- Work that can be safely parallelized
- Complex features that benefit from divide-and-conquer
"""


def get_superpowers_orientation() -> str:
    """Return the Superpowers skills documentation for orientation.

    This section is appended to the orientation prompt to inform
    sub-agents about all available Superpowers skills and when
    to use each one.

    Returns:
        A prompt string documenting all Superpowers skills.
    """
    return SUPERPOWERS_ORIENTATION_SECTION


def build_superpowers_prompt(
    *,
    enable_tdd: bool = False,
    enable_verification: bool = True,
    enable_subagent: bool = False,
) -> str:
    """Build a combined superpowers prompt from enabled skills.

    Assembles prompt sections for the enabled superpowers skills.
    The verification-before-completion skill is enabled by default
    since it should always run.

    Args:
        enable_tdd: Include TDD mode instructions.
        enable_verification: Include verification checklist (default: True).
        enable_subagent: Include sub-agent driven development instructions.

    Returns:
        Combined prompt string with all enabled skill sections.
    """
    sections: list[str] = []

    if enable_tdd:
        sections.append(get_tdd_prompt())

    if enable_subagent:
        sections.append(get_subagent_prompt())

    if enable_verification:
        sections.append(get_verification_prompt())

    if not sections:
        return ""

    return "\n".join(sections)
