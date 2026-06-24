"""Tests for structural-AC fuzzy function-lookup fallback via fallback_function_lookup.

AC: pytest: tests/test_structural_ac_fuzzy_lookup.py
Feature: F-R7-588 — Structural-AC fuzzy function-lookup fallback
"""

from __future__ import annotations

import pathlib

import pytest

from bob3.enhanced_verification import fallback_function_lookup


def _make_workspace(
    tmp_path: pathlib.Path,
    src_files: dict[str, str] | None = None,
) -> pathlib.Path:
    src = tmp_path / "src" / "bob3"
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


class TestFallbackFunctionLookupHit:
    """When symbol found elsewhere in workspace, returns True."""

    def test_function_found_in_wrong_module_returns_true(self, tmp_path: pathlib.Path) -> None:
        """AC expects X.py; function lives in Z.py — fuzzy search returns True."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/X.py": "# no function here\n",
                "src/bob3/Z.py": "def my_func(x):\n    return x\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fallback_function_lookup(
            workspace=workspace,
            symbol_name="my_func",
            expected_module_path="src/bob3/X.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert result is True

    def test_class_found_in_wrong_module_returns_true(self, tmp_path: pathlib.Path) -> None:
        """AC expects X.py; class lives in Z.py — fuzzy search returns True."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/X.py": "# no class here\n",
                "src/bob3/Z.py": "class MyClass:\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fallback_function_lookup(
            workspace=workspace,
            symbol_name="MyClass",
            expected_module_path="src/bob3/X.py",
            is_class=True,
            findings_path=findings_path,
        )

        assert result is True

    def test_warning_emitted_on_fuzzy_hit(self, tmp_path: pathlib.Path) -> None:
        """Fuzzy hit writes a WARNING entry to findings.yaml."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/X.py": "# no function here\n",
                "src/bob3/Z.py": "def function_in_z(arg):\n    return arg\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        before = findings_path.read_text()

        result = fallback_function_lookup(
            workspace=workspace,
            symbol_name="function_in_z",
            expected_module_path="src/bob3/X.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert result is True
        after = findings_path.read_text()
        assert after != before, "findings.yaml must be updated on fuzzy hit"
        assert "warning" in after.lower(), "Warning severity must appear in findings"


class TestFallbackFunctionLookupMiss:
    """When symbol absent from entire workspace, returns False."""

    def test_function_absent_returns_false(self, tmp_path: pathlib.Path) -> None:
        """Symbol not found anywhere → False."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/X.py": "def unrelated():\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fallback_function_lookup(
            workspace=workspace,
            symbol_name="totally_absent_sym",
            expected_module_path="src/bob3/X.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert result is False

    def test_class_absent_returns_false(self, tmp_path: pathlib.Path) -> None:
        """Class not found anywhere → False."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/X.py": "class SomeOtherClass:\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fallback_function_lookup(
            workspace=workspace,
            symbol_name="MissingClass",
            expected_module_path="src/bob3/X.py",
            is_class=True,
            findings_path=findings_path,
        )

        assert result is False


class TestFallbackFunctionLookupInvalidInput:
    """Invalid inputs raise ValueError."""

    def test_empty_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        workspace = _make_workspace(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            fallback_function_lookup(
                workspace=workspace,
                symbol_name="",
                expected_module_path="src/bob3/X.py",
            )

    def test_whitespace_only_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        workspace = _make_workspace(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            fallback_function_lookup(
                workspace=workspace,
                symbol_name="   ",
                expected_module_path="src/bob3/X.py",
            )

    def test_none_symbol_raises(self, tmp_path: pathlib.Path) -> None:
        workspace = _make_workspace(tmp_path)
        with pytest.raises((ValueError, TypeError)):
            fallback_function_lookup(
                workspace=workspace,
                symbol_name=None,  # type: ignore[arg-type]
                expected_module_path="src/bob3/X.py",
            )


class TestFallbackFunctionLookupExactMatch:
    """When exact module defines the symbol, returns True directly."""

    def test_exact_module_pass(self, tmp_path: pathlib.Path) -> None:
        """Function in exact module → True (no fuzzy needed)."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/X.py": "def exact_sym():\n    return 1\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"

        result = fallback_function_lookup(
            workspace=workspace,
            symbol_name="exact_sym",
            expected_module_path="src/bob3/X.py",
            is_class=False,
            findings_path=findings_path,
        )

        assert result is True
