"""Tests for bob3.security_scan — whitelist_local_modules and slopsquatting_check.

Verifies that the public API in security_scan.py correctly whitelists
locally-defined modules in the generated-code tree so that the
slopsquatting sub-check does not false-positive on local imports.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.security_scan import whitelist_local_modules, slopsquatting_check


# ---------------------------------------------------------------------------
# whitelist_local_modules
# ---------------------------------------------------------------------------


class TestWhitelistLocalModules:
    def test_src_bob3_py_files_whitelisted(self, tmp_path: Path) -> None:
        """Python files under src/bob3/ are included in the whitelist."""
        src = tmp_path / "src" / "bob3"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "spec_quality_score.py").write_text("# local module\n")

        result = whitelist_local_modules(tmp_path)

        assert "spec_quality_score" in result

    def test_top_level_src_package_whitelisted(self, tmp_path: Path) -> None:
        """A top-level package under src/ is included in the whitelist."""
        pkg = tmp_path / "src" / "mypackage"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)

        assert "mypackage" in result

    def test_tools_dir_modules_whitelisted(self, tmp_path: Path) -> None:
        """Python files under tools/ are included in the whitelist."""
        tools = tmp_path / "tools"
        tools.mkdir()
        (tools / "helper_script.py").write_text("# tool\n")

        result = whitelist_local_modules(tmp_path)

        assert "helper_script" in result

    def test_workspace_root_py_files_whitelisted(self, tmp_path: Path) -> None:
        """Python files at the workspace root are included in the whitelist."""
        (tmp_path / "my_helper.py").write_text("# helper\n")

        result = whitelist_local_modules(tmp_path)

        assert "my_helper" in result

    def test_init_stem_not_in_whitelist(self, tmp_path: Path) -> None:
        """__init__ stems are never added to the whitelist."""
        src = tmp_path / "src" / "pkg"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)

        assert "__init__" not in result

    def test_returns_set(self, tmp_path: Path) -> None:
        """Return type is a set."""
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_empty_workspace_returns_set(self, tmp_path: Path) -> None:
        """Empty workspace returns a set (may contain the workspace basename)."""
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_spec_quality_score_is_whitelisted(self, tmp_path: Path) -> None:
        """The canonical false-positive case: spec_quality_score is whitelisted."""
        src = tmp_path / "src" / "bob3"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "spec_quality_score.py").write_text("# generated local module\n")

        result = whitelist_local_modules(tmp_path)

        assert "spec_quality_score" in result, (
            "spec_quality_score must be whitelisted as a local module in src/bob3/"
        )

    def test_third_party_names_not_in_whitelist(self, tmp_path: Path) -> None:
        """Packages not present locally are not in the whitelist."""
        result = whitelist_local_modules(tmp_path)
        assert "requests" not in result
        assert "flask" not in result
        assert "numpy" not in result

    def test_invalid_type_raises(self) -> None:
        """Non-Path argument raises TypeError or similar."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            whitelist_local_modules("/tmp/path")  # type: ignore[arg-type]

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        """Nonexistent path raises ValueError or similar."""
        with pytest.raises((ValueError, FileNotFoundError, OSError)):
            whitelist_local_modules(tmp_path / "does_not_exist")

    def test_file_path_raises(self, tmp_path: Path) -> None:
        """Passing a file (not a directory) raises."""
        f = tmp_path / "not_a_dir.py"
        f.write_text("x = 1\n")
        with pytest.raises((ValueError, NotADirectoryError, OSError)):
            whitelist_local_modules(f)

    def test_workspace_basename_in_whitelist(self, tmp_path: Path) -> None:
        """The workspace directory's own name is in the whitelist."""
        result = whitelist_local_modules(tmp_path)
        assert tmp_path.resolve().name in result

    def test_nested_subpackage_whitelisted(self, tmp_path: Path) -> None:
        """Subpackage directories with __init__.py are whitelisted."""
        subpkg = tmp_path / "src" / "bob3" / "spec_quality"
        subpkg.mkdir(parents=True)
        (subpkg / "__init__.py").write_text("")

        result = whitelist_local_modules(tmp_path)

        assert "spec_quality" in result


# ---------------------------------------------------------------------------
# slopsquatting_check integration
# ---------------------------------------------------------------------------


class TestSlopsquattingCheck:
    def test_local_module_not_flagged(self, tmp_path: Path) -> None:
        """A local module imported in a diff is not flagged as slopsquatting."""
        src = tmp_path / "src" / "bob3"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")
        (src / "spec_quality_score.py").write_text("# local\n")

        diff = (
            "diff --git a/impl.py b/impl.py\n"
            "--- a/impl.py\n"
            "+++ b/impl.py\n"
            "@@ -0,0 +1 @@\n"
            "+import spec_quality_score\n"
        )

        with patch("bob3.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(tmp_path, diff, timeout=30)

        flagged = [f for f in findings if "spec_quality_score" in f.message]
        assert len(flagged) == 0, (
            f"spec_quality_score is local and must not be flagged: {flagged}"
        )

    def test_nonexistent_pypi_package_flagged(self, tmp_path: Path) -> None:
        """A genuinely fictitious import is flagged even with whitelisting active."""
        src = tmp_path / "src" / "bob3"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("")

        diff = (
            "diff --git a/impl.py b/impl.py\n"
            "--- a/impl.py\n"
            "+++ b/impl.py\n"
            "@@ -0,0 +1 @@\n"
            "+import zzz_totally_fake_pkg_that_does_not_exist_anywhere\n"
        )

        with patch("bob3.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(tmp_path, diff, timeout=30)

        flagged = [
            f for f in findings
            if "zzz_totally_fake_pkg_that_does_not_exist_anywhere" in f.message
        ]
        assert len(flagged) == 1

    def test_returns_tuple(self, tmp_path: Path) -> None:
        """slopsquatting_check returns a (list, str|None) tuple."""
        result = slopsquatting_check(tmp_path, None, timeout=5)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)

    def test_invalid_workspace_type_raises(self) -> None:
        """Non-Path workspace raises TypeError."""
        with pytest.raises((TypeError, ValueError, AttributeError)):
            slopsquatting_check("not_a_path", None, timeout=5)  # type: ignore[arg-type]

    def test_nonexistent_workspace_raises(self, tmp_path: Path) -> None:
        """Nonexistent workspace raises ValueError."""
        with pytest.raises((ValueError, FileNotFoundError, OSError)):
            slopsquatting_check(tmp_path / "missing", None, timeout=5)
