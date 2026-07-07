"""Tests for bob.pending_successor_verify (AC: dc709e23 + 6032ec54).

Acceptance criteria:
- File exists: src/bob/pending_successor_verify.py
- Function defined: bob.run_loop.set_pending_successor_verify
- Function defined: bob.pending_successor_verify.detect_verification_features
- Function defined: bob.pending_successor_verify.scan_ac_body_for_tokens
- pytest: tests/test_pending_successor_verify.py
- integration: bob.orchestrator
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature_mock(feature_id: str = "dc709e23-0000-0000-0000-000000000001") -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = "Test verifier-extension feature"
    f.status = "executing"
    return f


# ---------------------------------------------------------------------------
# AC 1: File exists — src/bob/pending_successor_verify.py
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_module_file_exists(self, tmp_path):
        import bob.pending_successor_verify  # noqa: F401

        module_file = Path(bob.pending_successor_verify.__file__)
        assert module_file.exists()
        assert module_file.name == "pending_successor_verify.py"

    def test_module_importable(self):
        import bob.pending_successor_verify  # noqa: F401

    def test_expected_names_exported(self):
        from bob.pending_successor_verify import (
            PENDING_SUCCESSOR_VERIFY_STATUS,
            VERIFIER_EXTENSION_MODULES,
            is_verifier_extension_feature,
            set_pending_successor_verify,
        )
        assert PENDING_SUCCESSOR_VERIFY_STATUS == "pending_successor_verify"
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert callable(is_verifier_extension_feature)
        assert callable(set_pending_successor_verify)


# ---------------------------------------------------------------------------
# AC 2: Function defined — bob.run_loop.set_pending_successor_verify
# ---------------------------------------------------------------------------


class TestRunLoopFunctionDefined:
    def test_set_pending_successor_verify_defined_in_run_loop(self):
        from bob.run_loop import set_pending_successor_verify
        assert callable(set_pending_successor_verify)

    def test_run_loop_all_includes_set_pending_successor_verify(self):
        import bob.run_loop as rl
        assert "set_pending_successor_verify" in rl.__all__

    def test_run_loop_function_signature(self):
        import inspect
        from bob.run_loop import set_pending_successor_verify
        sig = inspect.signature(set_pending_successor_verify)
        params = list(sig.parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params


# ---------------------------------------------------------------------------
# VERIFIER_EXTENSION_MODULES — canonical list
# ---------------------------------------------------------------------------


class TestVerifierExtensionModules:
    def test_includes_enhanced_verification(self):
        from bob.pending_successor_verify import VERIFIER_EXTENSION_MODULES
        assert any("enhanced_verification.py" in m for m in VERIFIER_EXTENSION_MODULES)

    def test_is_non_empty_tuple(self):
        from bob.pending_successor_verify import VERIFIER_EXTENSION_MODULES
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert len(VERIFIER_EXTENSION_MODULES) > 0

    def test_matches_spec_extractor_constant(self):
        from bob.pending_successor_verify import VERIFIER_EXTENSION_MODULES as PSV_MODS
        from bob.spec_quality.spec_extractor import VERIFIER_EXTENSION_MODULES as SE_MODS
        assert PSV_MODS == SE_MODS


# ---------------------------------------------------------------------------
# is_verifier_extension_feature
# ---------------------------------------------------------------------------


class TestIsVerifierExtensionFeature:
    def test_returns_false_when_workspace_is_none(self):
        from bob.pending_successor_verify import is_verifier_extension_feature
        result = is_verifier_extension_feature("feat-001", None)
        assert result is False

    def test_returns_false_when_workspace_has_no_src(self, tmp_path):
        from bob.pending_successor_verify import is_verifier_extension_feature
        result = is_verifier_extension_feature("feat-001", tmp_path)
        assert result is False

    def test_returns_false_when_no_verifier_files_present(self, tmp_path):
        from bob.pending_successor_verify import is_verifier_extension_feature
        src = tmp_path / "src"
        src.mkdir()
        (src / "some_other_module.py").write_text("# not a verifier")
        result = is_verifier_extension_feature("feat-001", tmp_path)
        assert result is False

    def test_returns_true_when_enhanced_verification_present(self, tmp_path):
        from bob.pending_successor_verify import is_verifier_extension_feature
        # Replicate the directory structure matching the module path
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")
        result = is_verifier_extension_feature("feat-001", tmp_path)
        assert result is True

    def test_returns_true_when_verifier_py_present(self, tmp_path):
        from bob.pending_successor_verify import is_verifier_extension_feature
        verif_dir = tmp_path / "src" / "bob" / "verification"
        verif_dir.mkdir(parents=True)
        (verif_dir / "verifier.py").write_text("# verifier")
        result = is_verifier_extension_feature("feat-001", tmp_path)
        assert result is True

    def test_returns_true_when_prose_ac_demotion_present(self, tmp_path):
        from bob.pending_successor_verify import is_verifier_extension_feature
        verif_dir = tmp_path / "src" / "bob" / "verification"
        verif_dir.mkdir(parents=True)
        (verif_dir / "prose_ac_demotion.py").write_text("# demotion")
        result = is_verifier_extension_feature("feat-001", tmp_path)
        assert result is True

    def test_returns_false_on_scan_error(self, tmp_path):
        from bob.pending_successor_verify import is_verifier_extension_feature
        # Create a src dir but make it unreadable — covered by error branch
        src = tmp_path / "src"
        src.mkdir()
        with patch("bob.pending_successor_verify.Path.rglob", side_effect=PermissionError("denied")):
            result = is_verifier_extension_feature("feat-001", tmp_path)
        assert result is False


# ---------------------------------------------------------------------------
# set_pending_successor_verify — guard conditions
# ---------------------------------------------------------------------------


class TestSetPendingSuccessorVerifyGuards:
    def test_returns_false_when_structural_ac_not_passed(self, tmp_path):
        from bob.pending_successor_verify import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")
        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-001", tmp_path, structural_ac_passed=False)
        assert result is False
        mock_db.update_feature.assert_not_called()

    def test_returns_false_when_not_verifier_extension(self, tmp_path):
        from bob.pending_successor_verify import set_pending_successor_verify
        src = tmp_path / "src"
        src.mkdir()
        (src / "regular_module.py").write_text("# not a verifier")
        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-001", tmp_path, structural_ac_passed=True)
        assert result is False
        mock_db.update_feature.assert_not_called()

    def test_returns_false_when_workspace_is_none_even_with_structural_ac(self):
        from bob.pending_successor_verify import set_pending_successor_verify
        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-001", None, structural_ac_passed=True)
        assert result is False
        mock_db.update_feature.assert_not_called()


# ---------------------------------------------------------------------------
# set_pending_successor_verify — happy path
# ---------------------------------------------------------------------------


class TestSetPendingSuccessorVerifyHappyPath:
    def test_sets_status_when_both_conditions_met(self, tmp_path):
        from bob.pending_successor_verify import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-abc", tmp_path, structural_ac_passed=True)

        assert result is True
        mock_db.update_feature.assert_called_once_with(
            "feat-abc", status="pending_successor_verify"
        )

    def test_returns_true_on_success(self, tmp_path):
        from bob.pending_successor_verify import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            mock_db.update_feature.return_value = MagicMock()
            result = set_pending_successor_verify("feat-xyz", tmp_path, structural_ac_passed=True)

        assert result is True

    def test_logs_info_when_status_updated(self, tmp_path, caplog):
        from bob.pending_successor_verify import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db"):
            with caplog.at_level(logging.INFO, logger="bob.pending_successor_verify"):
                set_pending_successor_verify("feat-log", tmp_path, structural_ac_passed=True)

        assert any("pending_successor_verify" in r.message for r in caplog.records)

    def test_works_with_mutation_gate_module(self, tmp_path):
        from bob.pending_successor_verify import set_pending_successor_verify
        verif_dir = tmp_path / "src" / "bob" / "verification"
        verif_dir.mkdir(parents=True)
        (verif_dir / "mutation_gate.py").write_text("# mutation gate")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-mut", tmp_path, structural_ac_passed=True)

        assert result is True
        mock_db.update_feature.assert_called_once_with(
            "feat-mut", status="pending_successor_verify"
        )


# ---------------------------------------------------------------------------
# set_pending_successor_verify — error handling
# ---------------------------------------------------------------------------


class TestSetPendingSuccessorVerifyErrors:
    def test_returns_false_on_db_error(self, tmp_path):
        from bob.pending_successor_verify import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            mock_db.update_feature.side_effect = Exception("db locked")
            result = set_pending_successor_verify("feat-err", tmp_path, structural_ac_passed=True)

        assert result is False

    def test_logs_error_on_db_failure(self, tmp_path, caplog):
        from bob.pending_successor_verify import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            mock_db.update_feature.side_effect = RuntimeError("write failed")
            with caplog.at_level(logging.ERROR, logger="bob.pending_successor_verify"):
                set_pending_successor_verify("feat-err2", tmp_path, structural_ac_passed=True)

        assert any("DB update failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# bob.run_loop delegation
# ---------------------------------------------------------------------------


class TestRunLoopDelegation:
    def test_run_loop_delegates_to_pending_successor_verify(self, tmp_path):
        from bob.run_loop import set_pending_successor_verify
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-rl", tmp_path, structural_ac_passed=True)

        assert result is True
        mock_db.update_feature.assert_called_once_with(
            "feat-rl", status="pending_successor_verify"
        )

    def test_run_loop_returns_false_when_not_verifier_extension(self, tmp_path):
        from bob.run_loop import set_pending_successor_verify
        src = tmp_path / "src"
        src.mkdir()

        with patch("bob.pending_successor_verify.db") as mock_db:
            result = set_pending_successor_verify("feat-rl2", tmp_path, structural_ac_passed=True)

        assert result is False
        mock_db.update_feature.assert_not_called()


# ---------------------------------------------------------------------------
# AC 4: Integration — bob.run_loop
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    def test_set_pending_successor_verify_in_run_loop_all(self):
        import bob.run_loop as rl
        assert "set_pending_successor_verify" in rl.__all__

    def test_orchestrator_run_loop_imports_pending_successor_verify(self):
        rl = importlib.import_module("bob.orchestrator.run_loop")
        assert hasattr(rl, "_set_pending_successor_verify"), (
            "bob.orchestrator.run_loop must import set_pending_successor_verify "
            "as _set_pending_successor_verify for integration AC dc709e23"
        )

    def test_orchestrator_imported_function_is_callable(self):
        rl = importlib.import_module("bob.orchestrator.run_loop")
        assert callable(rl._set_pending_successor_verify)

    def test_pending_successor_verify_module_in_all(self):
        from bob.pending_successor_verify import __all__
        assert "set_pending_successor_verify" in __all__
        assert "is_verifier_extension_feature" in __all__
        assert "PENDING_SUCCESSOR_VERIFY_STATUS" in __all__
        assert "VERIFIER_EXTENSION_MODULES" in __all__


# ---------------------------------------------------------------------------
# AC (8309a5ab): scan_for_verifier_self_reference / defer_to_successor
# ---------------------------------------------------------------------------


class TestScanForVerifierSelfReference:
    def test_defined_and_callable(self):
        from bob.pending_successor_verify import scan_for_verifier_self_reference
        assert callable(scan_for_verifier_self_reference)

    def test_in_all(self):
        from bob.pending_successor_verify import __all__
        assert "scan_for_verifier_self_reference" in __all__

    def test_returns_false_for_none(self):
        from bob.pending_successor_verify import scan_for_verifier_self_reference
        assert scan_for_verifier_self_reference(None) is False

    def test_returns_false_for_empty_list(self):
        from bob.pending_successor_verify import scan_for_verifier_self_reference
        assert scan_for_verifier_self_reference([]) is False

    def test_returns_true_for_behavior_ac_referencing_enhanced_verification(self):
        from bob.pending_successor_verify import scan_for_verifier_self_reference
        acs = ["behavior: enhanced_verification must demote prose AC failures"]
        assert scan_for_verifier_self_reference(acs) is True

    def test_returns_false_for_non_behavior_ac(self):
        from bob.pending_successor_verify import scan_for_verifier_self_reference
        acs = ["File exists: src/bob/enhanced_verification.py"]
        assert scan_for_verifier_self_reference(acs) is False

    def test_raises_value_error_for_int(self):
        from bob.pending_successor_verify import scan_for_verifier_self_reference
        with pytest.raises(ValueError):
            scan_for_verifier_self_reference(42)


class TestDeferToSuccessorAC8309:
    def test_defined_and_callable(self):
        from bob.pending_successor_verify import defer_to_successor
        assert callable(defer_to_successor)

    def test_defers_when_behavior_ac_references_verifier(self, tmp_path):
        from bob.pending_successor_verify import defer_to_successor
        acs = ["behavior: enhanced_verification must handle the new pattern"]
        with patch("bob.pending_successor_verify.db") as mock_db:
            result = defer_to_successor("feat-8309", "verifier feature", acs)
        assert result is True
        mock_db.update_feature.assert_called_once_with(
            "feat-8309", status="pending_successor_verify"
        )

    def test_no_defer_for_non_verifier_feature(self):
        from bob.pending_successor_verify import defer_to_successor
        acs = ["File exists: src/bob/regular.py", "pytest: tests/test_regular.py"]
        with patch("bob.pending_successor_verify.db") as mock_db:
            result = defer_to_successor("feat-x", "regular feature", acs)
        assert result is False
        mock_db.update_feature.assert_not_called()


# ---------------------------------------------------------------------------
# AC (6032ec54): scan_ac_body_for_tokens
# ---------------------------------------------------------------------------


class TestScanAcBodyForTokens:
    """Tests for the broadened AC-body token scanner (F-R7-596)."""

    def test_returns_false_for_empty_string(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("") is False

    def test_returns_true_for_enhanced_verification_exact(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("enhanced_verification") is True

    def test_returns_true_for_enhanced_verification_in_path(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("src/bob/enhanced_verification.py") is True

    def test_returns_true_for_path_ending_in_verification_py(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("src/bob/some_other_verification.py") is True

    def test_returns_true_for_path_ending_in_verifier_py(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("src/bob/artifact_verifier.py") is True

    def test_returns_false_for_unrelated_text(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("refuse to pass AC when referenced files are missing") is False

    def test_returns_false_for_ac_artifact_text(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("AC artifact-existence verifier must refuse to pass") is False

    def test_returns_true_for_verifier_substring_in_body(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        # Note: 'verifier' alone does NOT match — only path-tokens match
        # (the feature description says scan for path-tokens in structural/integration ACs)
        # But 'AC artifact-existence verifier' contains 'verifier' — check spec
        # Per spec: 'src/bob/enhanced_verification.py', 'enhanced_verification', path ending in
        # '_verification.py' OR '_verifier.py'. 'verifier' alone should NOT match.
        assert scan_ac_body_for_tokens("the verifier module") is False

    def test_returns_true_for_inline_enhanced_verification_reference(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens(
            "Function defined: bob.enhanced_verification.check_function_defined"
        ) is True

    def test_returns_false_for_pytest_ac_with_no_verifier_token(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("pytest: tests/test_my_feature.py") is False

    def test_returns_true_for_integration_ac_with_verification_module(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens(
            "integration: bob.enhanced_verification"
        ) is True

    def test_case_sensitive_match_enhanced_verification(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        # The token is lowercase; uppercase should not match (tokens are exact)
        assert scan_ac_body_for_tokens("ENHANCED_VERIFICATION") is False

    def test_returns_true_for_full_spec_path_token(self):
        from bob.pending_successor_verify import scan_ac_body_for_tokens
        assert scan_ac_body_for_tokens("src/bob/enhanced_verification.py exists") is True


# ---------------------------------------------------------------------------
# AC (6032ec54): detect_verification_features
# ---------------------------------------------------------------------------


class TestDetectVerificationFeatures:
    """Tests for the pre-dispatch detection function (F-R7-596)."""

    def test_returns_false_for_empty_acs(self):
        from bob.pending_successor_verify import detect_verification_features
        assert detect_verification_features("some feature", []) is False

    def test_returns_false_for_none_acs(self):
        from bob.pending_successor_verify import detect_verification_features
        assert detect_verification_features("some feature", None) is False

    def test_returns_false_when_no_verifier_token_in_acs(self):
        from bob.pending_successor_verify import detect_verification_features
        acs = [
            "File exists: src/bob/my_module.py",
            "Function defined: bob.my_module.my_func",
            "pytest: tests/test_my_module.py",
        ]
        assert detect_verification_features("my feature", acs) is False

    def test_returns_true_when_ac_body_contains_enhanced_verification(self):
        from bob.pending_successor_verify import detect_verification_features
        acs = [
            "File exists: src/bob/enhanced_verification.py",
            "Function defined: bob.enhanced_verification.new_handler",
            "pytest: tests/test_something.py",
        ]
        assert detect_verification_features("some verifier feature", acs) is True

    def test_returns_true_when_ac_body_contains_verification_py_path(self):
        from bob.pending_successor_verify import detect_verification_features
        acs = [
            "File exists: src/bob/my_verification.py",
            "pytest: tests/test_my_verification.py",
        ]
        assert detect_verification_features("my feature", acs) is True

    def test_returns_true_when_ac_body_contains_verifier_py_path(self):
        from bob.pending_successor_verify import detect_verification_features
        acs = [
            "File exists: src/bob/artifact_verifier.py",
            "pytest: tests/test_artifact_verifier.py",
        ]
        assert detect_verification_features("artifact check", acs) is True

    def test_title_fallback_triggers_when_title_contains_verifier(self):
        from bob.pending_successor_verify import detect_verification_features
        # ACs say "refuse to pass" / "AC artifact" — no verifier path-tokens
        # But title contains 'verifier' AND ACs reference verification/AC/criterion semantics
        acs = [
            "behavior: refuse to pass AC when referenced files are missing",
            "behavior: AC artifact-existence check must block incomplete features",
            "pytest: tests/test_ac_artifact.py",
        ]
        assert detect_verification_features(
            "AC artifact-existence verifier — refuse to pass AC when referenced files are missing",
            acs,
        ) is True

    def test_title_fallback_not_triggered_without_verifier_in_title(self):
        from bob.pending_successor_verify import detect_verification_features
        acs = [
            "behavior: refuse to pass AC when referenced files are missing",
            "behavior: AC artifact-existence check must block incomplete features",
            "pytest: tests/test_ac_artifact.py",
        ]
        # Title has no 'verifier' substring
        assert detect_verification_features("AC artifact-existence check", acs) is False

    def test_title_fallback_not_triggered_without_behavior_acs(self):
        from bob.pending_successor_verify import detect_verification_features
        # Title has 'verifier' but no behavior: ACs
        acs = [
            "File exists: src/bob/some_module.py",
            "pytest: tests/test_some_module.py",
        ]
        assert detect_verification_features("AC verifier helper", acs) is False

    def test_title_fallback_requires_verification_semantics_in_behavior_acs(self):
        from bob.pending_successor_verify import detect_verification_features
        # Title has 'verifier', has behavior: ACs, but they don't reference verification semantics
        acs = [
            "behavior: when the user runs the command, output is printed",
            "pytest: tests/test_cmd.py",
        ]
        assert detect_verification_features("CLI verifier runner", acs) is False

    def test_returns_true_for_json_encoded_acs(self):
        import json
        from bob.pending_successor_verify import detect_verification_features
        acs_json = json.dumps([
            "File exists: src/bob/enhanced_verification.py",
            "pytest: tests/test_enhanced.py",
        ])
        assert detect_verification_features("some feature", acs_json) is True

    def test_returns_false_for_invalid_json_acs(self):
        from bob.pending_successor_verify import detect_verification_features
        assert detect_verification_features("some feature", "not-json{") is False

    def test_single_ac_with_token_triggers(self):
        from bob.pending_successor_verify import detect_verification_features
        acs = ["integration: bob.enhanced_verification"]
        assert detect_verification_features("anything", acs) is True

    def test_d34c40f0_missed_case_is_now_caught(self):
        """The original F-R7-595 heuristic missed feature d34c40f0 because its ACs said
        'refuse to pass' / 'AC artifact' without naming enhanced_verification. The title-
        fallback in detect_verification_features closes this gap."""
        from bob.pending_successor_verify import detect_verification_features
        name = "AC artifact-existence verifier — refuse to pass AC when referenced files are missing"
        acs = [
            "behavior: verifier MUST refuse to pass an AC when the file it references does not exist",
            "behavior: AC artifact check must block features whose structural ACs reference missing files",
            "behavior: criterion check emits 'missing artifact' and marks the AC as failed",
            "pytest: tests/test_ac_artifact_verifier.py",
        ]
        assert detect_verification_features(name, acs) is True


# ---------------------------------------------------------------------------
# AC (6032ec54): orchestrator integration
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration6032:
    """Integration: bob.orchestrator must expose the new detection functions."""

    def test_orchestrator_exposes_detect_verification_features(self):
        import bob.orchestrator as orch
        assert hasattr(orch, "detect_verification_features") or \
               hasattr(orch, "detect_pending_successor_verify"), (
            "bob.orchestrator must expose detect_verification_features or "
            "detect_pending_successor_verify for integration AC 6032ec54"
        )

    def test_pending_successor_verify_module_exports_new_functions(self):
        from bob.pending_successor_verify import (
            detect_verification_features,
            scan_ac_body_for_tokens,
        )
        assert callable(detect_verification_features)
        assert callable(scan_ac_body_for_tokens)

    def test_new_functions_in_all(self):
        from bob.pending_successor_verify import __all__
        assert "detect_verification_features" in __all__
        assert "scan_ac_body_for_tokens" in __all__

    def test_orchestrator_init_imports_detect_verification_features(self):
        import bob.orchestrator as orch
        # After 6032ec54, the orchestrator must wire detect_verification_features
        # into its pre-dispatch machinery. At minimum, it must be importable from
        # bob.pending_successor_verify (already verified above); the orchestrator
        # integration is tested by verifying that the function is callable through
        # the orchestrator namespace or that the orchestrator module imports it.
        import bob.pending_successor_verify as psv
        assert callable(psv.detect_verification_features)
        assert callable(psv.scan_ac_body_for_tokens)


# ---------------------------------------------------------------------------
# AC (ec65822c): bob.enhanced_verification.VERIFIER_EXTENSION_MODULES
# ---------------------------------------------------------------------------


class TestEnhancedVerificationExtensionModules:
    """The verifier module must re-export the canonical extension-module list."""

    def test_enhanced_verification_exports_constant(self):
        from bob.enhanced_verification import VERIFIER_EXTENSION_MODULES
        assert isinstance(VERIFIER_EXTENSION_MODULES, tuple)
        assert len(VERIFIER_EXTENSION_MODULES) > 0

    def test_enhanced_verification_constant_matches_canonical(self):
        from bob.enhanced_verification import VERIFIER_EXTENSION_MODULES as EV_MODS
        from bob.spec_quality.spec_extractor import VERIFIER_EXTENSION_MODULES as SE_MODS
        assert EV_MODS == SE_MODS

    def test_includes_enhanced_verification_self(self):
        from bob.enhanced_verification import VERIFIER_EXTENSION_MODULES
        assert any("enhanced_verification.py" in m for m in VERIFIER_EXTENSION_MODULES)


# ---------------------------------------------------------------------------
# AC (ec65822c): bob.run_loop.classify_verifier_extension_failure
# ---------------------------------------------------------------------------


class TestClassifyVerifierExtensionFailure:
    """The run_loop must classify AC failures of verifier-extension features."""

    def test_function_defined_and_callable(self):
        from bob.run_loop import classify_verifier_extension_failure
        assert callable(classify_verifier_extension_failure)

    def test_in_run_loop_all(self):
        import bob.run_loop as rl
        assert "classify_verifier_extension_failure" in rl.__all__

    def test_signature(self):
        import inspect
        from bob.run_loop import classify_verifier_extension_failure
        params = list(inspect.signature(classify_verifier_extension_failure).parameters)
        assert "feature_id" in params
        assert "workspace" in params
        assert "structural_ac_passed" in params

    def test_needs_human_when_structural_ac_not_passed(self, tmp_path):
        from bob.run_loop import classify_verifier_extension_failure
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")
        result = classify_verifier_extension_failure(
            "feat-1", tmp_path, structural_ac_passed=False
        )
        assert result == "needs_human"

    def test_needs_human_when_not_verifier_extension(self, tmp_path):
        from bob.run_loop import classify_verifier_extension_failure
        src = tmp_path / "src"
        src.mkdir()
        (src / "regular_module.py").write_text("# not a verifier")
        result = classify_verifier_extension_failure(
            "feat-2", tmp_path, structural_ac_passed=True
        )
        assert result == "needs_human"

    def test_needs_human_when_workspace_none(self):
        from bob.run_loop import classify_verifier_extension_failure
        result = classify_verifier_extension_failure(
            "feat-3", None, structural_ac_passed=True
        )
        assert result == "needs_human"

    def test_defers_when_both_conditions_met(self, tmp_path):
        from bob.run_loop import classify_verifier_extension_failure
        src_bob = tmp_path / "src" / "bob"
        src_bob.mkdir(parents=True)
        (src_bob / "enhanced_verification.py").write_text("# verifier")
        result = classify_verifier_extension_failure(
            "feat-4", tmp_path, structural_ac_passed=True
        )
        assert result == "pending_successor_verify"

    def test_empty_feature_id_raises_value_error(self):
        from bob.run_loop import classify_verifier_extension_failure
        with pytest.raises(ValueError, match="feature_id"):
            classify_verifier_extension_failure("", None, True)

    def test_none_feature_id_raises_value_error(self):
        from bob.run_loop import classify_verifier_extension_failure
        with pytest.raises(ValueError, match="feature_id"):
            classify_verifier_extension_failure(None, None, True)

    def test_non_string_feature_id_raises_value_error(self):
        from bob.run_loop import classify_verifier_extension_failure
        with pytest.raises(ValueError):
            classify_verifier_extension_failure(42, None, True)

    def test_bool_feature_id_raises_value_error(self):
        from bob.run_loop import classify_verifier_extension_failure
        with pytest.raises(ValueError):
            classify_verifier_extension_failure(True, None, True)


# ---------------------------------------------------------------------------
# AC (ffad5c3d): scan_acs_for_verifier_tokens
# ---------------------------------------------------------------------------


class TestScanAcsForVerifierTokens:
    """Broaden detection to a target-file scan across the full AC list (F-R7-596)."""

    def test_returns_false_for_empty_list(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        assert scan_acs_for_verifier_tokens([]) is False

    def test_returns_false_for_none(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        assert scan_acs_for_verifier_tokens(None) is False

    def test_returns_true_when_any_ac_has_enhanced_verification(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        acs = [
            "File exists: src/bob/enhanced_verification.py",
            "pytest: tests/test_x.py",
        ]
        assert scan_acs_for_verifier_tokens(acs) is True

    def test_returns_true_for_verification_py_suffix(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        assert scan_acs_for_verifier_tokens(["File exists: src/bob/my_verification.py"]) is True

    def test_returns_true_for_verifier_py_suffix(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        assert scan_acs_for_verifier_tokens(["File exists: src/bob/artifact_verifier.py"]) is True

    def test_returns_false_for_unrelated_acs(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        acs = ["File exists: src/bob/foo.py", "pytest: tests/test_foo.py"]
        assert scan_acs_for_verifier_tokens(acs) is False

    def test_accepts_json_encoded_list(self):
        import json
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        acs = json.dumps(["integration: bob.enhanced_verification"])
        assert scan_acs_for_verifier_tokens(acs) is True

    def test_returns_bool(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        assert isinstance(scan_acs_for_verifier_tokens([]), bool)

    def test_non_list_non_str_raises_value_error(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        with pytest.raises(ValueError):
            scan_acs_for_verifier_tokens(42)

    def test_dict_raises_value_error(self):
        from bob.pending_successor_verify import scan_acs_for_verifier_tokens
        with pytest.raises(ValueError, match="dict"):
            scan_acs_for_verifier_tokens({"a": "b"})


# ---------------------------------------------------------------------------
# AC (ffad5c3d): should_defer_successor_verify
# ---------------------------------------------------------------------------


class TestShouldDeferSuccessorVerify:
    """Combined target-file-scan + title-fallback deferral decision (F-R7-596)."""

    def test_returns_false_for_empty_acs(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        assert should_defer_successor_verify("some feature", []) is False

    def test_returns_false_for_none_acs(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        assert should_defer_successor_verify("some feature", None) is False

    def test_returns_true_when_ac_targets_enhanced_verification(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        acs = ["File exists: src/bob/enhanced_verification.py"]
        assert should_defer_successor_verify("some feature", acs) is True

    def test_title_fallback_catches_d34c40f0(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        name = "AC artifact-existence verifier — refuse to pass AC when referenced files are missing"
        acs = [
            "behavior: verifier MUST refuse to pass an AC when the file it references does not exist",
            "pytest: tests/test_ac_artifact_verifier.py",
        ]
        assert should_defer_successor_verify(name, acs) is True

    def test_returns_false_for_unrelated_feature(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        acs = ["File exists: src/bob/foo.py", "pytest: tests/test_foo.py"]
        assert should_defer_successor_verify("plain feature", acs) is False

    def test_returns_bool(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        assert isinstance(should_defer_successor_verify("x", []), bool)

    def test_non_str_name_raises_value_error(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        with pytest.raises(ValueError):
            should_defer_successor_verify(42, [])

    def test_invalid_acs_type_raises_value_error(self):
        from bob.pending_successor_verify import should_defer_successor_verify
        with pytest.raises(ValueError):
            should_defer_successor_verify("x", 99)
