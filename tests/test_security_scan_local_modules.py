"""Tests for security_scan.whitelist_local_modules — local-module whitelisting.

Verifies that the slopsquatting check correctly whitelists locally-defined
modules so that imports of project-local files (e.g. spec_quality_score)
are never flagged as missing PyPI distributions.

Feature: 0ff1ca4b-b292-4949-9514-0e474e0ff0f7
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob.security_scan import whitelist_local_modules, slopsquatting_check


class TestWhitelistLocalModules:
    """Unit tests for whitelist_local_modules."""

    def test_returns_set(self, tmp_path: Path) -> None:
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_spec_quality_score_whitelisted_when_file_exists(self, tmp_path: Path) -> None:
        """spec_quality_score.py in src/bob/ is whitelisted — the root cause fix."""
        pkg = tmp_path / "src" / "bob"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "spec_quality_score.py").write_text("# local module\n")

        result = whitelist_local_modules(tmp_path)
        assert "spec_quality_score" in result

    def test_local_module_in_tools_whitelisted(self, tmp_path: Path) -> None:
        """A module in tools/ is whitelisted."""
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "my_local_tool.py").write_text("# tool\n")

        result = whitelist_local_modules(tmp_path)
        assert "my_local_tool" in result

    def test_local_module_at_root_whitelisted(self, tmp_path: Path) -> None:
        """A .py file at the workspace root is whitelisted."""
        (tmp_path / "my_local_script.py").write_text("x = 1\n")

        result = whitelist_local_modules(tmp_path)
        assert "my_local_script" in result

    def test_init_py_not_in_whitelist(self, tmp_path: Path) -> None:
        """__init__.py stem is excluded from the whitelist."""
        pkg = tmp_path / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)
        assert "__init__" not in result

    def test_workspace_name_in_whitelist(self, tmp_path: Path) -> None:
        """The workspace directory name itself is in the whitelist."""
        result = whitelist_local_modules(tmp_path)
        assert tmp_path.resolve().name in result

    def test_top_level_package_in_src_whitelisted(self, tmp_path: Path) -> None:
        """A top-level package (with __init__.py) in src/ is whitelisted."""
        pkg = tmp_path / "src" / "mypackage"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)
        assert "mypackage" in result

    def test_nested_subpackage_whitelisted(self, tmp_path: Path) -> None:
        """A sub-package with __init__.py under src/ is whitelisted."""
        subpkg = tmp_path / "src" / "mypkg" / "subpkg"
        subpkg.mkdir(parents=True)
        (subpkg / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)
        assert "subpkg" in result

    def test_third_party_packages_not_in_whitelist(self, tmp_path: Path) -> None:
        """Standard third-party names that are not local do not appear."""
        result = whitelist_local_modules(tmp_path)
        assert "requests" not in result
        assert "numpy" not in result
        assert "flask" not in result

    def test_pyproject_name_in_whitelist(self, tmp_path: Path) -> None:
        """Package name from pyproject.toml [project].name is in the whitelist."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my-project"\n'
        )

        result = whitelist_local_modules(tmp_path)
        assert "my_project" in result

    def test_tools_dir_itself_whitelisted(self, tmp_path: Path) -> None:
        """'tools' itself is in the whitelist when tools/ exists."""
        tools = tmp_path / "tools"
        tools.mkdir()

        result = whitelist_local_modules(tmp_path)
        assert "tools" in result

    def test_empty_workspace_returns_set(self, tmp_path: Path) -> None:
        """Empty workspace returns a set without raising."""
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_type_error_for_string_arg(self) -> None:
        """A raw string raises TypeError (not Path)."""
        with pytest.raises(TypeError):
            whitelist_local_modules("/tmp/foo")  # type: ignore[arg-type]

    def test_value_error_for_nonexistent_dir(self, tmp_path: Path) -> None:
        """A nonexistent path raises ValueError."""
        nonexistent = tmp_path / "no_such_dir"
        with pytest.raises(ValueError):
            whitelist_local_modules(nonexistent)

    def test_value_error_for_file_not_dir(self, tmp_path: Path) -> None:
        """A file path (not a directory) raises ValueError."""
        f = tmp_path / "some_file.py"
        f.write_text("x = 1\n")
        with pytest.raises(ValueError):
            whitelist_local_modules(f)


class TestSlopsquattingIntegration:
    """Integration tests verifying slopsquatting_check uses the whitelist."""

    def test_local_module_import_not_flagged(self, tmp_path: Path) -> None:
        """Integration: an import of a local module is not flagged as slopsquatting."""
        pkg = tmp_path / "src" / "bob"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "spec_quality_score.py").write_text("# local\n")

        diff = (
            "diff --git a/impl.py b/impl.py\n"
            "--- a/impl.py\n"
            "+++ b/impl.py\n"
            "@@ -0,0 +1 @@\n"
            "+import spec_quality_score\n"
        )

        with patch("bob.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(tmp_path, diff)

        flagged = [f for f in findings if "spec_quality_score" in f.message]
        assert len(flagged) == 0, f"Local module must not be flagged: {flagged}"

    def test_genuinely_missing_import_flagged(self, tmp_path: Path) -> None:
        """Integration: a non-local import is still checked against PyPI."""
        diff = (
            "diff --git a/impl.py b/impl.py\n"
            "--- a/impl.py\n"
            "+++ b/impl.py\n"
            "@@ -0,0 +1 @@\n"
            "+import totally_fictitious_pkg_zzz\n"
        )

        with patch("bob.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(tmp_path, diff)

        flagged = [f for f in findings if "totally_fictitious_pkg_zzz" in f.message]
        assert len(flagged) == 1, f"Non-local import must be flagged: {findings}"

    def test_stdlib_import_not_flagged(self, tmp_path: Path) -> None:
        """Integration: stdlib imports are never passed to PyPI probes."""
        diff = "+import os\n+import sys\n+import pathlib\n"

        with patch("bob.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(tmp_path, diff)

        slop_findings = [f for f in findings if f.tool == "slopsquatting"]
        assert len(slop_findings) == 0, f"stdlib imports must not be flagged: {slop_findings}"

    def test_returns_tuple_of_list_and_optional_str(self, tmp_path: Path) -> None:
        """slopsquatting_check always returns (list, str|None)."""
        result = slopsquatting_check(tmp_path, diff=None)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], list)
        assert result[1] is None or isinstance(result[1], str)

    def test_type_error_for_non_path_workspace(self) -> None:
        """Non-Path workspace raises TypeError."""
        with pytest.raises(TypeError):
            slopsquatting_check("/tmp/foo")  # type: ignore[arg-type]

    def test_value_error_for_missing_workspace(self, tmp_path: Path) -> None:
        """Missing workspace raises ValueError."""
        with pytest.raises(ValueError):
            slopsquatting_check(tmp_path / "ghost")
