"""Integration tests for the structural-AC fuzzy function-lookup fallback.

AC: pytest: tests/test_enhanced_verification_fuzzy_lookup.py
    integration: bob.enhanced_verification

Verifies that when a "structural: <module>.py defines function <Y>" AC fails
the exact-module check (because Y was implemented in a different module), the
enhanced_verification layer falls back to a workspace-wide grep and PASSES
(with a WARNING) rather than hard-failing.
"""

from __future__ import annotations

import pathlib

import pytest

from bob.enhanced_verification import (
    check_criterion,
    fallback_function_lookup,
    fuzzy_function_lookup,
    _structural_ac_fuzzy_fallback,
)


def _make_workspace(
    tmp_path: pathlib.Path,
    src_files: dict[str, str] | None = None,
) -> pathlib.Path:
    """Create a minimal workspace with optional source files."""
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    if src_files:
        for rel, content in src_files.items():
            full = tmp_path / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
    reviews = tmp_path / "reviews"
    reviews.mkdir(exist_ok=True)
    (reviews / "findings.yaml").write_text(
        "schema_version: 1\nfindings: []\n", encoding="utf-8"
    )
    return tmp_path


class TestStructuralACFuzzyLookupViaCheckCriterion:
    """Integration tests via check_criterion for structural AC fuzzy fallback."""

    def test_function_in_different_module_passes_via_fuzzy(self, tmp_path: pathlib.Path) -> None:
        """structural: X.py defines function Y — Y is in Z.py → fuzzy fallback passes."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/X.py": "# function not here\n",
                "src/bob/Z.py": "def my_target_func(arg):\n    return arg\n",
            },
        )
        criterion = "structural: src/bob/X.py defines function my_target_func"
        result = check_criterion(criterion, workspace=workspace)
        assert result is True, (
            "When function is in Z.py but AC expects X.py, fuzzy fallback must pass"
        )

    def test_class_in_different_module_passes_via_fuzzy(self, tmp_path: pathlib.Path) -> None:
        """structural: X.py defines class MyClass — MyClass is in Z.py → fuzzy fallback passes."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/X.py": "# class not here\n",
                "src/bob/Z.py": "class MyTargetClass:\n    pass\n",
            },
        )
        criterion = "structural: src/bob/X.py defines class MyTargetClass"
        result = check_criterion(criterion, workspace=workspace)
        assert result is True, (
            "When class is in Z.py but AC expects X.py, fuzzy fallback must pass"
        )

    def test_function_absent_entirely_fails(self, tmp_path: pathlib.Path) -> None:
        """structural: X.py defines function Y — Y not in workspace at all → hard-fail."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/X.py": "def unrelated_func():\n    pass\n",
            },
        )
        criterion = "structural: src/bob/X.py defines function totally_missing_sym"
        result = check_criterion(criterion, workspace=workspace)
        assert result is False, "Symbol absent from workspace must hard-fail"

    def test_function_in_exact_module_passes_directly(self, tmp_path: pathlib.Path) -> None:
        """structural: X.py defines function Y — Y is in X.py → direct pass (no fuzzy needed)."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/X.py": "def exact_function(x):\n    return x\n",
            },
        )
        criterion = "structural: src/bob/X.py defines function exact_function"
        result = check_criterion(criterion, workspace=workspace)
        assert result is True, "Exact module match must pass directly"

    def test_fuzzy_hit_writes_warning_to_findings_yaml(self, tmp_path: pathlib.Path) -> None:
        """When fuzzy fallback fires, findings.yaml gains a warning entry."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/X.py": "# empty\n",
                "src/bob/Z.py": "def warn_me_func():\n    return None\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        before = findings_path.read_text()

        criterion = "structural: src/bob/X.py defines function warn_me_func"
        result = check_criterion(criterion, workspace=workspace)

        assert result is True
        after = findings_path.read_text()
        assert after != before, "findings.yaml must be updated when fuzzy fallback fires"
        assert "warning" in after.lower(), "Severity must be 'warning' in findings entry"


class TestStructuralACFuzzyFallbackDirect:
    """Direct tests of _structural_ac_fuzzy_fallback internals."""

    def test_fuzzy_fallback_returns_true_when_found(self, tmp_path: pathlib.Path) -> None:
        """_structural_ac_fuzzy_fallback returns True when symbol found in workspace."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/Z.py": "def fuzzy_sym_here():\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = _structural_ac_fuzzy_fallback(
            workspace=workspace,
            expected_module_path="src/bob/X.py",
            symbol_name="fuzzy_sym_here",
            is_class=False,
            findings_path=findings_path,
        )
        assert result is True

    def test_fuzzy_fallback_returns_false_when_absent(self, tmp_path: pathlib.Path) -> None:
        """_structural_ac_fuzzy_fallback returns False when symbol not found."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/Z.py": "def some_other_func():\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = _structural_ac_fuzzy_fallback(
            workspace=workspace,
            expected_module_path="src/bob/X.py",
            symbol_name="completely_absent_sym",
            is_class=False,
            findings_path=findings_path,
        )
        assert result is False

    def test_fuzzy_fallback_class_search(self, tmp_path: pathlib.Path) -> None:
        """_structural_ac_fuzzy_fallback finds class definitions with is_class=True."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/Z.py": "class FuzzyClass:\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = _structural_ac_fuzzy_fallback(
            workspace=workspace,
            expected_module_path="src/bob/X.py",
            symbol_name="FuzzyClass",
            is_class=True,
            findings_path=findings_path,
        )
        assert result is True


class TestFuzzyFunctionLookupPublicAPI:
    """Integration tests for the public fuzzy_function_lookup API."""

    def test_public_api_function_found_elsewhere(self, tmp_path: pathlib.Path) -> None:
        """fuzzy_function_lookup finds a function in wrong module and returns True."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/expected_module.py": "# nothing here\n",
                "src/bob/actual_module.py": "def real_impl():\n    return 42\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="real_impl",
            expected_module_path="src/bob/expected_module.py",
            is_class=False,
            findings_path=findings_path,
        )
        assert result is True

    def test_public_api_returns_false_when_absent(self, tmp_path: pathlib.Path) -> None:
        """fuzzy_function_lookup returns False when symbol absent from all modules."""
        workspace = _make_workspace(tmp_path)
        findings_path = workspace / "reviews" / "findings.yaml"
        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="absent_function",
            expected_module_path="src/bob/any.py",
            is_class=False,
            findings_path=findings_path,
        )
        assert result is False

    def test_fallback_function_lookup_alias_works(self, tmp_path: pathlib.Path) -> None:
        """fallback_function_lookup is a valid public alias for fuzzy_function_lookup."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob/module_a.py": "def alias_target():\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = fallback_function_lookup(
            workspace=workspace,
            symbol_name="alias_target",
            expected_module_path="src/bob/module_b.py",
            is_class=False,
            findings_path=findings_path,
        )
        assert result is True, "fallback_function_lookup alias must work identically"

    def test_invalid_empty_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """fuzzy_function_lookup raises ValueError for empty symbol_name."""
        workspace = _make_workspace(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            fuzzy_function_lookup(
                workspace=workspace,
                symbol_name="",
                expected_module_path="src/bob/any.py",
            )
