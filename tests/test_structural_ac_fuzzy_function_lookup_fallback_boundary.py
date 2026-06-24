"""Boundary tests for fuzzy_function_lookup in bob.enhanced_verification.

AC: pytest: tests/test_structural_ac_fuzzy_function_lookup_fallback_boundary.py
    — empty, zero, or minimum input returns a well-defined result rather than raising
    (boundary case)
"""

from __future__ import annotations

import pathlib

import pytest

from bob.enhanced_verification import fuzzy_function_lookup


def _make_workspace(tmp_path: pathlib.Path, src_files: dict[str, str] | None = None) -> pathlib.Path:
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
    (reviews / "findings.yaml").write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")
    return tmp_path


class TestFuzzyFunctionLookupBoundary:
    """Boundary-condition tests: edge inputs return well-defined results, no crashes."""

    def test_symbol_not_found_in_empty_workspace_returns_false(self, tmp_path: pathlib.Path) -> None:
        """When workspace has no Python files with the symbol, returns False — does not raise."""
        workspace = _make_workspace(tmp_path, src_files={
            "src/bob/empty_module.py": "# no functions here\n",
        })
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="nonexistent_func",
            expected_module_path="src/bob/empty_module.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert result is False, "Must return False (not raise) when symbol is absent"

    def test_minimum_length_symbol_name_single_char(self, tmp_path: pathlib.Path) -> None:
        """Single-character symbol name is a valid minimum — returns well-defined bool."""
        workspace = _make_workspace(tmp_path, src_files={
            "src/bob/mod.py": "def f(x):\n    return x\n",
        })
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="f",
            expected_module_path="src/bob/other.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert isinstance(result, bool), "Must return a bool for single-char symbol name"

    def test_findings_path_none_uses_default(self, tmp_path: pathlib.Path) -> None:
        """When findings_path=None, falls back to workspace/reviews/findings.yaml — no crash."""
        workspace = _make_workspace(tmp_path, src_files={
            "src/bob/mod.py": "def boundary_sym():\n    pass\n",
        })

        # findings_path=None → default path; should not raise
        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="boundary_sym",
            expected_module_path="src/bob/other.py",
            is_class=False,
            findings_path=None,
        )

        assert result is True, "Symbol found in workspace → True even with findings_path=None"
        default_findings = workspace / "reviews" / "findings.yaml"
        assert default_findings.exists(), "Default findings.yaml must exist after fuzzy hit"

    def test_is_class_true_minimum_class_found(self, tmp_path: pathlib.Path) -> None:
        """is_class=True with a minimal class definition → returns True (fuzzy match)."""
        workspace = _make_workspace(tmp_path, src_files={
            "src/bob/impl.py": "class C:\n    pass\n",
        })
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="C",
            expected_module_path="src/bob/expected.py",
            is_class=True,
            findings_path=findings_path,
        )

        assert result is True, "Single-char class name found in workspace → True"

    def test_empty_src_dir_symbol_absent_returns_false(self, tmp_path: pathlib.Path) -> None:
        """Zero Python source files → symbol absent → returns False, not an exception."""
        workspace = _make_workspace(tmp_path)  # no extra src_files
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="any_func",
            expected_module_path="src/bob/nonexistent.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert result is False, "Empty workspace must return False, not raise"

    def test_symbol_found_returns_true_well_defined(self, tmp_path: pathlib.Path) -> None:
        """Minimum working scenario: exactly one file with symbol → True, no side-effects crash."""
        workspace = _make_workspace(tmp_path, src_files={
            "src/bob/only.py": "def lone_func():\n    return 1\n",
        })
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fuzzy_function_lookup(
            workspace=workspace,
            symbol_name="lone_func",
            expected_module_path="src/bob/missing.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert result is True
