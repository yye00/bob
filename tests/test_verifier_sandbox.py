"""Tests for bob.orchestrator.verifier_sandbox.

Verifies that check_verifier_untouched correctly blocks diffs that touch
protected verifier modules for non-verifier features, while allowing them
for features tagged role=verifier.
"""
from __future__ import annotations

import pytest

from bob.orchestrator.verifier_sandbox import (
    SandboxResult,
    SandboxViolation,
    _extract_touched_paths,
    _feature_is_verifier,
    _is_protected,
    check_verifier_untouched,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_diff(*paths: str, mode: str = "modify") -> str:
    """Create a minimal unified diff that touches the given paths."""
    parts: list[str] = []
    for path in paths:
        parts.append(
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1,3 +1,4 @@\n"
            " existing line\n"
            "+new line added\n"
        )
    return "\n".join(parts)


SAFE_DIFF = _make_diff("src/bob/some_feature.py")
ENHANCED_VERIFICATION_DIFF = _make_diff("src/bob/enhanced_verification.py")
SUPERPOWERS_DIFF = _make_diff("src/bob/superpowers.py")
RUN_LOOP_DIFF = _make_diff("src/bob/orchestrator/run_loop.py")
MULTI_PROTECTED_DIFF = _make_diff(
    "src/bob/enhanced_verification.py",
    "src/bob/superpowers.py",
)
MIXED_DIFF = _make_diff("src/bob/new_feature.py", "src/bob/enhanced_verification.py")


# ---------------------------------------------------------------------------
# _extract_touched_paths
# ---------------------------------------------------------------------------


class TestExtractTouchedPaths:
    def test_single_file(self):
        paths = _extract_touched_paths(SAFE_DIFF)
        assert "src/bob/some_feature.py" in paths

    def test_multiple_files(self):
        paths = _extract_touched_paths(MULTI_PROTECTED_DIFF)
        assert "src/bob/enhanced_verification.py" in paths
        assert "src/bob/superpowers.py" in paths

    def test_deduplication(self):
        diff = SAFE_DIFF + SAFE_DIFF
        paths = _extract_touched_paths(diff)
        assert paths.count("src/bob/some_feature.py") == 1

    def test_empty_diff(self):
        paths = _extract_touched_paths("")
        assert paths == []

    def test_ignores_dev_null(self):
        diff = "diff --git a/new.py b/new.py\n--- /dev/null\n+++ b/new.py\n"
        paths = _extract_touched_paths(diff)
        assert "/dev/null" not in paths
        assert "new.py" in paths


# ---------------------------------------------------------------------------
# _is_protected
# ---------------------------------------------------------------------------


class TestIsProtected:
    def test_enhanced_verification(self):
        assert _is_protected("src/bob/enhanced_verification.py") is True

    def test_superpowers(self):
        assert _is_protected("src/bob/superpowers.py") is True

    def test_run_loop(self):
        assert _is_protected("src/bob/orchestrator/run_loop.py") is True

    def test_evaluator_file(self):
        assert _is_protected("src/bob/evaluator_agent.py") is True

    def test_safe_file(self):
        assert _is_protected("src/bob/some_feature.py") is False

    def test_safe_tests_file(self):
        assert _is_protected("tests/test_enhanced_verification.py") is False

    def test_windows_path_separators(self):
        assert _is_protected("src\\bob\\enhanced_verification.py") is True


# ---------------------------------------------------------------------------
# _feature_is_verifier
# ---------------------------------------------------------------------------


class TestFeatureIsVerifier:
    def test_role_verifier_in_name(self):
        assert _feature_is_verifier("role=verifier guard") is True

    def test_role_verifier_in_description(self):
        assert _feature_is_verifier("some feature", "tagged role=verifier") is True

    def test_role_verifier_case_insensitive(self):
        assert _feature_is_verifier("ROLE=VERIFIER guard") is True

    def test_verifier_sandbox_name(self):
        assert _feature_is_verifier("verifier_sandbox") is True

    def test_verifier_sandbox_space_name(self):
        assert _feature_is_verifier("Sandbox the verifier from feature commits") is True

    def test_non_verifier_feature(self):
        assert _feature_is_verifier("Add new cache layer", "Caches expensive queries") is False

    def test_plain_verifier_word_without_role_tag_not_enough(self):
        # The word "verifier" alone in a non-sandbox context should not grant access
        assert _feature_is_verifier("Improve the verifier output", "Prettify logs") is False


# ---------------------------------------------------------------------------
# check_verifier_untouched — allowed cases
# ---------------------------------------------------------------------------


class TestCheckVerifierUntouchedAllowed:
    def test_safe_diff_non_verifier_feature_allowed(self):
        result = check_verifier_untouched(SAFE_DIFF, "Add cache layer", "some description")
        assert result.allowed is True
        assert result.violations == []
        assert result.is_verifier_feature is False

    def test_protected_diff_verifier_feature_allowed(self):
        result = check_verifier_untouched(
            ENHANCED_VERIFICATION_DIFF,
            "Fix verifier check",
            "role=verifier infrastructure fix",
        )
        assert result.allowed is True
        assert result.is_verifier_feature is True

    def test_verifier_sandbox_itself_allowed(self):
        diff = _make_diff("src/bob/orchestrator/verifier_sandbox.py", "src/bob/enhanced_verification.py")
        result = check_verifier_untouched(
            diff,
            "Sandbox the verifier from feature commits",
            "Add a guard that rejects any diff touching verifier modules",
        )
        assert result.allowed is True

    def test_empty_diff_allowed(self):
        result = check_verifier_untouched("", "Some feature", "")
        assert result.allowed is True
        assert result.violations == []

    def test_role_verifier_in_name_allows_protected_diff(self):
        result = check_verifier_untouched(
            SUPERPOWERS_DIFF,
            "role=verifier: extend superpowers checks",
            "",
        )
        assert result.allowed is True


# ---------------------------------------------------------------------------
# check_verifier_untouched — blocked cases
# ---------------------------------------------------------------------------


class TestCheckVerifierUntouchedBlocked:
    def test_enhanced_verification_blocked_for_non_verifier(self):
        result = check_verifier_untouched(
            ENHANCED_VERIFICATION_DIFF,
            "Implement new feature X",
            "Adds X to the system",
        )
        assert result.allowed is False
        assert len(result.violations) == 1
        assert "enhanced_verification.py" in result.violations[0].path

    def test_superpowers_blocked_for_non_verifier(self):
        result = check_verifier_untouched(SUPERPOWERS_DIFF, "My feature", "desc")
        assert result.allowed is False
        assert any("superpowers.py" in v.path for v in result.violations)

    def test_run_loop_blocked_for_non_verifier(self):
        result = check_verifier_untouched(RUN_LOOP_DIFF, "My feature", "desc")
        assert result.allowed is False
        assert any("run_loop.py" in v.path for v in result.violations)

    def test_multiple_violations_reported(self):
        result = check_verifier_untouched(MULTI_PROTECTED_DIFF, "My feature", "desc")
        assert result.allowed is False
        assert len(result.violations) == 2

    def test_mixed_diff_blocked(self):
        result = check_verifier_untouched(MIXED_DIFF, "My feature", "desc")
        assert result.allowed is False
        violation_paths = [v.path for v in result.violations]
        assert any("enhanced_verification.py" in p for p in violation_paths)

    def test_message_contains_blocked_path(self):
        result = check_verifier_untouched(
            ENHANCED_VERIFICATION_DIFF, "My feature", "desc"
        )
        assert "BLOCKED" in result.message
        assert "enhanced_verification.py" in result.message

    def test_message_ok_when_allowed(self):
        result = check_verifier_untouched(SAFE_DIFF, "My feature", "desc")
        assert result.message == "OK"


# ---------------------------------------------------------------------------
# SandboxResult dataclass
# ---------------------------------------------------------------------------


class TestSandboxResult:
    def test_allowed_result_has_empty_violations(self):
        result = check_verifier_untouched(SAFE_DIFF, "Feature", "")
        assert isinstance(result, SandboxResult)
        assert result.violations == []

    def test_blocked_result_has_violations(self):
        result = check_verifier_untouched(ENHANCED_VERIFICATION_DIFF, "Feature", "")
        assert isinstance(result, SandboxResult)
        assert all(isinstance(v, SandboxViolation) for v in result.violations)

    def test_violation_has_path_and_reason(self):
        result = check_verifier_untouched(ENHANCED_VERIFICATION_DIFF, "Feature", "")
        v = result.violations[0]
        assert isinstance(v.path, str) and len(v.path) > 0
        assert isinstance(v.reason, str) and len(v.reason) > 0
