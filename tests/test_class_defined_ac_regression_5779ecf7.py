"""Regression test for feature 5779ecf7 root cause.

feature 5779ecf7 (Mutation-testing post-impl quality gate / mutmut) was
NH-demoted despite emitting a correct MutationReport @dataclass because
enhanced_verification had no 'Class defined:' handler.

This test asserts that a Class-defined AC for an emitted dataclass passes
verification — verifying the fix closes that regression.
"""

import pathlib
import pytest
from bob3.verification.class_defined_ac_check import (
    check_class_defined_ac,
    extract_class_name_from_criterion,
)


AC_CRITERION = "Class defined: bob3.verification.mutation_gate.MutationReport"


def test_extract_returns_mutation_report():
    """AC criterion extracts correct class name."""
    result = extract_class_name_from_criterion(AC_CRITERION)
    assert result == "MutationReport"


def test_mutation_report_class_exists_in_real_workspace():
    """MutationReport dataclass exists in the actual workspace — regression guard."""
    workspace = pathlib.Path(__file__).parent.parent
    class_name = extract_class_name_from_criterion(AC_CRITERION)
    assert class_name is not None
    result = check_class_defined_ac(class_name, workspace)
    assert result is True, (
        f"MutationReport dataclass not found in workspace {workspace}. "
        "This would have caused NH-demotion for feature 5779ecf7."
    )


def test_class_defined_ac_passes_for_emitted_dataclass(tmp_path):
    """Simulate the exact failure scenario: dataclass decorated class in workspace."""
    # Simulate the mutation_gate.py module with the MutationReport dataclass
    verification_dir = tmp_path / "src" / "bob3" / "verification"
    verification_dir.mkdir(parents=True)
    mutation_gate = verification_dir / "mutation_gate.py"
    mutation_gate.write_text(
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class MutationReport:\n"
        "    \"\"\"Result of a mutmut mutation-testing run.\"\"\"\n"
        "    mutants_generated: int\n"
        "    mutants_killed: int\n"
        "    kill_rate: float\n"
        "    passed: bool\n"
    )

    class_name = extract_class_name_from_criterion(AC_CRITERION)
    assert class_name == "MutationReport"

    result = check_class_defined_ac(class_name, tmp_path)
    assert result is True, (
        "check_class_defined_ac must return True for a @dataclass-decorated class. "
        "Decorator above class line must be irrelevant (only 'class Name' token required)."
    )
