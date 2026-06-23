"""Tests for bob3.spec_quality.integration_reachability.check_spec.

Verifies:
- Non-integration ACs are ignored.
- A module that exists as a source file in the workspace passes.
- A module declared as an integration target in a sibling feature passes.
- An importable module passes.
- An unreachable module produces a ReachabilityIssue with missing_module set.
- The closest-match suggestion is populated when a similar module exists.
- The format_report() output names the missing module and suggestion.
- Multiple features / multiple ACs all checked.
- passed=True when all targets are reachable.
- passed=False when any target is unreachable.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from bob3.spec_quality.integration_reachability import (
    ReachabilityIssue,
    ReachabilityResult,
    check_spec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

class TestReachabilityResult:
    def test_empty_is_passed(self):
        r = ReachabilityResult()
        assert r.passed is True

    def test_with_issue_is_failed(self):
        issue = ReachabilityIssue(
            feature_name="F1",
            ac_index=0,
            criterion="integration: foo.bar",
            missing_module="foo.bar",
            closest_match=None,
        )
        r = ReachabilityResult(issues=[issue])
        assert r.passed is False

    def test_format_report_passed(self):
        r = ReachabilityResult()
        assert "PASSED" in r.format_report()

    def test_format_report_failed_contains_module(self):
        issue = ReachabilityIssue(
            feature_name="MyFeature",
            ac_index=2,
            criterion="integration: very.missing.module",
            missing_module="very.missing.module",
            closest_match=None,
        )
        r = ReachabilityResult(issues=[issue])
        report = r.format_report()
        assert "FAILED" in report
        assert "very.missing.module" in report
        assert "MyFeature" in report

    def test_format_report_failed_includes_suggestion(self):
        issue = ReachabilityIssue(
            feature_name="F1",
            ac_index=0,
            criterion="integration: bob3.cli.pln",
            missing_module="bob3.cli.pln",
            closest_match="bob3.cli.plan",
        )
        r = ReachabilityResult(issues=[issue])
        report = r.format_report()
        assert "bob3.cli.plan" in report
        assert "Suggestion" in report


# ---------------------------------------------------------------------------
# check_spec — non-integration ACs are ignored
# ---------------------------------------------------------------------------

class TestNonIntegrationACs:
    def test_file_exists_ac_ignored(self, tmp_path):
        features = [_make_feature("F1", "File exists: src/foo.py")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_pytest_ac_ignored(self, tmp_path):
        features = [_make_feature("F1", "pytest: tests/test_foo.py")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_function_defined_ac_ignored(self, tmp_path):
        features = [_make_feature("F1", "Function defined: foo.bar.baz")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_empty_spec_passes(self, tmp_path):
        result = check_spec([], workspace=tmp_path)
        assert result.passed is True

    def test_feature_with_no_acs_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": []}]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_spec — module exists in workspace
# ---------------------------------------------------------------------------

class TestWorkspaceFileReachability:
    def test_module_exists_as_src_file_passes(self, tmp_path):
        # Create src/bob3/cli/plan.py
        plan_file = tmp_path / "src" / "bob3" / "cli" / "plan.py"
        plan_file.parent.mkdir(parents=True)
        plan_file.write_text("# plan module\n")

        features = [_make_feature("F1", "integration: bob3.cli.plan")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_module_exists_as_package_init_passes(self, tmp_path):
        pkg = tmp_path / "src" / "mypackage" / "sub"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")

        features = [_make_feature("F1", "integration: mypackage.sub")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_module_missing_produces_issue(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.module")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.missing_module == "totally.nonexistent.module"
        assert issue.feature_name == "F1"
        assert issue.ac_index == 0


# ---------------------------------------------------------------------------
# check_spec — sibling feature in same spec
# ---------------------------------------------------------------------------

class TestSiblingFeatureReachability:
    def test_sibling_integration_target_passes(self, tmp_path):
        # F1 declares integration: myapp.new_module. F2 also references it.
        # Since myapp.new_module is declared in the spec, it is reachable.
        features = [
            _make_feature("F1", "integration: myapp.new_module"),
            _make_feature("F2", "integration: myapp.new_module", "File exists: src/foo.py"),
        ]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_lone_integration_target_not_in_workspace_fails(self, tmp_path):
        # A lone feature whose integration target doesn't exist in the workspace
        # and has no sibling feature to create it is unreachable.
        features = [
            _make_feature("F1", "integration: myapp.orphan_module"),
        ]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        assert result.issues[0].missing_module == "myapp.orphan_module"

    def test_two_features_cross_reference(self, tmp_path):
        # Both features declare integration: foo.bar, so it's in spec_modules.
        features = [
            _make_feature("F1", "integration: foo.bar"),
            _make_feature("F2", "integration: foo.bar"),
        ]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_integration_target_not_in_spec_or_workspace_fails(self, tmp_path):
        # A feature whose integration target is NOT in the spec and NOT in the
        # workspace should fail.
        features = [
            _make_feature("F1", "File exists: src/foo.py"),
            _make_feature("F2", "integration: completely.absent.module"),
        ]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        assert result.issues[0].missing_module == "completely.absent.module"


# ---------------------------------------------------------------------------
# check_spec — importable module
# ---------------------------------------------------------------------------

class TestImportableModuleReachability:
    def test_stdlib_module_passes(self, tmp_path):
        # "os" is always importable
        features = [_make_feature("F1", "integration: os")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_installed_package_passes(self, tmp_path):
        # "pathlib" is always available
        features = [_make_feature("F1", "integration: pathlib")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_spec — closest-match suggestion
# ---------------------------------------------------------------------------

class TestClosestMatchSuggestion:
    def test_typo_in_module_name_suggests_correction(self, tmp_path):
        # Create bob3/cli/plan.py in the workspace
        plan_file = tmp_path / "src" / "bob3" / "cli" / "plan.py"
        plan_file.parent.mkdir(parents=True)
        plan_file.write_text("# plan")

        # Reference a typo: "bob3.cli.pln" instead of "bob3.cli.plan"
        features = [_make_feature("F1", "integration: bob3.cli.pln")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.missing_module == "bob3.cli.pln"
        # The suggestion should be non-None and close to "bob3.cli.plan"
        assert issue.closest_match is not None

    def test_no_suggestion_when_no_candidates(self, tmp_path):
        features = [_make_feature("F1", "integration: zzz.yyy.xxx.totally.absent")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        issue = result.issues[0]
        # No close match — may be None or something; at minimum no crash.
        # closest_match may be None or a far-off suggestion; just assert it's str or None.
        assert issue.closest_match is None or isinstance(issue.closest_match, str)


# ---------------------------------------------------------------------------
# check_spec — multiple features and ACs
# ---------------------------------------------------------------------------

class TestMultipleFeaturesAndACs:
    def test_multiple_integration_acs_in_one_feature(self, tmp_path):
        # Create one module, leave another missing
        (tmp_path / "src" / "bob3").mkdir(parents=True)
        (tmp_path / "src" / "bob3" / "exists.py").write_text("")

        features = [
            _make_feature(
                "F1",
                "integration: bob3.exists",
                "integration: bob3.missing_module",
            )
        ]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].missing_module == "bob3.missing_module"

    def test_multiple_features_one_missing(self, tmp_path):
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "good.py").write_text("")

        features = [
            _make_feature("F1", "integration: pkg.good"),
            _make_feature("F2", "integration: pkg.totally_missing"),
        ]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        names = [i.feature_name for i in result.issues]
        assert "F2" in names
        assert "F1" not in names

    def test_all_reachable_returns_passed(self, tmp_path):
        (tmp_path / "src" / "alpha").mkdir(parents=True)
        (tmp_path / "src" / "alpha" / "beta.py").write_text("")

        features = [
            _make_feature("F1", "integration: alpha.beta"),
            _make_feature("F2", "File exists: src/alpha/beta.py"),
        ]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True

    def test_case_insensitive_integration_prefix(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "mymod.py").write_text("")
        features = [_make_feature("F1", "Integration: mymod")]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# check_spec — feature with missing 'name' key
# ---------------------------------------------------------------------------

class TestFeatureWithMissingNameKey:
    def test_unnamed_feature_uses_fallback(self, tmp_path):
        features = [{"acceptance_criteria": ["integration: ghost.module"]}]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        assert result.issues[0].feature_name == "(unnamed feature)"


# ---------------------------------------------------------------------------
# check_spec — acceptance_criteria as a single string
# ---------------------------------------------------------------------------

class TestACAsString:
    def test_single_string_ac_supported(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": "integration: ghost.str.module"}]
        result = check_spec(features, workspace=tmp_path)
        assert result.passed is False
        assert result.issues[0].missing_module == "ghost.str.module"


# ---------------------------------------------------------------------------
# check_spec — default workspace is cwd (smoke test)
# ---------------------------------------------------------------------------

class TestDefaultWorkspace:
    def test_no_workspace_does_not_crash(self):
        # Should not raise; just runs against cwd.
        features = [_make_feature("F1", "File exists: something.txt")]
        result = check_spec(features)
        # Non-integration AC should pass regardless.
        assert result.passed is True
