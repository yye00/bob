"""Tests for executable acceptance criteria (``pytest:`` / ``python:`` forms).

These tests exercise the rigor upgrade in
``src/bob3/enhanced_verification.py`` that lets criteria be ACTUALLY executed
as tests rather than matched by keyword heuristics.

Covered scenarios:
- ``pytest: <node>`` returns True when the underlying test passes.
- ``pytest: <node>`` returns False when the underlying test fails.
- ``python: <expr>`` returns True/False based on assertion outcome.
- Per-criterion timeout protection prevents runaway expressions from hanging.
- Missing workspace and missing/invalid targets degrade gracefully (False
  with explanatory details, never a crash).
- The ``validate_acceptance_criteria`` aggregator routes executable forms
  alongside legacy keyword-pattern criteria.
"""

from __future__ import annotations

import os
import pathlib
import textwrap

import pytest

from bob3.enhanced_verification import (
    _check_criterion,
    _check_criterion_with_details,
    validate_acceptance_criteria,
)


# ---------------------------------------------------------------------------
# Workspace fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_with_passing_test(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace containing a real pytest file with a passing and failing test."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_real.py"
    test_file.write_text(
        textwrap.dedent(
            """
            def test_passes():
                assert 1 + 1 == 2

            def test_fails():
                assert 1 + 1 == 3
            """
        ).strip()
        + "\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# pytest: form
# ---------------------------------------------------------------------------


class TestPytestCriterion:
    """The ``pytest:`` criterion form runs a real pytest invocation."""

    def test_passing_test_returns_true(self, workspace_with_passing_test):
        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_passes",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"expected pass, got details={details!r}"
        assert details == ""

    def test_failing_test_returns_false_with_details(self, workspace_with_passing_test):
        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_fails",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        # Details should include something about the pytest exit code so that
        # debugging surfaces useful info instead of just "False".
        assert "pytest" in details.lower()
        assert "exit=" in details

    def test_no_tests_collected_returns_false(self, workspace_with_passing_test):
        # Pointing at a nonexistent test node should not silently succeed.
        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_does_not_exist",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert details  # must explain why

    def test_missing_workspace_returns_false(self, tmp_path):
        # Use a path that does not exist.
        nonexistent = tmp_path / "does-not-exist"
        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_passes",
            workspace=nonexistent,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "workspace" in details.lower()

    def test_bool_only_check_criterion_still_works(self, workspace_with_passing_test):
        """``_check_criterion`` (bool-only) must still handle pytest forms."""
        assert (
            _check_criterion(
                criterion="pytest: tests/test_real.py::test_passes",
                workspace=workspace_with_passing_test,
                is_python_project=True,
                is_cmake_project=False,
                is_opm_project=False,
            )
            is True
        )
        assert (
            _check_criterion(
                criterion="pytest: tests/test_real.py::test_fails",
                workspace=workspace_with_passing_test,
                is_python_project=True,
                is_cmake_project=False,
                is_opm_project=False,
            )
            is False
        )


# ---------------------------------------------------------------------------
# python: form
# ---------------------------------------------------------------------------


class TestPythonCriterion:
    """The ``python:`` criterion form runs an inline expression via ``-c``."""

    def test_truthy_assertion_passes(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="python: assert 1 + 1 == 2",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"expected pass, got details={details!r}"
        assert details == ""

    def test_falsy_assertion_fails(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="python: assert 1 + 1 == 3",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "python" in details.lower()
        assert "exit=" in details

    def test_timeout_protection(self, tmp_path, monkeypatch):
        """A long-sleeping expression must be killed by the configured timeout.

        We assert on elapsed wall-clock time too: the only way this test can
        pass within ~30s is if the configured 5s timeout was actually honored
        and the long-sleeping subprocess was killed. Without the elapsed-time
        assertion, a regression that ignored the timeout would still let the
        test pass after waiting the full 120s.
        """
        import time as _time

        monkeypatch.setenv("BOB3_CRITERION_EXEC_TIMEOUT", "5")
        start = _time.perf_counter()
        passed, details = _check_criterion_with_details(
            criterion="python: import time; time.sleep(120)",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        elapsed = _time.perf_counter() - start
        assert passed is False
        assert "timed out" in details.lower()
        # 5s configured timeout + generous CI overhead must still leave us
        # well under the 120s sleep. If the timeout is not honored we'd pay
        # the full 120s.
        assert elapsed < 30, (
            f"timeout was not honored — elapsed={elapsed:.1f}s "
            f"(should be << 120s sleep)"
        )

    def test_empty_expression_returns_false(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="python:",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert details  # must explain

    def test_missing_workspace_returns_false(self, tmp_path):
        nonexistent = tmp_path / "no-such-dir"
        passed, details = _check_criterion_with_details(
            criterion="python: assert True",
            workspace=nonexistent,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "workspace" in details.lower()

    def test_bool_only_check_criterion_still_works(self, tmp_path):
        assert (
            _check_criterion(
                criterion="python: assert 1 + 1 == 2",
                workspace=tmp_path,
                is_python_project=True,
                is_cmake_project=False,
                is_opm_project=False,
            )
            is True
        )
        assert (
            _check_criterion(
                criterion="python: assert 1 + 1 == 3",
                workspace=tmp_path,
                is_python_project=True,
                is_cmake_project=False,
                is_opm_project=False,
            )
            is False
        )


# ---------------------------------------------------------------------------
# Integration with validate_acceptance_criteria
# ---------------------------------------------------------------------------


class TestValidateAcceptanceCriteriaWithExecutable:
    """End-to-end: aggregator routes executable forms correctly."""

    def test_all_executable_criteria_pass(self, workspace_with_passing_test):
        passed, details = validate_acceptance_criteria(
            workspace=workspace_with_passing_test,
            acceptance_criteria=[
                "python: assert 2 * 3 == 6",
                "pytest: tests/test_real.py::test_passes",
            ],
            is_python_project=True,
        )
        assert passed is True, details
        assert "All 2" in details

    def test_one_executable_criterion_fails(self, workspace_with_passing_test):
        passed, details = validate_acceptance_criteria(
            workspace=workspace_with_passing_test,
            acceptance_criteria=[
                "python: assert 2 * 3 == 6",
                "pytest: tests/test_real.py::test_fails",
            ],
            is_python_project=True,
        )
        assert passed is False
        # The aggregator should surface the failing criterion plus its details.
        assert "test_fails" in details
        assert "exit=" in details

    def test_legacy_keyword_form_still_works(self, workspace_with_passing_test):
        # "File exists:" is a legacy keyword form. The aggregator must keep
        # supporting it alongside the new executable forms.
        target = workspace_with_passing_test / "tests" / "test_real.py"
        assert target.exists()
        passed, details = validate_acceptance_criteria(
            workspace=workspace_with_passing_test,
            acceptance_criteria=[
                "File exists: tests/test_real.py",
                "python: assert True",
            ],
            is_python_project=True,
        )
        assert passed is True, details

    def test_default_timeout_when_env_invalid(
        self, workspace_with_passing_test, monkeypatch
    ):
        """An invalid timeout env var falls back to the default — no crash."""
        monkeypatch.setenv("BOB3_CRITERION_EXEC_TIMEOUT", "not-a-number")
        passed, details = validate_acceptance_criteria(
            workspace=workspace_with_passing_test,
            acceptance_criteria=["python: assert True"],
            is_python_project=True,
        )
        assert passed is True, details


# ---------------------------------------------------------------------------
# python: form — allowlist enforcement (security hardening)
# ---------------------------------------------------------------------------
#
# ``python: <expr>`` runs ``python -c <expr>`` in the workspace. Without
# enforcement, a malicious or careless spec could ``import os; os.system(...)``,
# read/write arbitrary files, or exfiltrate secrets via HTTP. The allowlist
# check is an AST scan that refuses banned imports and operations BEFORE the
# subprocess is launched.
#
# This is not a sandbox — it raises the bar from "trivially exploitable" to
# "requires real effort". Specs needing unrestricted access should use the
# ``pytest:`` form (sandboxed by the test framework itself).


class TestPythonCriterionAllowlist:
    """Verify the ``python:`` criterion form refuses dangerous operations."""

    def test_os_system_is_refused(self, tmp_path):
        """``import os; os.system(...)`` must be refused before execution.

        The marker file the criterion would create must NOT exist after the
        check returns — proof the subprocess never ran.
        """
        marker = tmp_path / "pwned"
        passed, details = _check_criterion_with_details(
            criterion=f'python: import os; os.system("touch {marker}")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "banned" in details.lower()
        assert not marker.exists(), (
            "criterion was supposed to be refused but the marker file exists"
        )

    def test_dunder_import_subprocess_is_refused(self, tmp_path):
        """``__import__("subprocess").run(...)`` must be refused.

        This is the bypass for a missing top-level ``import`` — refusing
        ``__import__`` by name closes that hole.
        """
        passed, details = _check_criterion_with_details(
            criterion='python: __import__("subprocess").run(["echo", "x"])',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        # Reason should mention __import__ specifically so the spec author
        # knows how to fix it.
        assert "__import__" in details

    def test_subprocess_import_is_refused(self, tmp_path):
        """A bare ``import subprocess`` should be refused even without a call."""
        passed, details = _check_criterion_with_details(
            criterion="python: import subprocess; assert subprocess",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "subprocess" in details.lower()

    def test_socket_module_is_refused(self, tmp_path):
        """Network access via ``socket`` is refused."""
        passed, details = _check_criterion_with_details(
            criterion="python: import socket; socket.socket()",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_urllib_is_refused(self, tmp_path):
        """``from urllib import request`` is refused."""
        passed, details = _check_criterion_with_details(
            criterion="python: from urllib import request; assert request",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_eval_is_refused(self, tmp_path):
        """A bare ``eval(...)`` call is refused."""
        passed, details = _check_criterion_with_details(
            criterion='python: eval("1+1")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_exec_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion='python: exec("x = 1")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_compile_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion='python: compile("1", "f", "eval")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_os_environ_is_refused(self, tmp_path):
        """Reading or mutating ``os.environ`` is refused."""
        passed, details = _check_criterion_with_details(
            criterion='python: import os; assert os.environ.get("PATH")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_os_remove_is_refused(self, tmp_path):
        """``os.remove`` (file deletion) is refused."""
        target = tmp_path / "f.txt"
        target.write_text("keep me")
        passed, details = _check_criterion_with_details(
            criterion=f'python: import os; os.remove("{target}")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert target.exists(), "criterion was refused; file should not be deleted"

    def test_os_unlink_is_refused(self, tmp_path):
        target = tmp_path / "f.txt"
        target.write_text("keep me")
        passed, details = _check_criterion_with_details(
            criterion=f'python: import os; os.unlink("{target}")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert target.exists()

    def test_shutil_rmtree_is_refused(self, tmp_path):
        """``shutil.rmtree`` is refused."""
        target = tmp_path / "subdir"
        target.mkdir()
        passed, details = _check_criterion_with_details(
            criterion=f'python: import shutil; shutil.rmtree("{target}")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert target.exists()

    def test_open_for_write_is_refused(self, tmp_path):
        """``open(<path>, "w")`` (write mode) is refused."""
        target = tmp_path / "out.txt"
        passed, details = _check_criterion_with_details(
            criterion=f'python: open("{target}", "w").write("x")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert not target.exists()

    def test_benign_assertion_still_works(self, tmp_path):
        """The classic ``python: assert 1 + 1 == 2`` still passes — no false positive."""
        passed, details = _check_criterion_with_details(
            criterion="python: assert 1 + 1 == 2",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"benign criterion incorrectly refused: {details!r}"
        assert details == ""

    def test_allowed_import_still_works(self, tmp_path):
        """``from <user-module> import f; assert f() == 42`` still works.

        The allowlist only blocks dangerous standard library modules; importing
        a user-defined module from the workspace is exactly the intended use
        of the ``python:`` form.
        """
        # Create a real ``mymodule.py`` in the workspace so the inline import
        # actually resolves.
        (tmp_path / "mymodule.py").write_text(
            "def compute():\n    return 42\n"
        )
        passed, details = _check_criterion_with_details(
            criterion="python: from mymodule import compute; assert compute() == 42",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"allowed-import criterion failed: {details!r}"
        assert details == ""

    def test_open_for_read_still_works(self, tmp_path):
        """``open(<path>)`` and ``open(<path>, "r")`` (read modes) are allowed."""
        sentinel = tmp_path / "sentinel.txt"
        sentinel.write_text("ok")
        passed, details = _check_criterion_with_details(
            criterion=f'python: assert open("{sentinel}").read() == "ok"',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"open-for-read incorrectly refused: {details!r}"

    def test_pytest_form_unaffected_by_allowlist(
        self, workspace_with_passing_test
    ):
        """The allowlist applies ONLY to ``python:`` form, not ``pytest:``.

        ``pytest:`` is sandboxed by the test framework itself; the allowlist
        is the explicit escape hatch documented in the SKILL.md.
        """
        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_passes",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, details
