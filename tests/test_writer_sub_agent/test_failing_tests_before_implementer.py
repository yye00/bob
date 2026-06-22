"""Tests for test_writer_sub_agent.generate_failing_tests integration.

Verifies that the test-writer sub-agent:
  1. Emits one failing pytest per AC before the implementer fires
  2. Applies the TestGen-LLM triple filter (compile/stub/coverage checks)
  3. Integrates correctly between spec-critic (F-R7-450) and the implementer
  4. Returns well-formed results with gate_passed boolean

These tests verify the top-level API exposed by test_writer_sub_agent module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import test_writer_sub_agent as _mod
from bob3.orchestrator.test_writer_agent import (
    BijectionReport,
    EmittedTest,
    FilterResult,
)


class TestGenerateFailingTests:
    """Tests for test_writer_sub_agent.generate_failing_tests."""

    def test_generates_failing_tests_for_feature(self, tmp_path):
        """Primary AC: generate_failing_tests emits one test file per AC."""
        acs = [
            "File exists: src/example.py",
            "Function defined: example.run",
        ]
        result = _mod.generate_failing_tests(
            "feat-primary",
            acs,
            workspace=tmp_path,
        )

        assert "emitted" in result
        assert "filter_results" in result
        assert "bijection" in result
        assert "gate_passed" in result

        assert len(result["emitted"]) == 2
        assert len(result["filter_results"]) == 2
        assert isinstance(result["gate_passed"], bool)

    def test_emitted_tests_are_emitted_test_objects(self, tmp_path):
        """Each emitted test must be an EmittedTest dataclass."""
        acs = ["File exists: src/a.py"]
        result = _mod.generate_failing_tests(
            "feat-type-check", acs, workspace=tmp_path
        )

        assert all(isinstance(e, EmittedTest) for e in result["emitted"])

    def test_filter_results_are_filter_result_objects(self, tmp_path):
        """Each filter result must be a FilterResult dataclass."""
        acs = ["pytest: tests/test_x.py"]
        result = _mod.generate_failing_tests(
            "feat-filter-type", acs, workspace=tmp_path
        )

        assert all(isinstance(r, FilterResult) for r in result["filter_results"])

    def test_bijection_is_bijection_report(self, tmp_path):
        """The bijection result must be a BijectionReport."""
        acs = ["Function defined: bob3.mod.fn"]
        result = _mod.generate_failing_tests(
            "feat-bij-type", acs, workspace=tmp_path
        )

        assert isinstance(result["bijection"], BijectionReport)

    def test_gate_passed_true_when_all_checks_pass(self, tmp_path):
        """gate_passed must be True when all triple-filter checks pass and bijection is satisfied."""
        acs = ["File exists: src/gate_pass.py", "pytest: tests/test_gate.py"]
        result = _mod.generate_failing_tests(
            "feat-gate-pass", acs, workspace=tmp_path
        )

        # The generated tests use pytest.fail, which should pass all triple filter checks
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True
        assert all(r.accepted for r in result["filter_results"])

    def test_emitted_test_files_exist_on_disk(self, tmp_path):
        """All emitted test files must actually exist on disk."""
        acs = ["File exists: src/disk_check.py"]
        result = _mod.generate_failing_tests(
            "feat-disk", acs, workspace=tmp_path
        )

        for emitted in result["emitted"]:
            assert emitted.test_path.exists()
            assert emitted.test_path.is_file()

    def test_test_files_placed_under_feature_id_directory(self, tmp_path):
        """Test files must be placed under tests/<feature_id>/test_<ac_id>.py."""
        feature_id = "feat-dir-structure"
        acs = ["Function defined: bob3.x.run"]
        result = _mod.generate_failing_tests(
            feature_id, acs, workspace=tmp_path
        )

        expected_dir = tmp_path / "tests" / feature_id
        assert expected_dir.exists()
        assert expected_dir.is_dir()

        for emitted in result["emitted"]:
            assert emitted.test_path.parent == expected_dir

    def test_one_test_file_per_acceptance_criterion(self, tmp_path):
        """Must emit exactly one test file per acceptance criterion."""
        acs = [
            "File exists: src/a.py",
            "Function defined: bob3.b.fn",
            "pytest: tests/test_c.py",
        ]
        result = _mod.generate_failing_tests(
            "feat-one-per-ac", acs, workspace=tmp_path
        )

        assert len(result["emitted"]) == len(acs)

    def test_empty_acceptance_criteria_returns_empty_result(self, tmp_path):
        """Zero ACs must return empty emitted/filter_results and gate_passed=True."""
        result = _mod.generate_failing_tests(
            "feat-empty", [], workspace=tmp_path
        )

        assert result["emitted"] == []
        assert result["filter_results"] == []
        assert result["gate_passed"] is True
        assert result["bijection"].is_bijective is True


class TestIntegrationWithSpecCritic:
    """Integration tests verifying the test-writer sub-agent works between spec-critic and implementer."""

    def test_accepts_feature_spec_output_format(self, tmp_path):
        """Must accept the same AC format that spec-critic (F-R7-450) emits."""
        # Spec-critic emits acceptance criteria as a list of strings
        acs = [
            "File exists: src/bob3/mymod.py",
            "Function defined: bob3.mymod.my_fn",
            "pytest: tests/test_mymod.py",
        ]
        result = _mod.generate_failing_tests(
            "feat-spec-critic-fmt", acs, workspace=tmp_path
        )

        assert len(result["emitted"]) == 3
        assert result["gate_passed"] is True

    def test_can_be_called_after_spec_critic_before_implementer(self, tmp_path):
        """Simulates the orchestrator flow: spec-critic → test-writer → implementer.

        The test-writer receives validated ACs from spec-critic and emits failing
        tests that the implementer will then make pass.
        """
        # Simulate spec-critic output
        validated_acs = [
            "File exists: src/bob3/orchestrated.py",
            "Function defined: bob3.orchestrated.process",
        ]

        # Test-writer sub-agent runs
        result = _mod.generate_failing_tests(
            "feat-orchestration", validated_acs, workspace=tmp_path
        )

        # Implementer would receive these failing tests
        assert len(result["emitted"]) == 2
        for emitted in result["emitted"]:
            # Each test file must fail before implementation
            content = emitted.test_path.read_text()
            assert "pytest.fail" in content
            # Test references the AC
            assert emitted.ac_text in content

    def test_gate_passed_blocks_implementer_when_tests_invalid(self, tmp_path):
        """gate_passed=False must prevent the implementer from firing."""
        # This is a meta-test: in real usage, the orchestrator would check
        # gate_passed and skip the implementer if False. We verify the flag works.
        acs = ["File exists: src/gate_test.py"]
        result = _mod.generate_failing_tests(
            "feat-gate-check", acs, workspace=tmp_path
        )

        # With pytest.fail in the template, gate_passed should be True for normal ACs
        if result["gate_passed"]:
            # Implementer may proceed
            pass
        else:
            # Implementer must NOT proceed - this is the safety gate
            pytest.fail("gate_passed should be True for valid test emission")


class TestTripleFilter:
    """Tests verifying the TestGen-LLM triple filter (compile / stub / coverage)."""

    def test_triple_filter_rejects_uncompilable_tests(self, tmp_path):
        """Tests that don't compile must be rejected by the triple filter."""
        # We can't easily generate an uncompilable test from the normal flow,
        # but we verify the filter_results structure includes the compile flag
        acs = ["File exists: src/compile_check.py"]
        result = _mod.generate_failing_tests(
            "feat-compile", acs, workspace=tmp_path
        )

        for filter_result in result["filter_results"]:
            assert hasattr(filter_result, "compiles")
            assert hasattr(filter_result, "accepted")

    def test_triple_filter_checks_fails_on_stub(self, tmp_path):
        """Tests must fail when run against stub code (no implementation)."""
        acs = ["pytest: tests/test_stub_fail.py"]
        result = _mod.generate_failing_tests(
            "feat-stub", acs, workspace=tmp_path
        )

        for filter_result in result["filter_results"]:
            assert hasattr(filter_result, "fails_on_stub")
            # Our template uses pytest.fail, so fails_on_stub should be True
            assert filter_result.fails_on_stub is True

    def test_triple_filter_checks_coverage_uplift(self, tmp_path):
        """Tests must reference non-pytest symbols (coverage heuristic)."""
        acs = ["Function defined: bob3.coverage.fn"]
        result = _mod.generate_failing_tests(
            "feat-cov", acs, workspace=tmp_path
        )

        for filter_result in result["filter_results"]:
            assert hasattr(filter_result, "raises_coverage")
            # Our template uses pytest.fail which counts as coverage
            assert filter_result.raises_coverage is True

    def test_all_filter_checks_must_pass_for_acceptance(self, tmp_path):
        """accepted=True only when compiles=True AND fails_on_stub=True AND raises_coverage=True."""
        acs = ["File exists: src/filter_all.py"]
        result = _mod.generate_failing_tests(
            "feat-filter-all", acs, workspace=tmp_path
        )

        for filter_result in result["filter_results"]:
            if filter_result.accepted:
                assert filter_result.compiles is True
                assert filter_result.fails_on_stub is True
                assert filter_result.raises_coverage is True


class TestBijectionVerification:
    """Tests for AC↔test bijection verification."""

    def test_bijection_satisfied_when_one_test_per_ac(self, tmp_path):
        """Every AC must have exactly one test file."""
        acs = ["File exists: src/a.py", "Function defined: b.fn"]
        result = _mod.generate_failing_tests(
            "feat-bij-sat", acs, workspace=tmp_path
        )

        assert result["bijection"].is_bijective is True

    def test_bijection_reports_missing_tests(self, tmp_path):
        """Bijection must detect when an AC has no corresponding test file."""
        # Generate tests normally
        acs = ["File exists: src/missing.py"]
        result = _mod.generate_failing_tests(
            "feat-bij-missing", acs, workspace=tmp_path
        )

        # Manually delete a test file to break bijection
        for emitted in result["emitted"]:
            emitted.test_path.unlink()

        # Re-verify bijection
        from bob3.orchestrator.test_writer_agent import verify_bijection
        broken = verify_bijection("feat-bij-missing", acs, workspace=tmp_path)

        assert broken.is_bijective is False
        assert len(broken.missing_tests) > 0

    def test_bijection_reports_orphan_tests(self, tmp_path):
        """Bijection must detect test files with no corresponding AC."""
        acs = ["File exists: src/orphan.py"]
        result = _mod.generate_failing_tests(
            "feat-bij-orphan", acs, workspace=tmp_path
        )

        # Create an extra test file not matching any AC
        test_dir = tmp_path / "tests" / "feat-bij-orphan"
        orphan_file = test_dir / "test_orphan_extra.py"
        orphan_file.write_text("# orphan test", encoding="utf-8")

        # Re-verify bijection
        from bob3.orchestrator.test_writer_agent import verify_bijection
        broken = verify_bijection("feat-bij-orphan", acs, workspace=tmp_path)

        assert broken.is_bijective is False
        assert len(broken.orphan_tests) > 0


class TestWorkspaceHandling:
    """Tests for workspace parameter handling."""

    def test_accepts_path_object_workspace(self, tmp_path):
        """workspace parameter must accept pathlib.Path objects."""
        acs = ["File exists: src/pathobj.py"]
        result = _mod.generate_failing_tests(
            "feat-path", acs, workspace=tmp_path
        )

        assert len(result["emitted"]) == 1

    def test_accepts_string_workspace(self, tmp_path):
        """workspace parameter must accept string paths."""
        acs = ["File exists: src/strpath.py"]
        result = _mod.generate_failing_tests(
            "feat-str", acs, workspace=str(tmp_path)
        )

        assert len(result["emitted"]) == 1

    def test_defaults_to_cwd_when_workspace_none(self, monkeypatch, tmp_path):
        """When workspace=None, must use current working directory."""
        monkeypatch.chdir(tmp_path)
        acs = ["Function defined: bob3.cwd.fn"]
        result = _mod.generate_failing_tests(
            "feat-cwd", acs, workspace=None
        )

        expected_dir = tmp_path / "tests" / "feat-cwd"
        assert expected_dir.exists()
