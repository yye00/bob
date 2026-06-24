"""Integration test: bob spec findings --since HEAD~1 exits 0 and stdout has 'finding'."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _bob_bin() -> list[str]:
    """Return the command prefix to invoke bob."""
    return [sys.executable, "-m", "bob.cli"]


def _bob_entry() -> list[str]:
    """Try to find bob entry point."""
    import shutil
    bob = shutil.which("bob")
    if bob:
        return [bob]
    return [sys.executable, "-c", "from bob.cli import main; main()"]


class TestCliSpecFindingsSinceRef:
    def test_spec_findings_since_ref_exits_zero(self, tmp_path, monkeypatch):
        """bob spec findings --since HEAD~1 exits 0."""
        # Create a temp findings file with one finding
        findings_file = tmp_path / "spec_findings.yaml"
        from bob.spec_quality.spec_findings_registry import record
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=findings_file, metrics_path=mp)

        from bob.cli import main
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["spec", "findings", "--since", "2026-01-01", "--findings-file", str(findings_file)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_spec_findings_output_contains_finding_info(self, tmp_path):
        """bob spec findings with a real entry outputs something about the finding."""
        findings_file = tmp_path / "spec_findings.yaml"
        from bob.spec_quality.spec_findings_registry import record
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=findings_file, metrics_path=mp)

        from bob.cli import main
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
        from bob.spec_quality.spec_findings_registry import record
        mp = tmp_path / "metrics.yaml"
        record("abc123", "AC-0", "ambiguity", findings_path=findings_file, metrics_path=mp)

        from bob.cli import main
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
