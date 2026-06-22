"""End-to-end slopsquatting tests for local-tool import allowlist.

AC integration test:
  test_local_tool_import_not_flagged — workspace with tools/spec_quality_score.py
  plus a diff that adds 'import spec_quality_score' yields zero slopsquatting findings.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.security_checks import _run_slopsquatting, _read_first_party_packages


@pytest.fixture
def workspace_with_tool(tmp_path: Path) -> Path:
    """Workspace containing tools/spec_quality_score.py."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# local tool\ndef score(): pass\n")
    (tmp_path / "src").mkdir()
    return tmp_path


def test_local_tool_import_not_flagged(workspace_with_tool: Path) -> None:
    """A diff adding 'import spec_quality_score' must produce zero slopsquatting findings.

    spec_quality_score.py lives in workspace tools/ — it's first-party and
    must never trigger a PyPI probe.
    """
    diff = (
        "diff --git a/impl.py b/impl.py\n"
        "--- a/impl.py\n"
        "+++ b/impl.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+import spec_quality_score\n"
        "+\n"
        "+result = spec_quality_score.score()\n"
    )

    # We patch _pypi_package_exists to prove it is never called for spec_quality_score.
    # If the allowlist is working correctly, the name should be filtered out before
    # any PyPI probe happens.
    with patch("bob3.security_checks._pypi_package_exists") as mock_probe:
        mock_probe.return_value = False  # would flag if called
        findings, error = _run_slopsquatting(workspace_with_tool, diff, timeout=30)

    slopsquatting_findings = [
        f for f in findings
        if f.tool == "slopsquatting" and "spec_quality_score" in f.message
    ]
    assert len(slopsquatting_findings) == 0, (
        f"Expected zero slopsquatting findings for first-party 'spec_quality_score', "
        f"got: {slopsquatting_findings}"
    )


def test_first_party_set_contains_tool_name(workspace_with_tool: Path) -> None:
    """_read_first_party_packages must include 'spec_quality_score' when tools/spec_quality_score.py exists."""
    result = _read_first_party_packages(workspace_with_tool)
    assert "spec_quality_score" in result


def test_unknown_import_still_probed(workspace_with_tool: Path) -> None:
    """Imports not in tools/ must still be probed (ensure filtering is selective)."""
    diff = (
        "diff --git a/impl.py b/impl.py\n"
        "--- a/impl.py\n"
        "+++ b/impl.py\n"
        "@@ -0,0 +1 @@\n"
        "+import definitely_not_a_real_package_xyz123\n"
    )

    with patch("bob3.security_checks._pypi_package_exists") as mock_probe:
        mock_probe.return_value = False  # simulate not found
        findings, _ = _run_slopsquatting(workspace_with_tool, diff, timeout=30)

    flagged_names = [f.message for f in findings if f.tool == "slopsquatting"]
    assert any("definitely_not_a_real_package_xyz123" in msg for msg in flagged_names), (
        "Unknown package should be flagged by slopsquatting check"
    )


def test_no_findings_when_no_imports_in_diff(workspace_with_tool: Path) -> None:
    """A diff with no import statements must produce no slopsquatting findings."""
    diff = (
        "diff --git a/impl.py b/impl.py\n"
        "--- a/impl.py\n"
        "+++ b/impl.py\n"
        "@@ -1 +1 @@\n"
        "-x = 1\n"
        "+x = 2\n"
    )

    findings, error = _run_slopsquatting(workspace_with_tool, diff, timeout=30)

    slopsquatting_findings = [f for f in findings if f.tool == "slopsquatting"]
    assert len(slopsquatting_findings) == 0


def test_root_level_script_not_flagged(tmp_path: Path) -> None:
    """A diff adding 'import my_script' where my_script.py is at project root must not be flagged."""
    (tmp_path / "my_script.py").write_text("# root-level script\n")
    (tmp_path / "src").mkdir()

    diff = (
        "diff --git a/impl.py b/impl.py\n"
        "--- a/impl.py\n"
        "+++ b/impl.py\n"
        "@@ -0,0 +1 @@\n"
        "+import my_script\n"
    )

    with patch("bob3.security_checks._pypi_package_exists") as mock_probe:
        mock_probe.return_value = False
        findings, _ = _run_slopsquatting(tmp_path, diff, timeout=30)

    flagged = [f for f in findings if f.tool == "slopsquatting" and "my_script" in f.message]
    assert len(flagged) == 0, f"Root-level script 'my_script' should not be flagged: {flagged}"
