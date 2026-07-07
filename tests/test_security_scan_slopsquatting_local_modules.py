"""Tests for security_scan local-module whitelisting.

Covers ``bob.security_scan.is_local_module`` and
``bob.security_scan.slopsquatting_check`` — the fix ensuring that
locally-defined modules in the generated-code tree (e.g.
``spec_quality_score``) are never flagged as missing PyPI distributions
by the slopsquatting heuristic.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.security_scan import (
    is_local_module,
    slopsquatting_check,
    whitelist_local_modules,
)


def _make_workspace(tmp_path: Path) -> Path:
    """Build a minimal workspace with a src/bob package and a local module."""
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        '[project]\nname = "bob-workspace"\n'
        '[tool.pytest.ini_options]\npythonpath = ["src"]\n'
    )
    pkg = tmp_path / "src" / "bob"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "spec_quality_score.py").write_text("SCORE = 1.0\n")
    return tmp_path


class TestIsLocalModule:
    def test_local_module_recognised(self, tmp_path: Path) -> None:
        """A module present in src/bob is recognised as local."""
        ws = _make_workspace(tmp_path)
        assert is_local_module("spec_quality_score", ws) is True

    def test_local_package_recognised(self, tmp_path: Path) -> None:
        """The bob package itself is recognised as local."""
        ws = _make_workspace(tmp_path)
        assert is_local_module("bob", ws) is True

    def test_third_party_name_not_local(self, tmp_path: Path) -> None:
        """A name that is not in the tree is not local."""
        ws = _make_workspace(tmp_path)
        assert is_local_module("requests", ws) is False

    def test_root_level_module_recognised(self, tmp_path: Path) -> None:
        """A root-level .py file is recognised as local."""
        ws = _make_workspace(tmp_path)
        (ws / "spawn_next_generation.py").write_text("x = 1\n")
        assert is_local_module("spawn_next_generation", ws) is True

    def test_tools_module_recognised(self, tmp_path: Path) -> None:
        """A module under tools/ is recognised as local."""
        ws = _make_workspace(tmp_path)
        tools = ws / "tools"
        tools.mkdir()
        (tools / "helper.py").write_text("x = 1\n")
        assert is_local_module("helper", ws) is True

    def test_returns_bool(self, tmp_path: Path) -> None:
        """Return value is a plain bool."""
        ws = _make_workspace(tmp_path)
        assert isinstance(is_local_module("spec_quality_score", ws), bool)


class TestSlopsquattingCheckWhitelistsLocal:
    def test_local_import_not_flagged(self, tmp_path: Path) -> None:
        """A diff importing a local module produces no slopsquatting finding.

        Even though ``spec_quality_score`` does not exist on PyPI, it is a
        local module and must be whitelisted before any PyPI probe, so the
        check must return no findings for it (no network call is made).
        """
        ws = _make_workspace(tmp_path)
        diff = (
            "--- a/src/bob/feature.py\n"
            "+++ b/src/bob/feature.py\n"
            "@@ -0,0 +1,1 @@\n"
            "+import spec_quality_score\n"
        )
        findings, tool_failure = slopsquatting_check(ws, diff)
        assert not any(
            f.message and "spec_quality_score" in f.message for f in findings
        )

    def test_returns_findings_list_and_optional_message(self, tmp_path: Path) -> None:
        """Return shape is a (list, Optional[str]) pair."""
        ws = _make_workspace(tmp_path)
        findings, tool_failure = slopsquatting_check(ws, diff=None)
        assert isinstance(findings, list)
        assert tool_failure is None or isinstance(tool_failure, str)

    def test_empty_diff_no_findings(self, tmp_path: Path) -> None:
        """A diff with no imports yields no findings and no network probe."""
        ws = _make_workspace(tmp_path)
        diff = (
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -0,0 +1,1 @@\n"
            "+hello world\n"
        )
        findings, tool_failure = slopsquatting_check(ws, diff)
        assert findings == []


class TestWhitelistContainsLocalModule:
    def test_spec_quality_score_in_whitelist(self, tmp_path: Path) -> None:
        """The recurring false-positive module is in the whitelist."""
        ws = _make_workspace(tmp_path)
        assert "spec_quality_score" in whitelist_local_modules(ws)
