"""Tests for contract-based verification in the verifier module.

Validates that verify_task_outputs() discovers and runs .py contract
files from .bob/contracts/, and that the stdout-acceptance fix works.
"""

import pytest
import textwrap
from pathlib import Path
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import Optional

from bob.orchestrator.verifier import (
    run_contract_tests,
    run_verify_script,
    run_verification_test,
    verify_task_outputs,
)


@dataclass
class FakeExpectedOutput:
    path: str = ""
    min_lines: int = 0
    must_contain: list = field(default_factory=list)
    must_not_contain: list = field(default_factory=list)


@dataclass
class FakeVerificationTest:
    name: str = "test"
    command: str = "echo PASS"
    timeout: int = 30
    expected_exit_code: int = 0


@dataclass
class FakeTask:
    spec_id: str = "T001"
    priority: str = "medium"
    expected_outputs: list = field(default_factory=list)
    verify_script: Optional[str] = None
    numerical_tests: list = field(default_factory=list)
    algorithmic_tests: list = field(default_factory=list)
    convergence_tests: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# run_contract_tests
# ---------------------------------------------------------------------------


class TestRunContractTests:
    def test_no_contracts_dir(self, tmp_path):
        """No .bob/contracts/ → pass (nothing to run)."""
        passed, msgs = run_contract_tests("T001", tmp_path)
        assert passed
        assert msgs == []

    def test_no_matching_contracts(self, tmp_path):
        """Contracts dir exists but no files for this task."""
        (tmp_path / ".bob" / "contracts").mkdir(parents=True)
        passed, msgs = run_contract_tests("T001", tmp_path)
        assert passed
        assert msgs == []

    def test_passing_contract(self, tmp_path):
        """A valid contract that passes."""
        contracts_dir = tmp_path / ".bob" / "contracts"
        contracts_dir.mkdir(parents=True)

        contract = contracts_dir / "T001_numerical.py"
        contract.write_text(textwrap.dedent("""\
            def test_math():
                assert 1 + 1 == 2

            def test_more_math():
                assert 2 * 3 == 6
        """))

        passed, msgs = run_contract_tests("T001", tmp_path)
        assert passed
        assert any("PASS" in m for m in msgs)

    def test_failing_contract(self, tmp_path):
        """A contract with a failing test."""
        contracts_dir = tmp_path / ".bob" / "contracts"
        contracts_dir.mkdir(parents=True)

        contract = contracts_dir / "T002_numerical.py"
        contract.write_text(textwrap.dedent("""\
            def test_wrong():
                assert 1 == 2, "math is broken"
        """))

        passed, msgs = run_contract_tests("T002", tmp_path)
        assert not passed
        assert any("FAIL" in m for m in msgs)

    def test_multiple_contracts(self, tmp_path):
        """Multiple contract files for one task."""
        contracts_dir = tmp_path / ".bob" / "contracts"
        contracts_dir.mkdir(parents=True)

        (contracts_dir / "T003_numerical.py").write_text(
            "def test_a():\n    assert True\n"
        )
        (contracts_dir / "T003_algorithmic.py").write_text(
            "def test_b():\n    assert True\n"
        )

        passed, msgs = run_contract_tests("T003", tmp_path)
        assert passed
        assert len([m for m in msgs if "PASS" in m or "SKIP" in m]) >= 2

    def test_meta_tests_skipped(self, tmp_path):
        """Meta-tests (test_meta_*) should not run during verification."""
        contracts_dir = tmp_path / ".bob" / "contracts"
        contracts_dir.mkdir(parents=True)

        contract = contracts_dir / "T004_numerical.py"
        contract.write_text(textwrap.dedent("""\
            def test_meta_should_skip():
                # This would fail if run
                assert False, "meta should not run"

            def test_real():
                assert 1 + 1 == 2
        """))

        passed, msgs = run_contract_tests("T004", tmp_path)
        assert passed  # meta-test not run → only test_real runs

    def test_timeout_handling(self, tmp_path):
        """Contract that times out."""
        contracts_dir = tmp_path / ".bob" / "contracts"
        contracts_dir.mkdir(parents=True)

        contract = contracts_dir / "T005_numerical.py"
        contract.write_text(textwrap.dedent("""\
            import time
            def test_slow():
                time.sleep(999)
        """))

        passed, msgs = run_contract_tests("T005", tmp_path, timeout=2)
        assert not passed
        assert any("TIMEOUT" in m for m in msgs)


# ---------------------------------------------------------------------------
# Fix #5: verify script stdout acceptance
# ---------------------------------------------------------------------------


class TestVerifyScriptStdout:
    def test_script_with_no_stdout_passes(self, tmp_path):
        """Script that exits 0 with no stdout should pass."""
        passed, msg = run_verify_script("true", tmp_path)
        assert passed
        assert "exit 0" in msg.lower() or "pass" in msg.lower()

    def test_script_with_stderr_only_passes(self, tmp_path):
        """Script that writes to stderr but exits 0 should pass."""
        passed, msg = run_verify_script(
            "echo 'info' >&2; exit 0", tmp_path
        )
        assert passed

    def test_script_that_fails_still_fails(self, tmp_path):
        """Script that exits non-zero should still fail."""
        passed, msg = run_verify_script("exit 1", tmp_path)
        assert not passed

    def test_verification_test_no_stdout(self, tmp_path):
        """VerificationTest with no stdout should pass if exit 0."""
        test = FakeVerificationTest(
            name="silent_test",
            command="true",
        )
        passed, msg = run_verification_test(test, tmp_path)
        assert passed


# ---------------------------------------------------------------------------
# Integration: verify_task_outputs with contracts
# ---------------------------------------------------------------------------


class TestVerifyTaskOutputsWithContracts:
    def test_contracts_run_during_verification(self, tmp_path):
        """Contracts are discovered and run as part of verify_task_outputs."""
        # Create a passing contract (no external imports needed)
        contracts_dir = tmp_path / ".bob" / "contracts"
        contracts_dir.mkdir(parents=True)
        (contracts_dir / "T010_numerical.py").write_text(textwrap.dedent("""\
            def test_basic_math():
                assert 1 + 1 == 2

            def test_string_ops():
                assert "hello".upper() == "HELLO"
        """))

        task = FakeTask(
            spec_id="T010",
            verify_script="echo PASS",
        )

        passed, msg = verify_task_outputs(task, tmp_path)
        assert passed, f"verify_task_outputs failed:\n{msg}"
        assert "Contract Tests" in msg

    def test_failing_contract_fails_verification(self, tmp_path):
        """A failing contract causes verify_task_outputs to fail."""
        contracts_dir = tmp_path / ".bob" / "contracts"
        contracts_dir.mkdir(parents=True)
        (contracts_dir / "T011_numerical.py").write_text(textwrap.dedent("""\
            def test_should_fail():
                assert False, "implementation is wrong"
        """))

        task = FakeTask(
            spec_id="T011",
            verify_script="echo PASS",
        )

        passed, msg = verify_task_outputs(task, tmp_path)
        assert not passed
        assert "FAIL" in msg
