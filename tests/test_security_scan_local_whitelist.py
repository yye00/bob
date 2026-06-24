"""Tests for security_scan local-module whitelisting.

Verifies that whitelist_local_modules correctly identifies locally-defined
modules in the generated-code tree so that slopsquatting checks do not
flag legitimate local imports as missing PyPI distributions.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob.security_scan import whitelist_local_modules, slopsquatting_check


class TestWhitelistLocalModules:
    def test_returns_set(self, tmp_path: Path) -> None:
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_src_bob_module_whitelisted(self, tmp_path: Path) -> None:
        """A .py file under src/bob/ is whitelisted by its stem."""
        pkg = tmp_path / "src" / "bob"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "spec_quality_score.py").write_text("# local module\n")

        result = whitelist_local_modules(tmp_path)
        assert "spec_quality_score" in result

    def test_tools_module_whitelisted(self, tmp_path: Path) -> None:
        """A .py file under tools/ is whitelisted by its stem."""
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "spec_quality_score.py").write_text("# tool module\n")

        result = whitelist_local_modules(tmp_path)
        assert "spec_quality_score" in result

    def test_root_level_py_whitelisted(self, tmp_path: Path) -> None:
        """A .py file at the workspace root is whitelisted."""
        (tmp_path / "my_util.py").write_text("x = 1\n")

        result = whitelist_local_modules(tmp_path)
        assert "my_util" in result

    def test_init_not_whitelisted(self, tmp_path: Path) -> None:
        """__init__.py stems are excluded from the whitelist."""
        pkg = tmp_path / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)
        assert "__init__" not in result

    def test_third_party_not_whitelisted(self, tmp_path: Path) -> None:
        """Packages not present locally do not appear in the whitelist."""
        result = whitelist_local_modules(tmp_path)
        assert "requests" not in result
        assert "numpy" not in result
        assert "flask" not in result

    def test_workspace_name_in_whitelist(self, tmp_path: Path) -> None:
        """The workspace directory name itself is included in the whitelist."""
        result = whitelist_local_modules(tmp_path)
        assert tmp_path.resolve().name in result

    def test_nested_package_whitelisted(self, tmp_path: Path) -> None:
        """Sub-packages with __init__.py under src/ are whitelisted."""
        subpkg = tmp_path / "src" / "mypkg" / "subpkg"
        subpkg.mkdir(parents=True)
        (subpkg / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)
        assert "subpkg" in result

    def test_empty_workspace_no_raise(self, tmp_path: Path) -> None:
        """Empty workspace returns a set without raising."""
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_type_error_for_non_path(self) -> None:
        """Non-Path argument raises TypeError."""
        with pytest.raises(TypeError):
            whitelist_local_modules("/tmp/foo")  # type: ignore[arg-type]

    def test_value_error_for_nonexistent(self, tmp_path: Path) -> None:
        """Nonexistent directory raises ValueError."""
        nonexistent = tmp_path / "ghost"
        with pytest.raises(ValueError):
            whitelist_local_modules(nonexistent)

    def test_value_error_for_file(self, tmp_path: Path) -> None:
        """File path (not directory) raises ValueError."""
        f = tmp_path / "not_a_dir.py"
        f.write_text("x = 1\n")
        with pytest.raises(ValueError):
            whitelist_local_modules(f)


class TestSlopsquattingCheckIntegration:
    def test_local_module_not_flagged(self, tmp_path: Path) -> None:
        """Integration: local module in src/bob/ is not flagged as missing PyPI dist."""
        pkg = tmp_path / "src" / "bob"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "spec_quality_score.py").write_text("# local module\n")

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
        assert len(flagged) == 0, (
            f"spec_quality_score is local and must not be flagged: {flagged}"
        )

    def test_nonlocal_import_can_be_flagged(self, tmp_path: Path) -> None:
        """Integration: a genuinely non-local import is still checked against PyPI."""
        diff = (
            "diff --git a/impl.py b/impl.py\n"
            "--- a/impl.py\n"
            "+++ b/impl.py\n"
            "@@ -0,0 +1 @@\n"
            "+import totally_fake_pkg_xyz\n"
        )

        with patch("bob.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(tmp_path, diff)

        flagged = [f for f in findings if "totally_fake_pkg_xyz" in f.message]
        assert len(flagged) == 1, (
            f"A non-local import must be flagged: {findings}"
        )

    def test_returns_tuple(self, tmp_path: Path) -> None:
        """slopsquatting_check returns a (list, str-or-None) tuple."""
        diff = "+import os\n"
        result = slopsquatting_check(tmp_path, diff)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)

    def test_type_error_for_non_path(self) -> None:
        """Non-Path workspace raises TypeError."""
        with pytest.raises(TypeError):
            slopsquatting_check("/tmp/foo")  # type: ignore[arg-type]

    def test_value_error_for_nonexistent(self, tmp_path: Path) -> None:
        """Nonexistent workspace raises ValueError."""
        nonexistent = tmp_path / "ghost"
        with pytest.raises(ValueError):
            slopsquatting_check(nonexistent)
