"""Tests for bob3.acceptance_criteria.verify_artifacts — AC artifact-existence verifier.

Pre-pytest pass MUST verify that every AC of the form
``pytest: <path>``, ``File exists: <path>``, ``File modified: <path>``,
or ``Function defined: <module>.<symbol>`` resolves to an actual artifact.
Missing artifact -> AC fails with reason ARTIFACT_MISSING:<path>, never
swallowed as a generic pytest exit code.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bob3.acceptance_criteria import ArtifactMiss, verify_artifact_existence

_WORKSPACE = Path(__file__).resolve().parent.parent
_IMPL_REL = "src/bob3/acceptance_criteria.py"


class TestVerifyArtifactExistenceFileExists:
    def test_file_exists_ac_passes_for_real_file(self):
        """File exists: AC pointing to a real file returns no misses."""
        ac = f"File exists: {_IMPL_REL}"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert result == [], f"Expected no misses for real file, got: {result}"

    def test_file_exists_ac_fails_for_missing_file(self):
        """File exists: AC for a nonexistent file returns an ArtifactMiss."""
        ac = "File exists: totally_missing_file.py"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert len(result) >= 1, "Expected at least one miss for missing file"
        assert result[0].kind == "file_exists"
        assert "ARTIFACT_MISSING" in result[0].reason

    def test_file_exists_miss_is_artifact_miss(self):
        """Each entry in the returned list must be an ArtifactMiss."""
        ac = "File exists: no_such_file.py"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert isinstance(result[0], ArtifactMiss)


class TestVerifyArtifactExistencePytest:
    def test_pytest_ac_fails_for_missing_file(self):
        """pytest: AC for a nonexistent file produces a miss with kind='pytest'."""
        ac = "pytest: tests/no_such_test.py"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert len(result) >= 1
        assert result[0].kind == "pytest"
        assert "ARTIFACT_MISSING" in result[0].reason

    def test_pytest_ac_passes_for_real_test_file(self):
        """pytest: AC for a real test file with tests returns no misses."""
        ac = "pytest: tests/test_ac_artifact_existence_verifier_boundary.py"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert result == [], f"Expected no misses for real test file, got: {result}"

    def test_pytest_ac_miss_expected_path_contains_path(self):
        """The ArtifactMiss expected_path must reference the missing test path."""
        missing = "tests/totally_gone_test.py"
        ac = f"pytest: {missing}"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert missing in result[0].expected_path


class TestVerifyArtifactExistenceFunctionDefined:
    def test_function_defined_ac_passes_for_real_function(self):
        """Function defined: AC for a real function returns no misses."""
        ac = "Function defined: bob3.acceptance_criteria.verify_artifact_existence"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert result == [], f"Expected no misses for real function, got: {result}"

    def test_function_defined_ac_fails_for_missing_function(self):
        """Function defined: AC for a nonexistent symbol produces an ArtifactMiss."""
        ac = "Function defined: bob3.acceptance_criteria.no_such_function_xyz"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert len(result) >= 1
        assert result[0].kind == "function_defined"
        assert "ARTIFACT_MISSING" in result[0].reason

    def test_function_defined_ac_fails_for_missing_module(self):
        """Function defined: AC for a missing module produces an ArtifactMiss."""
        ac = "Function defined: bob3.no_module_xyz_abc.some_func"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert len(result) >= 1


class TestVerifyArtifactExistenceMultipleAcs:
    def test_empty_list_returns_empty(self):
        """Empty AC list returns an empty list."""
        assert verify_artifact_existence([], _WORKSPACE) == []

    def test_all_present_returns_empty(self):
        """All present ACs return no misses."""
        acs = [
            f"File exists: {_IMPL_REL}",
            "Function defined: bob3.acceptance_criteria.verify_artifact_existence",
        ]
        result = verify_artifact_existence(acs, _WORKSPACE)
        assert result == []

    def test_mix_of_present_and_missing(self):
        """Mixed ACs: only missing ones produce misses; present ones are silent."""
        acs = [
            f"File exists: {_IMPL_REL}",
            "File exists: totally_gone_file.py",
        ]
        result = verify_artifact_existence(acs, _WORKSPACE)
        assert len(result) == 1
        assert "totally_gone_file.py" in result[0].expected_path

    def test_multiple_missing_produces_multiple_misses(self):
        """Each missing AC produces a separate ArtifactMiss."""
        acs = [
            "File exists: missing_a.py",
            "File exists: missing_b.py",
        ]
        result = verify_artifact_existence(acs, _WORKSPACE)
        assert len(result) == 2

    def test_reason_is_never_empty(self):
        """Each ArtifactMiss must have a non-empty reason."""
        ac = "File exists: not_there.py"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert result[0].reason, "reason must not be empty"

    def test_reason_contains_artifact_missing_prefix(self):
        """The reason must begin with or contain 'ARTIFACT_MISSING:'."""
        ac = "File exists: missing_file.py"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert "ARTIFACT_MISSING" in result[0].reason


class TestVerifyArtifactExistencePathConfinement:
    def test_path_traversal_produces_miss(self):
        """AC with path traversal must not silently pass."""
        ac = "File exists: ../../etc/passwd"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert len(result) >= 1, "Path traversal must not silently pass"

    def test_absolute_path_produces_miss(self):
        """AC with an absolute path must not silently pass."""
        ac = "File exists: /etc/passwd"
        result = verify_artifact_existence([ac], _WORKSPACE)
        assert len(result) >= 1, "Absolute path must not silently pass"


class TestVerifyArtifactExistenceOrchestratorIntegration:
    def test_verify_artifacts_callable_from_orchestrator_path(self):
        """bob3.orchestrator can import and use verify_artifact_existence."""
        from bob3.acceptance_criteria import verify_artifact_existence as fn
        assert callable(fn)

    def test_run_loop_exposes_pre_pytest_hook(self):
        """run_loop exposes verify_artifact_existence_pre_pytest."""
        import importlib
        mod = importlib.import_module("bob3.run_loop")
        assert hasattr(mod, "verify_artifact_existence_pre_pytest"), (
            "bob3.run_loop must expose verify_artifact_existence_pre_pytest"
        )

    def test_pre_pytest_hook_returns_empty_list_for_real_ac(self):
        """verify_artifact_existence_pre_pytest passes for a real file AC."""
        from bob3.run_loop import verify_artifact_existence_pre_pytest
        ac = f"File exists: {_IMPL_REL}"
        result = verify_artifact_existence_pre_pytest([ac], _WORKSPACE)
        assert result == []

    def test_pre_pytest_hook_returns_miss_for_missing_file(self):
        """verify_artifact_existence_pre_pytest flags a missing file."""
        from bob3.run_loop import verify_artifact_existence_pre_pytest
        ac = "File exists: definitely_missing_artifact.py"
        result = verify_artifact_existence_pre_pytest([ac], _WORKSPACE)
        assert len(result) >= 1
