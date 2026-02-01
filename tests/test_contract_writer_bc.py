"""Tests for B+C hybrid additions to ContractWriter.

Tests verification level tracking, promotion, and meta-test integration.
"""

import pytest
import tempfile
from pathlib import Path

from bob.orchestrator.contract_writer import ContractWriter
from bob.orchestrator.verification_level import VerificationLevel


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temp workspace with .bob/contracts/ dir."""
    return str(tmp_path)


@pytest.fixture
def writer(tmp_workspace):
    return ContractWriter(tmp_workspace)


# Real test code that satisfies the meta-test requirements
GOOD_TEST_CODE = '''\
def test_addition():
    """Test basic addition."""
    import numpy as np
    result = 1 + 1
    assert result == 2, "1 + 1 should be 2"
    np.testing.assert_allclose(result, 2.0, atol=1e-10)
    print("PASS: addition")


def test_multiplication():
    """Test basic multiplication."""
    result = 3 * 4
    assert result == 12, "3 * 4 should be 12"
    assert result > 0, "product should be positive"
    print("PASS: multiplication")


def test_sqrt():
    """Test square root computation."""
    import math
    result = math.sqrt(16)
    assert abs(result - 4.0) < 1e-10, "sqrt(16) should be 4"
    assert result > 0, "sqrt should be positive"
    print("PASS: sqrt")
'''


class TestVerificationLevelTracking:
    def test_write_with_unit_level(self, writer):
        path = writer.write_contract(
            task_id="T001",
            category="numerical",
            test_code=GOOD_TEST_CODE,
            verification_level=VerificationLevel.UNIT,
        )
        content = path.read_text()
        assert "Verification level: unit" in content

    def test_write_with_integration_level(self, writer):
        path = writer.write_contract(
            task_id="T001",
            category="algorithmic",
            test_code=GOOD_TEST_CODE,
            verification_level=VerificationLevel.INTEGRATION,
        )
        content = path.read_text()
        assert "Verification level: integration" in content

    def test_write_with_system_level(self, writer):
        path = writer.write_contract(
            task_id="T001",
            category="convergence",
            test_code=GOOD_TEST_CODE,
            verification_level=VerificationLevel.SYSTEM,
        )
        content = path.read_text()
        assert "Verification level: system" in content

    def test_default_level_is_unit(self, writer):
        path = writer.write_contract(
            task_id="T002",
            category="numerical",
            test_code=GOOD_TEST_CODE,
        )
        content = path.read_text()
        assert "Verification level: unit" in content

    def test_get_contract_level(self, writer):
        path = writer.write_contract(
            task_id="T003",
            category="numerical",
            test_code=GOOD_TEST_CODE,
            verification_level=VerificationLevel.INTEGRATION,
        )
        level = writer.get_contract_level(path)
        assert level == VerificationLevel.INTEGRATION

    def test_get_level_missing_file(self, writer):
        fake_path = Path(writer.workspace_dir) / "nonexistent.py"
        level = writer.get_contract_level(fake_path)
        assert level is None


class TestPromoteToIntegration:
    def test_promote_unit_to_integration(self, writer):
        path = writer.write_contract(
            task_id="T004",
            category="numerical",
            test_code=GOOD_TEST_CODE,
            verification_level=VerificationLevel.UNIT,
        )
        # Verify starts as unit
        assert writer.get_contract_level(path) == VerificationLevel.UNIT

        # Promote
        result = writer.promote_to_integration(path)

        # Verify promoted
        assert result == path
        assert writer.get_contract_level(path) == VerificationLevel.INTEGRATION

    def test_promote_system_to_integration(self, writer):
        path = writer.write_contract(
            task_id="T005",
            category="numerical",
            test_code=GOOD_TEST_CODE,
            verification_level=VerificationLevel.SYSTEM,
        )
        writer.promote_to_integration(path)
        assert writer.get_contract_level(path) == VerificationLevel.INTEGRATION

    def test_promote_already_integration(self, writer):
        path = writer.write_contract(
            task_id="T006",
            category="numerical",
            test_code=GOOD_TEST_CODE,
            verification_level=VerificationLevel.INTEGRATION,
        )
        writer.promote_to_integration(path)
        # Should stay integration
        assert writer.get_contract_level(path) == VerificationLevel.INTEGRATION


class TestValidateWithMetaTests:
    def test_good_contract_passes(self, writer):
        path = writer.write_contract(
            task_id="T007",
            category="numerical",
            test_code=GOOD_TEST_CODE,
        )
        is_valid, errors = writer.validate_with_meta_tests(path)
        assert is_valid, f"Expected valid, got errors: {errors}"
        assert errors == []

    def test_bad_syntax_fails_before_meta(self, writer):
        bad_code = "def test_broken(:\n    pass"
        path = writer.write_contract(
            task_id="T008",
            category="numerical",
            test_code=bad_code,
        )
        is_valid, errors = writer.validate_with_meta_tests(path)
        assert not is_valid
        assert any("yntax" in e for e in errors)  # Syntax error

    def test_trivial_contract_fails_meta(self, writer):
        # A contract with assert True should fail meta-tests
        trivial_code = '''\
def test_fake1():
    """Fake test."""
    assert True

def test_fake2():
    """Another fake."""
    assert 1
'''
        path = writer.write_contract(
            task_id="T009",
            category="numerical",
            test_code=trivial_code,
            min_assertions=3,
        )
        is_valid, errors = writer.validate_with_meta_tests(path)
        # Should fail either static (trivial assertions) or meta-tests
        assert not is_valid
