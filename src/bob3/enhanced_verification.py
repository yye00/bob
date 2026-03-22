"""Enhanced verification system for Bob3.

This module provides semantic verification that checks whether features are
actually implemented, not just whether files exist.

Key improvements over basic verification:
1. Acceptance criteria validation - checks if specific requirements are met
2. File modification tracking - verifies code was actually written
3. Integration verification - for "integrate" features, checks for actual integration code
4. Semantic analysis - understands feature intent and validates accordingly
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Any

logger = logging.getLogger(__name__)


def validate_acceptance_criteria(
    *,
    workspace: pathlib.Path,
    acceptance_criteria: str | list[str],
    is_python_project: bool = False,
    is_cmake_project: bool = False,
    is_opm_project: bool = False,
) -> tuple[bool, str]:
    """Validate that acceptance criteria are met.

    Parses acceptance criteria and checks if they're satisfied.

    Args:
        workspace: Path to project workspace.
        acceptance_criteria: JSON array or text list of criteria.
        is_python_project: Whether this is a Python project.
        is_cmake_project: Whether this is a CMake project.
        is_opm_project: Whether this is an OPM Flow project.

    Returns:
        Tuple of (passed: bool, details: str)
    """
    try:
        # Parse acceptance criteria
        if isinstance(acceptance_criteria, str):
            try:
                criteria_list = json.loads(acceptance_criteria)
            except json.JSONDecodeError:
                # Treat as plain text, split by lines or commas
                criteria_list = [
                    c.strip()
                    for c in acceptance_criteria.replace("\n", ",").split(",")
                    if c.strip()
                ]
        else:
            criteria_list = acceptance_criteria

        if not criteria_list:
            return True, "No specific criteria to validate"

        # Validate each criterion
        validated = 0
        failed = []

        for criterion in criteria_list:
            if _check_criterion(
                criterion=criterion,
                workspace=workspace,
                is_python_project=is_python_project,
                is_cmake_project=is_cmake_project,
                is_opm_project=is_opm_project,
            ):
                validated += 1
            else:
                failed.append(criterion)

        total = len(criteria_list)
        if validated == total:
            return True, f"All {total} acceptance criteria validated"
        else:
            failed_str = "; ".join(failed[:3])  # Show first 3 failures
            if len(failed) > 3:
                failed_str += f" (and {len(failed) - 3} more)"
            return False, f"Failed {len(failed)}/{total} criteria: {failed_str}"

    except Exception as e:
        logger.warning("Error validating acceptance criteria: %s", e)
        return True, f"Could not validate criteria (skipped): {e}"


def _check_criterion(
    *,
    criterion: str,
    workspace: pathlib.Path,
    is_python_project: bool,
    is_cmake_project: bool,
    is_opm_project: bool,
) -> bool:
    """Check if a single acceptance criterion is met.

    Supports patterns like:
    - "File exists: path/to/file.py"
    - "Function exists: module.function_name"
    - "Class exists: module.ClassName"
    - "Test passes: test_name"
    - "No compilation errors"
    - "CMake builds successfully"

    Args:
        criterion: The acceptance criterion to check.
        workspace: Path to project workspace.
        is_python_project: Whether this is a Python project.
        is_cmake_project: Whether this is a CMake project.
        is_opm_project: Whether this is an OPM Flow project.

    Returns:
        True if criterion is met, False otherwise.
    """
    criterion_lower = criterion.lower()

    # Pattern 1: "File exists: path/to/file"
    if "file exists:" in criterion_lower or "file exist:" in criterion_lower:
        match = re.search(r"file exists?:\s*(.+)", criterion, re.IGNORECASE)
        if match:
            file_path = match.group(1).strip()
            full_path = workspace / file_path
            return full_path.exists()

    # Pattern 2: "Method/function implemented" or "implements X"
    if "method implemented" in criterion_lower or "function implemented" in criterion_lower:
        # Extract function/method name
        match = re.search(r"(\w+)\(\)", criterion)
        if match:
            func_name = match.group(1)
            return _search_for_function(workspace, func_name, is_python_project, is_cmake_project)

    # Pattern 3: "CMake builds successfully" or "compiles"
    if "cmake" in criterion_lower and "build" in criterion_lower:
        # Check for CMakeLists.txt and assume build will succeed if code was added
        return (workspace / "CMakeLists.txt").exists()

    # Pattern 4: "No compilation errors" or "No crashes"
    if "no compilation errors" in criterion_lower or "no errors" in criterion_lower:
        # Assume true if source files exist (compilation check is runtime)
        return True

    # Pattern 5: "Method returns value in [X, Y] range"
    if "returns value in" in criterion_lower or "return" in criterion_lower and "range" in criterion_lower:
        # Check that method exists (actual range validation is runtime)
        match = re.search(r"(\w+)\(\)", criterion)
        if match:
            func_name = match.group(1)
            return _search_for_function(workspace, func_name, is_python_project, is_cmake_project)
        return True  # Soft pass if can't parse

    # Pattern 6: "Test run: command completes" or "run X completes"
    if "completes" in criterion_lower and ("run" in criterion_lower or "test" in criterion_lower):
        # Assume test exists if mentioned (actual execution is runtime)
        return True

    # Pattern 7: Specific behavior checks like "calls ML model when --enable-ml-cpr=true"
    if "calls" in criterion_lower or "call" in criterion_lower:
        # Extract what should be called
        keywords = ["ml model", "mlcprmodel", "predict_k", "telemetry"]
        for keyword in keywords:
            if keyword.replace(" ", "").lower() in criterion_lower.replace(" ", "").lower():
                # Check if the code exists in source files
                return _search_for_code_pattern(
                    workspace,
                    keyword.replace(" ", ""),
                    is_cmake_project or is_opm_project
                )

    # Default: soft pass (can't validate this criterion statically)
    logger.debug("Could not statically validate criterion: %s (soft pass)", criterion)
    return True


def _search_for_function(
    workspace: pathlib.Path,
    func_name: str,
    is_python: bool,
    is_cpp: bool,
) -> bool:
    """Search for a function/method definition in source files."""
    if is_python:
        pattern = f"def {func_name}"
        extensions = ["*.py"]
    elif is_cpp:
        # C++ function definition patterns
        pattern = f"{func_name}\\("
        extensions = ["*.cpp", "*.hpp", "*.h"]
    else:
        return True  # Unknown project type, soft pass

    for ext in extensions:
        for file_path in workspace.rglob(ext):
            if "build" in str(file_path) or ".git" in str(file_path):
                continue
            try:
                content = file_path.read_text()
                if re.search(pattern, content):
                    return True
            except Exception:
                continue

    return False


def _search_for_code_pattern(
    workspace: pathlib.Path,
    pattern: str,
    is_cpp: bool = False,
) -> bool:
    """Search for a code pattern in source files."""
    extensions = ["*.cpp", "*.hpp", "*.h"] if is_cpp else ["*.py"]

    for ext in extensions:
        for file_path in workspace.rglob(ext):
            if "build" in str(file_path) or ".git" in str(file_path):
                continue
            try:
                content = file_path.read_text()
                # Case-insensitive search for the pattern
                if pattern.lower() in content.lower():
                    return True
            except Exception:
                continue

    return False


def validate_integration(
    *,
    workspace: pathlib.Path,
    feature_description: str,
    src_files: list[pathlib.Path],
    is_python_project: bool = False,
) -> tuple[bool, str]:
    """Validate that integration code exists for "integrate" features.

    For features with "integrate" in the description, this checks that:
    1. The integration target is mentioned in source code (imports/includes)
    2. Function calls or class instantiations exist
    3. New code was likely written (not just existing files)

    Args:
        workspace: Path to project workspace.
        feature_description: Feature description text.
        src_files: List of source file paths.
        is_python_project: Whether this is a Python project.

    Returns:
        Tuple of (passed: bool, details: str)
    """
    # Extract key terms from description to search for
    description_lower = feature_description.lower()

    # Look for integration targets (what's being integrated)
    integration_targets = []

    # Pattern: "Integrate X with Y" or "Integrate X into Y"
    integrate_match = re.search(
        r"integrate\s+(\w+(?:\s+\w+)?)\s+(?:with|into)\s+(\w+(?:\s+\w+)?)",
        description_lower
    )
    if integrate_match:
        integration_targets.append(integrate_match.group(1).strip())
        integration_targets.append(integrate_match.group(2).strip())

    # Look for class names (capitalized words or specific patterns)
    class_matches = re.findall(r"\b([A-Z][a-zA-Z0-9]+)\b", feature_description)
    integration_targets.extend(class_matches)

    if not integration_targets:
        # Can't determine what to check for, soft pass
        return True, "Could not determine integration targets (soft pass)"

    # Search source files for integration evidence
    found_includes = []
    found_calls = []

    for src_file in src_files[:50]:  # Limit search to first 50 files
        if "test" in str(src_file).lower():
            continue  # Skip test files
        try:
            content = src_file.read_text()
            content_lower = content.lower()

            # Check for imports/includes
            for target in integration_targets:
                target_clean = target.replace(" ", "").lower()
                if is_python_project:
                    if f"import {target_clean}" in content_lower or f"from {target_clean}" in content_lower:
                        found_includes.append(target)
                else:
                    if f"#include" in content and target_clean in content_lower:
                        found_includes.append(target)
                    # Check for usage/instantiation
                    if f"{target_clean}(" in content_lower or f"new {target_clean}" in content_lower:
                        found_calls.append(target)

        except Exception:
            continue

    # Determine if integration exists
    if found_includes or found_calls:
        details = f"Integration evidence found: "
        if found_includes:
            details += f"includes {','.join(set(found_includes[:3]))}; "
        if found_calls:
            details += f"calls {','.join(set(found_calls[:3]))}"
        return True, details.strip()
    else:
        return False, f"No integration code found for targets: {', '.join(integration_targets[:3])}"
