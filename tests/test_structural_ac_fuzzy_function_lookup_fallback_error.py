"""Error-path tests for fuzzy_function_lookup in bob.enhanced_verification.

AC: pytest: tests/test_structural_ac_fuzzy_function_lookup_fallback_error.py
    — invalid input raises ValueError and the function does not silently succeed
    (error path)
"""

from __future__ import annotations

import pathlib

import pytest

from bob.enhanced_verification import fuzzy_function_lookup


def _make_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    reviews = tmp_path / "reviews"
    reviews.mkdir(exist_ok=True)
    (reviews / "findings.yaml").write_text("schema_version: 1\nfindings: []\n", encoding="utf-8")
    return tmp_path


class TestFuzzyFunctionLookupErrorPath:
    """Error-path tests: invalid inputs must raise ValueError, not silently succeed."""

    def test_empty_string_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """Empty string symbol_name must raise ValueError (not silently succeed)."""
        workspace = _make_workspace(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            fuzzy_function_lookup(
                workspace=workspace,
                symbol_name="",
                expected_module_path="src/bob/mod.py",
                is_class=False,
            )

    def test_whitespace_only_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """Whitespace-only symbol_name must raise ValueError (not silently succeed)."""
        workspace = _make_workspace(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            fuzzy_function_lookup(
                workspace=workspace,
                symbol_name="   ",
                expected_module_path="src/bob/mod.py",
                is_class=False,
            )

    def test_none_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """None symbol_name must raise ValueError (guard against None input)."""
        workspace = _make_workspace(tmp_path)
        with pytest.raises((ValueError, TypeError)):
            fuzzy_function_lookup(
                workspace=workspace,
                symbol_name=None,  # type: ignore[arg-type]
                expected_module_path="src/bob/mod.py",
                is_class=False,
            )

    def test_integer_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """Integer symbol_name must raise ValueError or TypeError (not silently succeed)."""
        workspace = _make_workspace(tmp_path)
        with pytest.raises((ValueError, TypeError)):
            fuzzy_function_lookup(
                workspace=workspace,
                symbol_name=42,  # type: ignore[arg-type]
                expected_module_path="src/bob/mod.py",
                is_class=False,
            )

    def test_list_symbol_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """List symbol_name must raise ValueError or TypeError (not silently succeed)."""
        workspace = _make_workspace(tmp_path)
        with pytest.raises((ValueError, TypeError)):
            fuzzy_function_lookup(
                workspace=workspace,
                symbol_name=["func_name"],  # type: ignore[arg-type]
                expected_module_path="src/bob/mod.py",
                is_class=False,
            )

    def test_empty_symbol_does_not_return_true_silently(self, tmp_path: pathlib.Path) -> None:
        """Empty symbol_name must not silently return True — must raise ValueError."""
        workspace = _make_workspace(tmp_path)
        # Create a file so workspace has content (ensure no accidental True)
        (tmp_path / "src" / "bob" / "mod.py").write_text("def something():\n    pass\n")

        raised = False
        result = None
        try:
            result = fuzzy_function_lookup(
                workspace=workspace,
                symbol_name="",
                expected_module_path="src/bob/mod.py",
                is_class=False,
            )
        except (ValueError, TypeError):
            raised = True

        assert raised, (
            f"Empty symbol_name must raise ValueError, but returned {result!r} silently"
        )
