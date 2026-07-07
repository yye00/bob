"""Acceptance tests for the slopsquatting local-module whitelist.

Verifies the fix for the recurring false-positive where a locally-defined
module (e.g. ``spec_quality_score``) is flagged by the slopsquatting
heuristic as a missing PyPI distribution. Locally-defined modules found in
the generated-code tree must be whitelisted before any PyPI probe, while
genuinely-fictitious imports remain detectable.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob.security_scan import (
    is_local_module,
    slopsquatting_check,
    whitelist_local_modules,
)


def _make_workspace(tmp_path: Path) -> Path:
    """Build a minimal workspace with a src/bob package + local module."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "bob-workspace"\n'
    )
    pkg = tmp_path / "src" / "bob"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "spec_quality_score.py").write_text("SCORE = 1.0\n")
    return tmp_path


class TestIsLocalModule:
    def test_local_module_whitelisted(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        assert is_local_module("spec_quality_score", ws) is True

    def test_local_package_whitelisted(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        assert is_local_module("bob", ws) is True

    def test_third_party_not_whitelisted(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        assert is_local_module("requests", ws) is False

    def test_root_level_module_whitelisted(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        (ws / "spawn_next_generation.py").write_text("x = 1\n")
        assert is_local_module("spawn_next_generation", ws) is True

    def test_returns_bool(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        assert isinstance(is_local_module("spec_quality_score", ws), bool)


class TestWhitelistLocalModules:
    def test_recurring_false_positive_module_in_whitelist(self, tmp_path: Path) -> None:
        """The recurring ``spec_quality_score`` false positive is whitelisted."""
        ws = _make_workspace(tmp_path)
        assert "spec_quality_score" in whitelist_local_modules(ws)

    def test_returns_set(self, tmp_path: Path) -> None:
        assert isinstance(whitelist_local_modules(tmp_path), set)

    def test_third_party_absent(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        result = whitelist_local_modules(ws)
        assert "numpy" not in result
        assert "requests" not in result


class TestSlopsquattingCheck:
    def test_local_import_not_flagged(self, tmp_path: Path) -> None:
        """A local import must not be flagged even if absent from PyPI."""
        ws = _make_workspace(tmp_path)
        diff = (
            "--- a/src/bob/feature.py\n"
            "+++ b/src/bob/feature.py\n"
            "@@ -0,0 +1,1 @@\n"
            "+import spec_quality_score\n"
        )
        with patch("bob.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(ws, diff)
        assert not any(
            f.message and "spec_quality_score" in f.message for f in findings
        )

    def test_fictitious_import_still_flagged(self, tmp_path: Path) -> None:
        """A genuinely non-local, non-PyPI import is still flagged."""
        ws = _make_workspace(tmp_path)
        diff = (
            "--- a/src/bob/feature.py\n"
            "+++ b/src/bob/feature.py\n"
            "@@ -0,0 +1,1 @@\n"
            "+import totally_fake_pkg_xyz\n"
        )
        with patch("bob.security_checks._pypi_package_exists") as mock_probe:
            mock_probe.return_value = False
            findings, _ = slopsquatting_check(ws, diff)
        assert any(
            f.message and "totally_fake_pkg_xyz" in f.message for f in findings
        )

    def test_returns_tuple(self, tmp_path: Path) -> None:
        ws = _make_workspace(tmp_path)
        result = slopsquatting_check(ws, diff=None)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], list)
        assert result[1] is None or isinstance(result[1], str)
