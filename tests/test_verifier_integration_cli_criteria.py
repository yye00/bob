"""Tests for 'integration:' and 'CLI command:' acceptance criteria in enhanced_verification.

Verifies:
  - integration: pass (module file exists + another .py imports it)
  - integration: fail (module file missing, or no imports found)
  - CLI command: pass (--flag literal found in workspace .py)
  - CLI flag:    pass (synonym)
  - CLI command: fail (no --flag found in workspace .py)
  - Existing Function defined: and File exists: paths are unaffected
"""
from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.enhanced_verification import (
    _check_criterion,
    _integration_wired,
    validate_acceptance_criteria,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


# ---------------------------------------------------------------------------
# _integration_wired unit tests
# ---------------------------------------------------------------------------


class TestIntegrationWired:
    def test_pass_src_layout(self, tmp_path):
        """Module under src/ exists and another .py imports it."""
        _write(
            tmp_path / "src" / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        _write(
            tmp_path / "src" / "mypkg" / "caller.py",
            """\
            from mypkg.mymod import hello
            """,
        )
        assert _integration_wired(tmp_path, "mypkg.mymod") is True

    def test_pass_flat_layout(self, tmp_path):
        """Module at root level exists and another .py imports it."""
        _write(
            tmp_path / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        _write(
            tmp_path / "mypkg" / "caller.py",
            """\
            import mypkg.mymod
            """,
        )
        assert _integration_wired(tmp_path, "mypkg.mymod") is True

    def test_pass_init_layout(self, tmp_path):
        """Module as __init__.py and another .py imports it."""
        _write(
            tmp_path / "src" / "mypkg" / "mymod" / "__init__.py",
            """\
            def hello(): pass
            """,
        )
        _write(
            tmp_path / "src" / "mypkg" / "caller.py",
            """\
            from mypkg.mymod import hello
            """,
        )
        assert _integration_wired(tmp_path, "mypkg.mymod") is True

    def test_fail_module_missing(self, tmp_path):
        """Fails when the target module file does not exist."""
        _write(
            tmp_path / "src" / "mypkg" / "caller.py",
            """\
            from mypkg.mymod import hello
            """,
        )
        assert _integration_wired(tmp_path, "mypkg.mymod") is False

    def test_fail_no_import(self, tmp_path):
        """Fails when module exists but no .py imports it."""
        _write(
            tmp_path / "src" / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        # No other file imports mypkg.mymod
        assert _integration_wired(tmp_path, "mypkg.mymod") is False

    def test_no_substring_match(self, tmp_path):
        """import mypkg.mymod_other must NOT satisfy mypkg.mymod criterion."""
        _write(
            tmp_path / "src" / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        _write(
            tmp_path / "src" / "mypkg" / "caller.py",
            """\
            import mypkg.mymod_other
            """,
        )
        assert _integration_wired(tmp_path, "mypkg.mymod") is False

    def test_skips_build_and_venv(self, tmp_path):
        """Files under build/ and .venv/ are not counted as importers."""
        _write(
            tmp_path / "src" / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        _write(
            tmp_path / "build" / "mypkg" / "caller.py",
            """\
            from mypkg.mymod import hello
            """,
        )
        _write(
            tmp_path / ".venv" / "lib" / "caller.py",
            """\
            from mypkg.mymod import hello
            """,
        )
        assert _integration_wired(tmp_path, "mypkg.mymod") is False

    def test_never_raises_on_unreadable_file(self, tmp_path):
        """Exception in one file must be swallowed; function must not raise."""
        _write(
            tmp_path / "src" / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        bad = tmp_path / "caller.py"
        bad.write_bytes(b"\xff\xfe")  # Not valid UTF-8
        # Should not raise; may return False
        result = _integration_wired(tmp_path, "mypkg.mymod")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# CLI flag / command criterion via _check_criterion
# ---------------------------------------------------------------------------


class TestCliCriterion:
    def _check(self, criterion: str, workspace: pathlib.Path) -> bool:
        return _check_criterion(
            criterion=criterion,
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )

    def test_cli_flag_pass(self, tmp_path):
        """CLI flag: passes when flag literal found in a .py file."""
        _write(
            tmp_path / "src" / "cli.py",
            """\
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument('--max-concurrent-features', type=int)
            """,
        )
        assert self._check("CLI flag: --max-concurrent-features", tmp_path) is True

    def test_cli_command_pass(self, tmp_path):
        """CLI command: passes when any listed flag is found."""
        _write(
            tmp_path / "src" / "cli.py",
            """\
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument('--max-workers-8', type=int)
            """,
        )
        assert self._check("CLI command: bob run --max-workers-8", tmp_path) is True

    def test_cli_flag_with_digits(self, tmp_path):
        """Flags with digits in name (--max-workers-8) are handled."""
        _write(
            tmp_path / "src" / "cli.py",
            """\
            parser.add_argument('--max-workers-8', default=8)
            """,
        )
        assert self._check("CLI flag: --max-workers-8", tmp_path) is True

    def test_cli_flag_fail(self, tmp_path):
        """CLI flag: fails when flag is not present in workspace."""
        _write(
            tmp_path / "src" / "cli.py",
            """\
            parser.add_argument('--other-flag', type=int)
            """,
        )
        assert self._check("CLI flag: --missing-flag", tmp_path) is False

    def test_cli_command_multiple_flags_any_match(self, tmp_path):
        """CLI command: passes when any (not all) flags are found."""
        _write(
            tmp_path / "src" / "cli.py",
            """\
            parser.add_argument('--flag-a')
            """,
        )
        assert (
            self._check("CLI command: prog --flag-a --flag-b", tmp_path) is True
        )

    def test_cli_never_raises_on_bad_file(self, tmp_path):
        """Exception while reading a file must be swallowed."""
        bad = tmp_path / "cli.py"
        bad.write_bytes(b"\xff\xfe")
        result = self._check("CLI flag: --some-flag", tmp_path)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Existing patterns unaffected
# ---------------------------------------------------------------------------


class TestExistingPatternsUnaffected:
    def _check(self, criterion: str, workspace: pathlib.Path) -> bool:
        return _check_criterion(
            criterion=criterion,
            workspace=workspace,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )

    def test_file_exists_pass(self, tmp_path):
        f = tmp_path / "src" / "myfile.py"
        f.parent.mkdir(parents=True)
        f.touch()
        assert self._check("File exists: src/myfile.py", tmp_path) is True

    def test_file_exists_fail(self, tmp_path):
        assert self._check("File exists: src/nonexistent.py", tmp_path) is False

    def test_function_defined_pass(self, tmp_path):
        _write(
            tmp_path / "src" / "mymod.py",
            """\
            def my_func():
                pass
            """,
        )
        assert self._check("Function defined: mymod.my_func", tmp_path) is True

    def test_function_defined_fail(self, tmp_path):
        _write(
            tmp_path / "src" / "mymod.py",
            """\
            def other_func():
                pass
            """,
        )
        assert self._check("Function defined: mymod.my_func", tmp_path) is False


# ---------------------------------------------------------------------------
# validate_acceptance_criteria integration (end-to-end)
# ---------------------------------------------------------------------------


class TestValidateAcceptanceCriteria:
    def test_integration_criterion_pass(self, tmp_path):
        _write(
            tmp_path / "src" / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        _write(
            tmp_path / "src" / "mypkg" / "caller.py",
            """\
            from mypkg.mymod import hello
            """,
        )
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=["integration: mypkg.mymod"],
            is_python_project=True,
        )
        assert passed is True, details

    def test_integration_criterion_fail(self, tmp_path):
        # Module exists but no importer
        _write(
            tmp_path / "src" / "mypkg" / "mymod.py",
            """\
            def hello(): pass
            """,
        )
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=["integration: mypkg.mymod"],
            is_python_project=True,
        )
        assert passed is False

    def test_cli_criterion_pass(self, tmp_path):
        _write(
            tmp_path / "src" / "cli.py",
            """\
            parser.add_argument('--enable-feature')
            """,
        )
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=["CLI flag: --enable-feature"],
            is_python_project=True,
        )
        assert passed is True, details

    def test_cli_criterion_fail(self, tmp_path):
        _write(
            tmp_path / "src" / "cli.py",
            """\
            parser.add_argument('--other-flag')
            """,
        )
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=["CLI flag: --missing-flag"],
            is_python_project=True,
        )
        assert passed is False
