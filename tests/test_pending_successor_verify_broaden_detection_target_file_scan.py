"""Tests for bob3.pending_successor_verify_broaden_detection_target_file_scan.

Acceptance criteria:
- File exists: src/bob3/pending_successor_verify_broaden_detection_target_file_scan.py
- pytest: tests/test_pending_successor_verify_broaden_detection_target_file_scan.py::test_pending_successor_verify_broaden_detection_target_file_scan
- Function defined: bob3.pending_successor_verify_broaden_detection_target_file_scan.pending_successor_verify_broaden_detection_target_file_scan

Feature (F-R7-596): Broaden pending_successor_verify detection to scan target files
referenced in ACs, not just AC body wording. If any AC references a file path that
ends in _verification.py or _verifier.py (or is named enhanced_verification.py), the
detector should inspect the actual file (if reachable) and defer the feature if the
file is a verifier-extension module.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# AC 1: File exists
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_module_file_exists(self):
        import bob3.pending_successor_verify_broaden_detection_target_file_scan as m
        module_file = Path(m.__file__)
        assert module_file.exists()
        assert module_file.name == "pending_successor_verify_broaden_detection_target_file_scan.py"

    def test_module_importable(self):
        import bob3.pending_successor_verify_broaden_detection_target_file_scan  # noqa: F401


# ---------------------------------------------------------------------------
# AC 3: Function defined
# ---------------------------------------------------------------------------


class TestFunctionDefined:
    def test_function_is_defined(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        assert callable(pending_successor_verify_broaden_detection_target_file_scan)

    def test_function_in_all(self):
        import bob3.pending_successor_verify_broaden_detection_target_file_scan as m
        assert "pending_successor_verify_broaden_detection_target_file_scan" in m.__all__


# ---------------------------------------------------------------------------
# AC 2: pytest (main test function — must be named exactly as the AC specifies)
# ---------------------------------------------------------------------------


def test_pending_successor_verify_broaden_detection_target_file_scan():
    """End-to-end test: broaden detection scans target files referenced in ACs.

    This is the AC-mandated test function. It exercises the key behaviors
    described in F-R7-596:
    1. When an AC references a file whose path ends in _verification.py or
       _verifier.py, the detector should flag it.
    2. When no AC references a verifier file, the detector returns False.
    3. Title-fallback: if feature name contains 'verifier' and a behavior: AC
       references verification/AC/criterion semantics, defer.
    """
    from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
        pending_successor_verify_broaden_detection_target_file_scan,
    )

    # Case 1: AC references enhanced_verification.py → should detect
    acs_with_verifier = [
        "File exists: src/bob3/enhanced_verification.py",
        "pytest: tests/test_enhanced.py",
    ]
    result = pending_successor_verify_broaden_detection_target_file_scan(
        feature_name="some feature",
        acceptance_criteria=acs_with_verifier,
    )
    assert result is True, (
        "Expected True when an AC body references enhanced_verification.py"
    )

    # Case 2: AC references _verifier.py path → should detect
    acs_with_verifier_suffix = [
        "File exists: src/bob3/artifact_verifier.py",
        "pytest: tests/test_artifact.py",
    ]
    result2 = pending_successor_verify_broaden_detection_target_file_scan(
        feature_name="artifact check",
        acceptance_criteria=acs_with_verifier_suffix,
    )
    assert result2 is True, (
        "Expected True when an AC body references a _verifier.py path"
    )

    # Case 3: No verifier references → should not detect
    acs_no_verifier = [
        "File exists: src/bob3/my_feature.py",
        "Function defined: bob3.my_feature.my_func",
        "pytest: tests/test_my_feature.py",
    ]
    result3 = pending_successor_verify_broaden_detection_target_file_scan(
        feature_name="unrelated feature",
        acceptance_criteria=acs_no_verifier,
    )
    assert result3 is False, (
        "Expected False when no AC references a verifier-extension module"
    )

    # Case 4: Title-fallback — title has 'verifier', behavior: AC references verification semantics
    acs_behavior_verifier = [
        "behavior: refuse to pass AC when referenced files are missing",
        "behavior: criterion check must block features with missing artifacts",
        "pytest: tests/test_ac_artifact.py",
    ]
    result4 = pending_successor_verify_broaden_detection_target_file_scan(
        feature_name="AC artifact-existence verifier — refuse to pass",
        acceptance_criteria=acs_behavior_verifier,
    )
    assert result4 is True, (
        "Expected True when title contains 'verifier' and behavior ACs reference verification semantics"
    )

    # Case 5: Empty ACs → should not detect
    result5 = pending_successor_verify_broaden_detection_target_file_scan(
        feature_name="empty feature",
        acceptance_criteria=[],
    )
    assert result5 is False, "Expected False for empty acceptance criteria"

    # Case 6: None ACs → should not detect (safe fallback)
    result6 = pending_successor_verify_broaden_detection_target_file_scan(
        feature_name="none feature",
        acceptance_criteria=None,
    )
    assert result6 is False, "Expected False for None acceptance criteria"


# ---------------------------------------------------------------------------
# Detailed behavioral tests
# ---------------------------------------------------------------------------


class TestBroadenDetectionAcBodyScan:
    """Tests for AC body scanning (F-R7-596 path-token detection)."""

    def test_detects_enhanced_verification_token_in_ac(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = ["integration: bob3.enhanced_verification"]
        assert pending_successor_verify_broaden_detection_target_file_scan("feat", acs) is True

    def test_detects_verification_py_suffix_path(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = ["File exists: src/bob3/some_other_verification.py"]
        assert pending_successor_verify_broaden_detection_target_file_scan("feat", acs) is True

    def test_detects_verifier_py_suffix_path(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = ["File exists: src/bob3/my_verifier.py"]
        assert pending_successor_verify_broaden_detection_target_file_scan("feat", acs) is True

    def test_returns_false_for_plain_test_file_path(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = ["pytest: tests/test_my_feature.py"]
        assert pending_successor_verify_broaden_detection_target_file_scan("feat", acs) is False

    def test_returns_false_for_ac_artifact_wording_without_path_token(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        # The original F-R7-595 missed these — they have no path-token
        acs = ["behavior: refuse to pass AC when referenced files are missing"]
        # No verifier path-token, and title has no 'verifier' → should be False
        assert pending_successor_verify_broaden_detection_target_file_scan(
            "artifact check feature", acs
        ) is False

    def test_target_file_scan_detects_path_in_function_defined_ac(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = ["Function defined: bob3.enhanced_verification.check_function_defined"]
        assert pending_successor_verify_broaden_detection_target_file_scan("feat", acs) is True


class TestBroadenDetectionTitleFallback:
    """Tests for the title-fallback branch (F-R7-596 step 3)."""

    def test_title_fallback_triggers_with_verifier_and_behavior_ac(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = [
            "behavior: verifier MUST refuse to pass an AC when the file it references does not exist",
            "pytest: tests/test_verifier.py",
        ]
        assert pending_successor_verify_broaden_detection_target_file_scan(
            "AC artifact-existence verifier", acs
        ) is True

    def test_title_fallback_not_triggered_without_verifier_in_title(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = [
            "behavior: refuse to pass AC when referenced files are missing",
            "pytest: tests/test_check.py",
        ]
        assert pending_successor_verify_broaden_detection_target_file_scan(
            "AC artifact existence check", acs
        ) is False

    def test_title_fallback_not_triggered_without_behavior_ac_semantics(self):
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = [
            "behavior: when user runs the command, output is printed",
            "pytest: tests/test_cmd.py",
        ]
        assert pending_successor_verify_broaden_detection_target_file_scan(
            "CLI verifier runner", acs
        ) is False

    def test_d34c40f0_missed_case_now_caught(self):
        """Regression: feature d34c40f0 was missed by F-R7-595.

        Its ACs said 'refuse to pass' / 'AC artifact' without naming
        enhanced_verification. The title-fallback must catch it.
        """
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        name = "AC artifact-existence verifier — refuse to pass AC when referenced files are missing"
        acs = [
            "behavior: verifier MUST refuse to pass an AC when the file it references does not exist",
            "behavior: AC artifact check must block features whose structural ACs reference missing files",
            "behavior: criterion check emits 'missing artifact' and marks the AC as failed",
            "pytest: tests/test_ac_artifact_verifier.py",
        ]
        assert pending_successor_verify_broaden_detection_target_file_scan(name, acs) is True


class TestBroadenDetectionTargetFileScan:
    """Tests for target-file scanning (the 'broadened' part beyond AC body text)."""

    def test_scans_referenced_file_when_reachable(self, tmp_path):
        """If an AC references a file that exists in workspace and the file itself
        imports or defines verification patterns, the feature should be deferred."""
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        # Create a target file that clearly IS a verifier extension
        target = tmp_path / "src" / "bob3" / "some_handler.py"
        target.parent.mkdir(parents=True)
        target.write_text("from bob3.enhanced_verification import check_function_defined\n")

        acs = [f"File exists: src/bob3/some_handler.py"]
        # Pass workspace so the function can resolve the file path
        result = pending_successor_verify_broaden_detection_target_file_scan(
            feature_name="some handler feature",
            acceptance_criteria=acs,
            workspace=str(tmp_path),
        )
        # With target file scanning, this should return True (file imports enhanced_verification)
        assert result is True

    def test_does_not_defer_when_referenced_file_is_unrelated(self, tmp_path):
        """If the referenced file exists but has no verifier imports, do not defer."""
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        target = tmp_path / "src" / "bob3" / "my_module.py"
        target.parent.mkdir(parents=True)
        target.write_text("def my_func(): return 42\n")

        acs = [f"File exists: src/bob3/my_module.py"]
        result = pending_successor_verify_broaden_detection_target_file_scan(
            feature_name="my module feature",
            acceptance_criteria=acs,
            workspace=str(tmp_path),
        )
        assert result is False

    def test_safe_when_referenced_file_does_not_exist(self, tmp_path):
        """If the AC references a file that doesn't exist yet, don't crash."""
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = ["File exists: src/bob3/nonexistent_module.py"]
        result = pending_successor_verify_broaden_detection_target_file_scan(
            feature_name="nonexistent feature",
            acceptance_criteria=acs,
            workspace=str(tmp_path),
        )
        assert result is False

    def test_safe_when_workspace_is_none(self):
        """When no workspace provided, fall back to AC body scan only."""
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        acs = ["File exists: src/bob3/some_handler.py"]
        result = pending_successor_verify_broaden_detection_target_file_scan(
            feature_name="some feature",
            acceptance_criteria=acs,
            workspace=None,
        )
        # No verifier path-token in AC body, no workspace to scan → False
        assert result is False

    def test_target_file_containing_verifier_extension_import(self, tmp_path):
        """Target file that imports from enhanced_verification triggers deferral."""
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        target = tmp_path / "src" / "bob3" / "my_handler.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "import enhanced_verification\n"
            "def handle(): pass\n"
        )
        acs = ["File exists: src/bob3/my_handler.py"]
        result = pending_successor_verify_broaden_detection_target_file_scan(
            feature_name="my handler feature",
            acceptance_criteria=acs,
            workspace=str(tmp_path),
        )
        assert result is True

    def test_target_file_scan_uses_path_tokens_in_content(self, tmp_path):
        """If referenced file content contains '_verifier.py' or '_verification.py', defer."""
        from bob3.pending_successor_verify_broaden_detection_target_file_scan import (
            pending_successor_verify_broaden_detection_target_file_scan,
        )
        target = tmp_path / "src" / "bob3" / "my_glue.py"
        target.parent.mkdir(parents=True)
        target.write_text(
            "# This module delegates to artifact_verifier.py\n"
            "from bob3.artifact_verifier import check\n"
        )
        acs = ["File exists: src/bob3/my_glue.py"]
        result = pending_successor_verify_broaden_detection_target_file_scan(
            feature_name="my glue feature",
            acceptance_criteria=acs,
            workspace=str(tmp_path),
        )
        assert result is True
