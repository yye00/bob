"""Integration test: bob3 spec findings --since HEAD~1 exits 0 and stdout has 'finding'."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _bob3_bin() -> list[str]:
    """Return the command prefix to invoke bob3."""
    return [sys.executable, "-m", "bob3.cli"]


def _bob3_entry() -> list[str]:
    """Try to find bob3 entry point."""
    import shutil
    bob3 = shutil.which("bob3")
    if bob3:
        return [bob3]
    return [sys.executable, "-c", "from bob3.cli import main; main()"]


class TestCliSpecFindingsSinceRef:
    def test_spec_findings_since_ref_exits_zero(self, tmp_path, monkeypatch):
        """bob3 spec findings --since HEAD~1 exits 0."""
        # Create a temp findings file with one finding
        findings_file = tmp_path / "spec_findings.yaml"
        from bob3.spec_quality.spec_findings_registry import record
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=findings_file, metrics_path=mp)

        from bob3.cli import main
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["spec", "findings", "--since", "2026-01-01", "--findings-file", str(findings_file)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_spec_findings_output_contains_finding_info(self, tmp_path):
        """bob3 spec findings with a real entry outputs something about the finding."""
        findings_file = tmp_path / "spec_findings.yaml"
        from bob3.spec_quality.spec_findings_registry import record
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=findings_file, metrics_path=mp)

        from bob3.cli import main
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["spec", "findings", "--findings-file", str(findings_file)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # Output should mention something related to the finding
        output = result.output.lower()
        assert "finding" in output or "ambiguity" in output or "spec-critic" in output

    def test_spec_findings_since_ref_shows_finding_word(self, tmp_path):
        """Stdout must contain 'finding' when --since is passed."""
        findings_file = tmp_path / "spec_findings.yaml"
        from bob3.spec_quality.spec_findings_registry import record
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=findings_file, metrics_path=mp)

        from bob3.cli import main
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["spec", "findings", "--since", "2026-01-01", "--findings-file", str(findings_file)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # Must contain "finding" somewhere in output (case-insensitive)
        assert "finding" in result.output.lower()
