"""Tests for security_scan.whitelist_local_modules.

Verifies that locally-defined modules in the generated-code tree are
whitelisted from the PyPI existence check, so that legitimate local
imports do not trigger slopsquatting hard-fails.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob.security_scan import whitelist_local_modules


# ---------------------------------------------------------------------------
# Tests for whitelist_local_modules
# ---------------------------------------------------------------------------


def test_whitelist_includes_src_bob_module(tmp_path: Path) -> None:
    """Modules in src/bob/*.py are whitelisted."""
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "spec_quality_score.py").write_text("# local module\n")

    result = whitelist_local_modules(tmp_path)
    assert "spec_quality_score" in result


def test_whitelist_includes_src_package(tmp_path: Path) -> None:
    """Top-level packages under src/ are whitelisted."""
    src = tmp_path / "src" / "mypackage"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")

    result = whitelist_local_modules(tmp_path)
    assert "mypackage" in result


def test_whitelist_includes_tools_modules(tmp_path: Path) -> None:
    """Modules in tools/ directory are whitelisted."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# tool\n")

    result = whitelist_local_modules(tmp_path)
    assert "spec_quality_score" in result


def test_whitelist_includes_workspace_root_modules(tmp_path: Path) -> None:
    """Python files at the workspace root are whitelisted."""
    (tmp_path / "my_helper.py").write_text("# helper\n")

    result = whitelist_local_modules(tmp_path)
    assert "my_helper" in result


def test_whitelist_excludes_init_files(tmp_path: Path) -> None:
    """__init__.py stems are not added to the whitelist."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")

    result = whitelist_local_modules(tmp_path)
    assert "__init__" not in result


def test_whitelist_returns_set(tmp_path: Path) -> None:
    """Return type is a set."""
    result = whitelist_local_modules(tmp_path)
    assert isinstance(result, set)


def test_whitelist_empty_workspace(tmp_path: Path) -> None:
    """Empty workspace returns a set (may be empty or contain workspace name)."""
    result = whitelist_local_modules(tmp_path)
    assert isinstance(result, set)


def test_spec_quality_score_local_module_whitelisted(tmp_path: Path) -> None:
    """spec_quality_score local module is whitelisted when in src/bob/."""
    src = tmp_path / "src" / "bob"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "spec_quality_score.py").write_text("# generated local module\n")

    result = whitelist_local_modules(tmp_path)
    assert "spec_quality_score" in result, (
        "spec_quality_score must be whitelisted as a local module in src/bob/"
    )


def test_whitelist_does_not_include_non_local_packages(tmp_path: Path) -> None:
    """Packages that are not present locally are not in the whitelist."""
    result = whitelist_local_modules(tmp_path)
    assert "requests" not in result
    assert "flask" not in result
    assert "numpy" not in result


def test_slopsquatting_check_skips_whitelisted_local_module(tmp_path: Path) -> None:
    """Integration: importing a local module must not trigger PyPI probe.

    When spec_quality_score.py exists in src/bob/, it is local and must
    not be probed against PyPI even if the diff adds 'import spec_quality_score'.
    """
    from bob.security_checks import _run_slopsquatting

    src = tmp_path / "src" / "bob"
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

    with patch("bob.security_checks._pypi_package_exists") as mock_probe:
        mock_probe.return_value = False
        findings, _ = _run_slopsquatting(tmp_path, diff, timeout=30)

    flagged = [f for f in findings if "spec_quality_score" in f.message]
    assert len(flagged) == 0, (
        f"spec_quality_score is a local module and must not be flagged: {flagged}"
    )


def test_whitelist_nested_package_modules(tmp_path: Path) -> None:
    """Modules in nested packages (src/bob/subpkg/*.py) are whitelisted."""
    subpkg = tmp_path / "src" / "bob" / "spec_quality"
    subpkg.mkdir(parents=True)
    (subpkg / "__init__.py").write_text("")
    (subpkg / "quality_score.py").write_text("# nested\n")

    result = whitelist_local_modules(tmp_path)
    assert "spec_quality" in result
