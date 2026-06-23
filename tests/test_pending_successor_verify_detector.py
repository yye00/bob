"""Tests for bob3.pending_successor_verify_detector.detect_pending_successor_verify.

Acceptance criteria (F-R7-596):
- File exists: src/bob3/pending_successor_verify_detector.py
- Function defined: bob3.pending_successor_verify_detector.detect_pending_successor_verify
- pytest: tests/test_pending_successor_verify_detector.py
- integration: bob3.orchestrator
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# AC 1: File exists
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_module_file_exists(self):
        import bob3.pending_successor_verify_detector as m

        module_file = Path(m.__file__)
        assert module_file.exists()
        assert module_file.name == "pending_successor_verify_detector.py"

    def test_module_importable(self):
        import bob3.pending_successor_verify_detector  # noqa: F401


# ---------------------------------------------------------------------------
# AC 2: Function defined
# ---------------------------------------------------------------------------


class TestFunctionDefined:
    def test_function_is_callable(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        assert callable(detect_pending_successor_verify)

    def test_function_in_all(self):
        import bob3.pending_successor_verify_detector as m

        assert "detect_pending_successor_verify" in m.__all__


# ---------------------------------------------------------------------------
# Core detection — AC body scan (F-R7-596 step 2)
# ---------------------------------------------------------------------------


class TestAcBodyScan:
    def test_detects_enhanced_verification_in_ac_body(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = ["File exists: src/bob3/enhanced_verification.py"]
        assert detect_pending_successor_verify("feat", acs) is True

    def test_detects_enhanced_verification_token_anywhere_in_body(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = ["integration: bob3.enhanced_verification"]
        assert detect_pending_successor_verify("feat", acs) is True

    def test_detects_verification_py_suffix(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = ["File exists: src/bob3/some_other_verification.py"]
        assert detect_pending_successor_verify("feat", acs) is True

    def test_detects_verifier_py_suffix(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = ["File exists: src/bob3/my_verifier.py"]
        assert detect_pending_successor_verify("feat", acs) is True

    def test_no_detection_for_plain_test_path(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = ["pytest: tests/test_my_feature.py"]
        assert detect_pending_successor_verify("feat", acs) is False

    def test_no_detection_for_unrelated_acs(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = [
            "File exists: src/bob3/my_feature.py",
            "Function defined: bob3.my_feature.my_func",
            "pytest: tests/test_my_feature.py",
        ]
        assert detect_pending_successor_verify("unrelated feature", acs) is False


# ---------------------------------------------------------------------------
# Target-file scan (F-R7-596 step 3)
# ---------------------------------------------------------------------------


class TestTargetFileScan:
    def test_detects_verifier_import_in_referenced_file(self, tmp_path):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        target = tmp_path / "src" / "bob3" / "some_handler.py"
        target.parent.mkdir(parents=True)
        target.write_text("from bob3.enhanced_verification import check_function_defined\n")

        acs = ["File exists: src/bob3/some_handler.py"]
        result = detect_pending_successor_verify("some handler", acs, workspace=str(tmp_path))
        assert result is True

    def test_no_detection_when_referenced_file_is_unrelated(self, tmp_path):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        target = tmp_path / "src" / "bob3" / "my_module.py"
        target.parent.mkdir(parents=True)
        target.write_text("def my_func(): return 42\n")

        acs = ["File exists: src/bob3/my_module.py"]
        result = detect_pending_successor_verify("my module", acs, workspace=str(tmp_path))
        assert result is False

    def test_safe_when_referenced_file_missing(self, tmp_path):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = ["File exists: src/bob3/nonexistent_module.py"]
        result = detect_pending_successor_verify("nonexistent", acs, workspace=str(tmp_path))
        assert result is False

    def test_skips_target_file_scan_when_workspace_none(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        # AC body has no verifier token and workspace is None → False
        acs = ["File exists: src/bob3/some_handler.py"]
        result = detect_pending_successor_verify("some feature", acs, workspace=None)
        assert result is False

    def test_detects_verifier_py_reference_in_file_content(self, tmp_path):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        target = tmp_path / "src" / "bob3" / "my_glue.py"
        target.parent.mkdir(parents=True)
        target.write_text("# delegates to artifact_verifier.py\nfrom bob3.artifact_verifier import check\n")

        acs = ["File exists: src/bob3/my_glue.py"]
        result = detect_pending_successor_verify("my glue feature", acs, workspace=str(tmp_path))
        assert result is True


# ---------------------------------------------------------------------------
# Title-fallback (F-R7-596 step 4)
# ---------------------------------------------------------------------------


class TestTitleFallback:
    def test_title_fallback_triggers_with_verifier_and_semantic_behavior_ac(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = [
            "behavior: verifier MUST refuse to pass an AC when the file it references does not exist",
            "pytest: tests/test_verifier.py",
        ]
        assert detect_pending_successor_verify("AC artifact-existence verifier", acs) is True

    def test_title_fallback_not_triggered_without_verifier_in_title(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = [
            "behavior: refuse to pass AC when referenced files are missing",
            "pytest: tests/test_check.py",
        ]
        assert detect_pending_successor_verify("AC artifact existence check", acs) is False

    def test_title_fallback_not_triggered_without_semantic_behavior_ac(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        acs = [
            "behavior: when user runs the command, output is printed",
            "pytest: tests/test_cmd.py",
        ]
        assert detect_pending_successor_verify("CLI verifier runner", acs) is False

    def test_d34c40f0_regression_now_caught(self):
        """Regression: feature d34c40f0 was missed by F-R7-595; title-fallback must catch it."""
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        name = "AC artifact-existence verifier — refuse to pass AC when referenced files are missing"
        acs = [
            "behavior: verifier MUST refuse to pass an AC when the file it references does not exist",
            "behavior: AC artifact check must block features whose structural ACs reference missing files",
            "behavior: criterion check emits 'missing artifact' and marks the AC as failed",
            "pytest: tests/test_ac_artifact_verifier.py",
        ]
        assert detect_pending_successor_verify(name, acs) is True


# ---------------------------------------------------------------------------
# Boundary and edge cases
# ---------------------------------------------------------------------------


class TestBoundary:
    def test_none_ac_returns_false(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        assert detect_pending_successor_verify("feat", None) is False

    def test_empty_list_returns_false(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        assert detect_pending_successor_verify("feat", []) is False

    def test_empty_string_returns_false(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        assert detect_pending_successor_verify("feat", "") is False

    def test_json_encoded_list_is_parsed(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        import json

        acs = json.dumps(["File exists: src/bob3/enhanced_verification.py"])
        assert detect_pending_successor_verify("feat", acs) is True

    def test_json_encoded_empty_list_returns_false(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        assert detect_pending_successor_verify("feat", "[]") is False

    def test_returns_bool(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        result = detect_pending_successor_verify("feat", [])
        assert isinstance(result, bool)

    def test_invalid_type_raises_value_error(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        with pytest.raises(ValueError):
            detect_pending_successor_verify("feat", 42)  # type: ignore[arg-type]

    def test_dict_raises_value_error(self):
        from bob3.pending_successor_verify_detector import detect_pending_successor_verify

        with pytest.raises(ValueError):
            detect_pending_successor_verify("feat", {"key": "val"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator re-exports detect_pending_successor_verify
# ---------------------------------------------------------------------------


class TestOrchestratorIntegration:
    def test_orchestrator_has_detect_pending_successor_verify(self):
        from bob3.orchestrator import detect_pending_successor_verify

        assert callable(detect_pending_successor_verify)

    def test_orchestrator_detect_returns_false_for_empty(self):
        from bob3.orchestrator import detect_pending_successor_verify

        assert detect_pending_successor_verify([]) is False

    def test_orchestrator_detect_returns_true_for_enhanced_verification_ac(self):
        from bob3.orchestrator import detect_pending_successor_verify

        assert detect_pending_successor_verify(
            ["behavior: enhanced_verification must handle the new pattern"]
        ) is True
