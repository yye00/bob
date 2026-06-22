"""Tests for structural-AC fuzzy function-lookup fallback (ebae5ed8).

Acceptance criteria:
- test_pass_via_fuzzy: when exact module path doesn't define the function but
  another file in workspace does, fuzzy fallback returns True (PASS).
- test_fail_when_truly_absent: when function is absent from entire workspace,
  structural AC hard-fails (returns False).
- test_warning_emitted_on_fuzzy_hit: fuzzy-fallback hit emits a WARNING record
  to reviews/findings.yaml noting the path mismatch.
"""

from __future__ import annotations

import re
import tempfile
import pathlib

import pytest


def _make_workspace(
    tmp_path: pathlib.Path,
    *,
    src_files: dict[str, str] | None = None,
    reviews_findings: bool = True,
) -> pathlib.Path:
    """Create a minimal workspace with src/ layout."""
    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")

    if src_files:
        for rel_path, content in src_files.items():
            full = tmp_path / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)

    reviews = tmp_path / "reviews"
    reviews.mkdir(exist_ok=True)
    if reviews_findings:
        (reviews / "findings.yaml").write_text(
            "schema_version: 1\nfindings: []\n"
        )

    return tmp_path


def _run_structural_check(
    workspace: pathlib.Path,
    criterion: str,
) -> bool:
    """Run the structural AC check via _check_criterion."""
    import sys
    # Ensure bob3 source on path
    bob3_src = pathlib.Path(__file__).parent.parent / "src"
    if str(bob3_src) not in sys.path:
        sys.path.insert(0, str(bob3_src))

    from bob3.enhanced_verification import _check_criterion
    return _check_criterion(
        criterion=criterion,
        workspace=workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )


class TestPassViaFuzzy:
    """When exact module path doesn't define Y but another file does, PASS."""

    def test_pass_via_fuzzy(self, tmp_path: pathlib.Path) -> None:
        """Function defined in wrong module → fuzzy fallback finds it → PASS."""
        # AC says X.py defines Y, but Y actually lives in Z.py
        workspace = _make_workspace(
            tmp_path,
            src_files={
                # X.py exists but does NOT define the function
                "src/bob3/expected_module.py": "def other_function():\n    pass\n",
                # Z.py DOES define the function (different module)
                "src/bob3/actual_module.py": "def my_special_func(x, y):\n    return x + y\n",
            },
        )
        criterion = (
            "structural: src/bob3/expected_module.py defines function my_special_func"
        )
        result = _run_structural_check(workspace, criterion)
        assert result is True, (
            "Expected fuzzy fallback to PASS when function exists in workspace "
            "but not in the exact module named by the AC"
        )

    def test_pass_via_fuzzy_class(self, tmp_path: pathlib.Path) -> None:
        """Class defined in wrong module → fuzzy fallback finds it → PASS."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/wrong_module.py": "def unrelated():\n    pass\n",
                "src/bob3/right_module.py": "class MySpecialClass:\n    pass\n",
            },
        )
        criterion = (
            "structural: src/bob3/wrong_module.py defines class MySpecialClass"
        )
        result = _run_structural_check(workspace, criterion)
        assert result is True, (
            "Expected fuzzy fallback to PASS when class exists in workspace "
            "but not in the exact module named by the AC"
        )


class TestFailWhenTrulyAbsent:
    """When function is absent from entire workspace, structural AC hard-fails."""

    def test_fail_when_truly_absent(self, tmp_path: pathlib.Path) -> None:
        """Function not found anywhere in workspace → hard-fail (False)."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/some_module.py": "def different_function():\n    pass\n",
                "src/bob3/another_module.py": "x = 1\n",
            },
        )
        criterion = (
            "structural: src/bob3/some_module.py defines function totally_absent_func"
        )
        result = _run_structural_check(workspace, criterion)
        assert result is False, (
            "Expected hard-fail when function is absent from entire workspace"
        )

    def test_exact_match_still_passes(self, tmp_path: pathlib.Path) -> None:
        """When exact module DOES define the function, it should pass directly."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/correct_module.py": "def correct_function(a, b):\n    return a + b\n",
            },
        )
        criterion = (
            "structural: src/bob3/correct_module.py defines function correct_function"
        )
        result = _run_structural_check(workspace, criterion)
        assert result is True, (
            "Expected direct PASS when exact module defines the function"
        )


class TestWarningEmittedOnFuzzyHit:
    """Fuzzy-fallback hit MUST emit a WARNING record to reviews/findings.yaml."""

    def test_warning_emitted_on_fuzzy_hit(self, tmp_path: pathlib.Path) -> None:
        """Fuzzy hit writes a WARNING entry to reviews/findings.yaml."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/named_module.py": "def something_else():\n    pass\n",
                "src/bob3/other_module.py": "def fuzzy_hit_function():\n    pass\n",
            },
        )
        criterion = (
            "structural: src/bob3/named_module.py defines function fuzzy_hit_function"
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        before_content = findings_path.read_text()

        result = _run_structural_check(workspace, criterion)
        assert result is True, "Fuzzy fallback should PASS"

        after_content = findings_path.read_text()
        assert after_content != before_content, (
            "findings.yaml must be updated when fuzzy fallback fires"
        )
        # The warning record must mention the path mismatch
        assert "fuzzy_hit_function" in after_content or "named_module" in after_content, (
            "Warning record must mention the function or module name"
        )
        # Should contain a severity/warning indicator
        assert "warning" in after_content.lower(), (
            "Warning record must have severity=warning (case-insensitive)"
        )

    def test_no_warning_on_exact_match(self, tmp_path: pathlib.Path) -> None:
        """No warning should be emitted when exact module match succeeds."""
        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/exact_module.py": "def exact_func():\n    pass\n",
            },
        )
        criterion = (
            "structural: src/bob3/exact_module.py defines function exact_func"
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        before_content = findings_path.read_text()

        result = _run_structural_check(workspace, criterion)
        assert result is True

        after_content = findings_path.read_text()
        # No warning should be emitted on exact match
        assert after_content == before_content, (
            "No finding should be written when exact module match succeeds"
        )


class TestFuzzyFallbackFunction:
    """Direct unit tests for _structural_ac_fuzzy_fallback."""

    def test_function_exists_in_workspace(self, tmp_path: pathlib.Path) -> None:
        """_structural_ac_fuzzy_fallback returns True when def Y( found in workspace."""
        import sys
        bob3_src = pathlib.Path(__file__).parent.parent / "src"
        if str(bob3_src) not in sys.path:
            sys.path.insert(0, str(bob3_src))

        from bob3.enhanced_verification import _structural_ac_fuzzy_fallback

        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/module_a.py": "def target_function(x):\n    return x\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = _structural_ac_fuzzy_fallback(
            workspace=workspace,
            expected_module_path="src/bob3/other_module.py",
            symbol_name="target_function",
            is_class=False,
            findings_path=findings_path,
        )
        assert result is True

    def test_class_exists_in_workspace(self, tmp_path: pathlib.Path) -> None:
        """_structural_ac_fuzzy_fallback returns True when class Y found in workspace."""
        import sys
        bob3_src = pathlib.Path(__file__).parent.parent / "src"
        if str(bob3_src) not in sys.path:
            sys.path.insert(0, str(bob3_src))

        from bob3.enhanced_verification import _structural_ac_fuzzy_fallback

        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/module_b.py": "class TargetClass:\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = _structural_ac_fuzzy_fallback(
            workspace=workspace,
            expected_module_path="src/bob3/wrong_module.py",
            symbol_name="TargetClass",
            is_class=True,
            findings_path=findings_path,
        )
        assert result is True

    def test_absent_returns_false(self, tmp_path: pathlib.Path) -> None:
        """_structural_ac_fuzzy_fallback returns False when symbol absent everywhere."""
        import sys
        bob3_src = pathlib.Path(__file__).parent.parent / "src"
        if str(bob3_src) not in sys.path:
            sys.path.insert(0, str(bob3_src))

        from bob3.enhanced_verification import _structural_ac_fuzzy_fallback

        workspace = _make_workspace(
            tmp_path,
            src_files={
                "src/bob3/module_c.py": "def unrelated():\n    pass\n",
            },
        )
        findings_path = workspace / "reviews" / "findings.yaml"
        result = _structural_ac_fuzzy_fallback(
            workspace=workspace,
            expected_module_path="src/bob3/module_c.py",
            symbol_name="nonexistent_func",
            is_class=False,
            findings_path=findings_path,
        )
        assert result is False
