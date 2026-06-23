"""Tests for bob3.security_checks (Round 0 Task 2 — Gap #2).

Covers each of the four sub-checks (pip-audit, detect-secrets, bandit,
slopsquatting) with both a triggering fixture and a clean fixture.

All subprocess calls and HTTP probes are mocked — these tests never
touch the network and never invoke the real pip-audit / bandit binaries.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob3.models import SecurityFinding, SecurityResult
from bob3.security_checks import (
    _extract_imports_from_diff,
    _extract_imports_from_tree,
    _is_hard_fail,
    _normalise_to_distribution,
    _pypi_package_exists,
    _run_bandit,
    _run_detect_secrets,
    _run_pip_audit,
    _run_slopsquatting,
    run_security_checks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["x"], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Empty Python workspace skeleton."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("def hello():\n    return 'hi'\n")
    return tmp_path


# ---------------------------------------------------------------------------
# AC2: model fields
# ---------------------------------------------------------------------------


def test_security_finding_model_fields():
    f = SecurityFinding(
        tool="pip-audit",
        severity="high",
        message="x",
        file="a.py",
        line=3,
        cve_or_rule_id="CVE-2024-9999",
    )
    assert f.tool == "pip-audit"
    assert f.severity == "high"
    assert f.line == 3
    assert f.cve_or_rule_id == "CVE-2024-9999"


def test_security_result_model_fields():
    r = SecurityResult(
        hard_fail=True,
        findings=[],
        tool_failures=["pip-audit: timeout"],
        duration_seconds=1.23,
    )
    assert r.hard_fail is True
    assert r.findings == []
    assert r.tool_failures == ["pip-audit: timeout"]
    assert r.duration_seconds == 1.23


# ---------------------------------------------------------------------------
# Diff parsing helpers
# ---------------------------------------------------------------------------


def test_extract_imports_from_diff_picks_up_added_imports():
    diff = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@\n"
        "+import requests\n"
        "+from numpy import array\n"
        "-import os\n"  # stdlib; not added line
        "+import os\n"  # stdlib; should be filtered
    )
    pkgs = _extract_imports_from_diff(diff)
    assert "requests" in pkgs
    assert "numpy" in pkgs
    assert "os" not in pkgs  # stdlib filtered


def test_extract_imports_from_diff_returns_empty_for_none():
    assert _extract_imports_from_diff(None) == []
    assert _extract_imports_from_diff("") == []


def test_extract_imports_from_tree_walks_workspace(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import requests\nfrom numpy import array\n")
    (tmp_path / "src" / "__pycache__").mkdir()
    (tmp_path / "src" / "__pycache__" / "junk.py").write_text("import nope_pkg\n")
    pkgs = _extract_imports_from_tree(tmp_path)
    assert "requests" in pkgs
    assert "numpy" in pkgs
    assert "nope_pkg" not in pkgs  # __pycache__ skipped


def test_normalise_to_distribution_handles_known_aliases():
    assert _normalise_to_distribution("cv2") == "opencv-python"
    assert _normalise_to_distribution("PIL") == "Pillow"
    assert _normalise_to_distribution("requests") == "requests"  # passthrough


# ---------------------------------------------------------------------------
# Sub-check 1: pip-audit
# ---------------------------------------------------------------------------


def test_pip_audit_parses_vulnerabilities(workspace: Path):
    payload = {
        "dependencies": [
            {
                "name": "requests",
                "vulns": [
                    {"id": "GHSA-1234", "description": "remote code execution"},
                ],
            }
        ]
    }
    with patch("bob3.security_checks.subprocess.run") as m_run:
        m_run.return_value = _completed(stdout=json.dumps(payload), returncode=1)
        findings, err = _run_pip_audit(workspace, timeout=60)
    assert err is None
    assert len(findings) == 1
    assert findings[0].tool == "pip-audit"
    assert findings[0].cve_or_rule_id == "GHSA-1234"
    assert findings[0].severity == "medium"  # pip-audit findings are warn per AC4


def test_pip_audit_clean_returns_no_findings(workspace: Path):
    with patch("bob3.security_checks.subprocess.run") as m_run:
        m_run.return_value = _completed(stdout=json.dumps({"dependencies": []}), returncode=0)
        findings, err = _run_pip_audit(workspace, timeout=60)
    assert err is None
    assert findings == []


def test_pip_audit_timeout_returns_tool_failure(workspace: Path):
    with patch("bob3.security_checks.subprocess.run", side_effect=subprocess.TimeoutExpired("pip-audit", 60)):
        findings, err = _run_pip_audit(workspace, timeout=60)
    assert findings == []
    assert err is not None
    assert "timed out" in err


# ---------------------------------------------------------------------------
# Sub-check 2: detect-secrets
# ---------------------------------------------------------------------------


SECRET_DIFF = """\
--- a/config.py
+++ b/config.py
@@ -1,1 +1,2 @@
 # config
+AWS_SECRET = "AKIAIOSFODNN7EXAMPLE"
+API_KEY = "ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD"
"""


def test_detect_secrets_flags_aws_key_in_diff(workspace: Path):
    findings, err = _run_detect_secrets(workspace, diff=SECRET_DIFF, timeout=60)
    assert err is None
    assert len(findings) >= 1
    assert all(f.tool == "detect-secrets" for f in findings)
    assert all(f.severity == "high" for f in findings)


def test_detect_secrets_clean_diff_returns_nothing(workspace: Path):
    clean = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@\n"
        "+def hello():\n"
        "+    return 42\n"
    )
    findings, err = _run_detect_secrets(workspace, diff=clean, timeout=60)
    assert err is None
    assert findings == []


def test_detect_secrets_handles_missing_module(workspace: Path):
    # Simulate ImportError by patching the import inside the function.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "detect_secrets" or name.startswith("detect_secrets."):
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        findings, err = _run_detect_secrets(workspace, diff=SECRET_DIFF, timeout=60)
    assert findings == []
    assert err is not None and "detect-secrets" in err


# ---------------------------------------------------------------------------
# Sub-check 3: bandit
# ---------------------------------------------------------------------------


def test_bandit_parses_high_severity(workspace: Path):
    payload = {
        "results": [
            {
                "filename": "src/foo.py",
                "line_number": 12,
                "issue_severity": "HIGH",
                "issue_text": "Use of eval() detected",
                "test_id": "B307",
                "test_name": "blacklist",
            },
            {
                "filename": "src/bar.py",
                "line_number": 5,
                "issue_severity": "MEDIUM",
                "issue_text": "Possible binding to all interfaces",
                "test_id": "B104",
                "test_name": "hardcoded_bind_all_interfaces",
            },
        ]
    }
    with patch("bob3.security_checks.subprocess.run") as m_run:
        m_run.return_value = _completed(stdout=json.dumps(payload), returncode=1)
        findings, err = _run_bandit(workspace, timeout=60)
    assert err is None
    assert len(findings) == 2
    sev = {f.severity for f in findings}
    assert "high" in sev
    assert "medium" in sev


def test_bandit_clean_returns_no_findings(workspace: Path):
    with patch("bob3.security_checks.subprocess.run") as m_run:
        m_run.return_value = _completed(stdout=json.dumps({"results": []}), returncode=0)
        findings, err = _run_bandit(workspace, timeout=60)
    assert err is None
    assert findings == []


def test_bandit_unparseable_output_is_tool_failure(workspace: Path):
    with patch("bob3.security_checks.subprocess.run") as m_run:
        m_run.return_value = _completed(stdout="not json at all", returncode=0)
        findings, err = _run_bandit(workspace, timeout=60)
    assert findings == []
    assert err is not None
    assert "unparseable" in err


# ---------------------------------------------------------------------------
# Sub-check 4: slopsquatting
# ---------------------------------------------------------------------------


SLOP_DIFF = "+import nonexistent_pkg_xyz\n+from real_pkg import thing\n"


def test_slopsquatting_flags_404_packages(workspace: Path):
    def fake_exists(name, *, timeout):  # noqa: ARG001
        if name == "nonexistent_pkg_xyz":
            return False
        return True

    with patch("bob3.security_checks._pypi_package_exists", side_effect=fake_exists):
        findings, err = _run_slopsquatting(workspace, diff=SLOP_DIFF, timeout=60)
    assert err is None
    assert len(findings) == 1
    assert findings[0].tool == "slopsquatting"
    assert findings[0].severity == "high"
    assert "nonexistent_pkg_xyz" in findings[0].message


def test_slopsquatting_clean_returns_no_findings(workspace: Path):
    with patch("bob3.security_checks._pypi_package_exists", return_value=True):
        findings, err = _run_slopsquatting(workspace, diff=SLOP_DIFF, timeout=60)
    assert err is None
    assert findings == []


def test_slopsquatting_no_imports_returns_empty(workspace: Path):
    findings, err = _run_slopsquatting(workspace, diff="+# nothing to see\n", timeout=60)
    assert err is None
    assert findings == []


def test_slopsquatting_all_network_failures_records_tool_failure(workspace: Path):
    with patch("bob3.security_checks._pypi_package_exists", return_value=None):
        findings, err = _run_slopsquatting(workspace, diff=SLOP_DIFF, timeout=60)
    assert findings == []
    assert err is not None and "network" in err.lower()


def test_pypi_package_exists_handles_404():
    fake_err = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    with patch("bob3.security_checks.urllib.request.urlopen", side_effect=fake_err):
        assert _pypi_package_exists("nope", timeout=5) is False


def test_pypi_package_exists_handles_200():
    fake_resp = MagicMock()
    fake_resp.status = 200
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    with patch("bob3.security_checks.urllib.request.urlopen", return_value=fake_resp):
        assert _pypi_package_exists("requests", timeout=5) is True


# ---------------------------------------------------------------------------
# Severity policy & end-to-end runner
# ---------------------------------------------------------------------------


def test_is_hard_fail_secrets():
    f = [SecurityFinding(tool="detect-secrets", severity="high", message="x")]
    assert _is_hard_fail(f) is True


def test_is_hard_fail_slopsquatting():
    f = [SecurityFinding(tool="slopsquatting", severity="high", message="x")]
    assert _is_hard_fail(f) is True


def test_is_hard_fail_bandit_high():
    f = [SecurityFinding(tool="bandit", severity="high", message="x")]
    assert _is_hard_fail(f) is True


def test_is_hard_fail_bandit_medium_is_warn():
    f = [SecurityFinding(tool="bandit", severity="medium", message="x")]
    assert _is_hard_fail(f) is False


def test_is_hard_fail_pip_audit_is_always_warn():
    f = [SecurityFinding(tool="pip-audit", severity="high", message="x")]
    assert _is_hard_fail(f) is False


def test_run_security_checks_clean_returns_no_hard_fail(workspace: Path):
    with (
        patch("bob3.security_checks._run_pip_audit", return_value=([], None)),
        patch("bob3.security_checks._run_detect_secrets", return_value=([], None)),
        patch("bob3.security_checks._run_bandit", return_value=([], None)),
        patch("bob3.security_checks._run_slopsquatting", return_value=([], None)),
    ):
        result = run_security_checks(workspace, diff="+x = 1\n", timeout=30)
    assert isinstance(result, SecurityResult)
    assert result.hard_fail is False
    assert result.findings == []
    assert result.tool_failures == []
    assert result.duration_seconds >= 0


def test_run_security_checks_hard_fail_on_secret(workspace: Path):
    secret_finding = SecurityFinding(
        tool="detect-secrets", severity="high", message="AWS key",
    )
    with (
        patch("bob3.security_checks._run_pip_audit", return_value=([], None)),
        patch("bob3.security_checks._run_detect_secrets", return_value=([secret_finding], None)),
        patch("bob3.security_checks._run_bandit", return_value=([], None)),
        patch("bob3.security_checks._run_slopsquatting", return_value=([], None)),
    ):
        result = run_security_checks(workspace, diff="+secret\n", timeout=30)
    assert result.hard_fail is True
    assert any(f.tool == "detect-secrets" for f in result.findings)


def test_run_security_checks_tool_failure_recorded(workspace: Path):
    with (
        patch("bob3.security_checks._run_pip_audit", return_value=([], "pip-audit timed out")),
        patch("bob3.security_checks._run_detect_secrets", return_value=([], None)),
        patch("bob3.security_checks._run_bandit", return_value=([], None)),
        patch("bob3.security_checks._run_slopsquatting", return_value=([], None)),
    ):
        result = run_security_checks(workspace, diff=None, timeout=30)
    assert result.hard_fail is False  # tool_failed is info, never blocks
    assert any("pip-audit" in tf for tf in result.tool_failures)
    assert any(
        f.tool == "pip-audit" and f.severity == "info" and f.message.startswith("tool_failed:")
        for f in result.findings
    )


def test_run_security_checks_one_subcheck_crash_does_not_block_others(workspace: Path):
    """If pip-audit raises an unhandled exception, the other three still run."""
    with (
        patch("bob3.security_checks._run_pip_audit", side_effect=RuntimeError("kaboom")),
        patch("bob3.security_checks._run_detect_secrets", return_value=([], None)),
        patch("bob3.security_checks._run_bandit", return_value=([], None)),
        patch("bob3.security_checks._run_slopsquatting", return_value=([], None)),
    ):
        result = run_security_checks(workspace, diff="", timeout=30)
    assert result.hard_fail is False
    assert any("pip-audit" in tf and "kaboom" in tf for tf in result.tool_failures)


def test_run_security_checks_invokes_all_four_sub_checks(workspace: Path):
    with (
        patch("bob3.security_checks._run_pip_audit", return_value=([], None)) as m1,
        patch("bob3.security_checks._run_detect_secrets", return_value=([], None)) as m2,
        patch("bob3.security_checks._run_bandit", return_value=([], None)) as m3,
        patch("bob3.security_checks._run_slopsquatting", return_value=([], None)) as m4,
    ):
        run_security_checks(workspace, diff=None, timeout=42)
    assert m1.called
    assert m2.called
    assert m3.called
    assert m4.called
    # Each sub-check is allotted the per-check timeout (AC3)
    assert m1.call_args.kwargs["timeout"] == 42
    assert m2.call_args.kwargs["timeout"] == 42
    assert m3.call_args.kwargs["timeout"] == 42
    assert m4.call_args.kwargs["timeout"] == 42


def test_run_security_checks_default_timeout_is_60(workspace: Path):
    with (
        patch("bob3.security_checks._run_pip_audit", return_value=([], None)) as m1,
        patch("bob3.security_checks._run_detect_secrets", return_value=([], None)),
        patch("bob3.security_checks._run_bandit", return_value=([], None)),
        patch("bob3.security_checks._run_slopsquatting", return_value=([], None)),
    ):
        run_security_checks(workspace)  # no explicit timeout
    assert m1.call_args.kwargs["timeout"] == 60


# ---------------------------------------------------------------------------
# AC5: Check #9 wired into superpowers.run_verification_checklist POST-IMPLEMENTATION
# ---------------------------------------------------------------------------


def test_check_9_invoked_from_run_verification_checklist(tmp_path: Path):
    """The orchestrator-level checklist invokes run_security_checks.

    This is the "post-implementation, not inside the sub-agent" wiring
    requirement (AC5). We verify by mocking run_security_checks and
    asserting it was called.
    """
    from bob3 import superpowers

    # Build a minimal Python-project workspace so the security branch fires.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("def hi():\n    return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_hi():\n    assert True\n")

    fake_clean_result = SecurityResult(
        hard_fail=False, findings=[], tool_failures=[], duration_seconds=0.01,
    )
    with patch("bob3.superpowers.run_security_checks", return_value=fake_clean_result) as m:
        result = superpowers.run_verification_checklist(
            workspace=str(tmp_path),
            diff="+def hi():\n+    return 1\n",
            enable_security_check=True,
        )
    assert m.called
    names = [c["name"] for c in result["checks"]]
    assert "security_scan" in names


def test_check_9_hard_fail_blocks_overall_passed(tmp_path: Path):
    from bob3 import superpowers

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("def hi():\n    return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_hi():\n    assert True\n")

    fake_bad = SecurityResult(
        hard_fail=True,
        findings=[
            SecurityFinding(tool="detect-secrets", severity="high", message="aws key")
        ],
        tool_failures=[],
        duration_seconds=0.01,
    )
    with patch("bob3.superpowers.run_security_checks", return_value=fake_bad):
        result = superpowers.run_verification_checklist(
            workspace=str(tmp_path),
            diff="+SECRET=...\n",
            enable_security_check=True,
        )
    sec = [c for c in result["checks"] if c["name"] == "security_scan"][0]
    assert sec["passed"] is False
    assert sec.get("severity") == "error"
    assert result["passed"] is False  # blocked overall


def test_check_9_can_be_disabled(tmp_path: Path):
    from bob3 import superpowers

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("def hi():\n    return 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text("def test_hi():\n    assert True\n")

    with patch("bob3.superpowers.run_security_checks") as m:
        result = superpowers.run_verification_checklist(
            workspace=str(tmp_path),
            enable_security_check=False,
        )
    assert not m.called
    names = [c["name"] for c in result["checks"]]
    assert "security_scan" not in names


# ---------------------------------------------------------------------------
# AC: _read_first_party_packages includes tools/ and project-root .py modules
# ---------------------------------------------------------------------------


def test_read_first_party_packages_includes_tools_and_root(tmp_path: Path) -> None:
    """_read_first_party_packages must include tools/*.py and workspace-root .py files.

    This is the regression test for the recurring NH pattern: slopsquatting
    hard-fails on ``import spec_quality_score`` because _read_first_party_packages
    only walked src/<pkg>/ and missed tools/spec_quality_score.py.
    """
    from bob3.security_checks import _read_first_party_packages

    # Set up a realistic workspace skeleton
    (tmp_path / "src" / "mypkg").mkdir(parents=True)
    (tmp_path / "src" / "mypkg" / "__init__.py").write_text("")

    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# first-party tool\n")
    (tools / "foo.py").write_text("# another tool\n")

    (tmp_path / "root_helper.py").write_text("# root-level script\n")

    result = _read_first_party_packages(tmp_path)

    assert isinstance(result, set)
    # src package
    assert "mypkg" in result
    # tools/ .py stems
    assert "spec_quality_score" in result, (
        "spec_quality_score must be first-party — it lives at tools/spec_quality_score.py"
    )
    assert "foo" in result, "foo.py in tools/ must be first-party"
    # project-root .py stem
    assert "root_helper" in result, "root-level .py files must be first-party"
    # __init__ must never appear
    assert "__init__" not in result
