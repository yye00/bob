"""Tests for executable acceptance criteria (``pytest:`` / ``python:`` forms).

These tests exercise the rigor upgrade in
``src/bob/enhanced_verification.py`` that lets criteria be ACTUALLY executed
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

from unittest.mock import patch

from bob.enhanced_verification import (
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

        monkeypatch.setenv("BOB_CRITERION_EXEC_TIMEOUT", "5")
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
        monkeypatch.setenv("BOB_CRITERION_EXEC_TIMEOUT", "not-a-number")
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
        assert "open" in details.lower()
        assert not target.exists()

    def test_open_for_read_is_refused(self, tmp_path):
        """``open(<path>)`` (read mode) is now ALSO refused.

        The previous policy allowed read-mode opens for sentinel files,
        but ``python: open("/proc/self/environ").read()`` is a one-line
        secret-exfiltration bypass against any criterion runtime that
        leaks parent-process environment to children. We ban ``open``
        outright; specs that need to read files should use the
        ``pytest:`` form (``tmp_path`` is the right fixture for that).
        """
        sentinel = tmp_path / "sentinel.txt"
        sentinel.write_text("ok")
        passed, details = _check_criterion_with_details(
            criterion=f'python: assert open("{sentinel}").read() == "ok"',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False, (
            f"open() must be refused outright, got passed=True details={details!r}"
        )
        assert "refused" in details.lower()
        assert "open" in details.lower()

    def test_open_proc_self_environ_is_refused(self, tmp_path):
        """The exact bypass: ``open('/proc/self/environ').read()``.

        This was the pre-fix exploit — read-mode ``open`` was permitted,
        and ``/proc/self/environ`` exposes every env var inherited by
        the criterion subprocess (including ANTHROPIC_API_KEY).
        """
        passed, details = _check_criterion_with_details(
            criterion='python: open("/proc/self/environ").read()',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "open" in details.lower()

    def test_builtins_open_is_refused(self, tmp_path):
        """``import builtins; builtins.open(...).read()`` must be refused.

        ``builtins`` itself is now in the banned-modules set, so the
        ``import builtins`` line should already be the first AST hit.
        Either way the criterion must NOT execute.
        """
        passed, details = _check_criterion_with_details(
            criterion='python: import builtins; builtins.open("/etc/passwd").read()',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        # Either ``builtins`` (module ban) or ``open`` (attr-call ban) is
        # acceptable as the surfaced reason — both close this hole.
        assert "builtins" in details.lower() or "open" in details.lower()

    def test_dunder_builtins_open_is_refused(self, tmp_path):
        """``__builtins__.open(...)`` must be refused.

        ``__builtins__`` is in the banned-attribute set (covered by the
        existing dunder bans); we add a regression test pinning the
        specific access pattern so it cannot regress quietly.
        """
        passed, details = _check_criterion_with_details(
            criterion='python: __builtins__.open("/etc/passwd").read()',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_attribute_open_is_refused(self, tmp_path):
        """``some.attr.open(...)`` is refused via the attribute-call ban.

        Even if a future module wrapper is added that exposes ``open``
        as an attribute, calling it must remain blocked.
        """
        passed, details = _check_criterion_with_details(
            criterion='python: x = object(); x.open("/etc/passwd")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "open" in details.lower()

    def test_bare_open_reference_is_refused(self, tmp_path):
        """``f = open`` is refused via the Name-binding check.

        Catches the rename-then-call smuggling pattern.
        """
        passed, details = _check_criterion_with_details(
            criterion="python: f = open",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "open" in details.lower()

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

    # ------------------------------------------------------------------
    # Bypass-closure tests — ensure each historical allowlist hole stays
    # closed. These exercise the second hardening pass that added
    # ``importlib``/``runpy``/``pkgutil`` to the banned-module set,
    # ``getattr``/``setattr``/``delattr``/``globals``/``locals``/``vars``
    # to the banned-call-name set, and the dunder escape-path attributes
    # (``__class__``, ``__bases__``, ``__subclasses__``, ``__mro__``,
    # ``mro``, ``__dict__``, ``__globals__``, ``__builtins__``,
    # ``__init_subclass__``, ``__getattribute__``) to the banned-attribute
    # set.
    # ------------------------------------------------------------------

    def test_importlib_import_module_is_refused(self, tmp_path):
        """``importlib.import_module("os")`` is the canonical bypass for
        the ``import os`` ban — ``importlib`` itself must be banned."""
        passed, details = _check_criterion_with_details(
            criterion=(
                'python: import importlib; m = importlib.import_module("os")'
            ),
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "importlib" in details.lower()

    def test_runpy_is_refused(self, tmp_path):
        """``runpy`` can execute modules as ``__main__``; it must be banned."""
        passed, details = _check_criterion_with_details(
            criterion='python: import runpy; runpy.run_module("os")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "runpy" in details.lower()

    def test_pkgutil_is_refused(self, tmp_path):
        """``pkgutil`` exposes loader-fetching primitives; it must be banned."""
        passed, details = _check_criterion_with_details(
            criterion='python: import pkgutil; pkgutil.find_loader("os")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "pkgutil" in details.lower()

    def test_getattr_with_dunder_import_is_refused(self, tmp_path):
        """``getattr(__import__("os"), "system")("id")`` must be refused.

        ``getattr`` lets the attacker construct any attribute name dynamically,
        so the attribute allowlist alone is insufficient — ``getattr`` is
        banned by name regardless of its arguments.
        """
        passed, details = _check_criterion_with_details(
            criterion='python: getattr(__import__("os"), "system")("id")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        # ``__import__`` happens to be the first banned token reached in
        # AST walk order, but either token is acceptable proof of refusal.
        assert "getattr" in details or "__import__" in details

    def test_getattr_alone_is_refused_even_with_benign_args(self, tmp_path):
        """``getattr`` is banned regardless of args — even ``getattr(x, "y")``.

        A spec that legitimately needs ``getattr`` should use ``pytest:``
        with a real test file. We deliberately do not try to allow
        "obviously safe" ``getattr`` calls because the attacker controls
        the args.
        """
        passed, details = _check_criterion_with_details(
            criterion='python: x = object(); v = getattr(x, "__class__")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_setattr_is_refused(self, tmp_path):
        """``setattr(sys, "argv", [])`` must be refused — state-mutation hole."""
        passed, details = _check_criterion_with_details(
            criterion='python: import sys; setattr(sys, "argv", [])',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "setattr" in details

    def test_delattr_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion='python: x = object(); delattr(x, "y")',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "delattr" in details

    def test_globals_is_refused(self, tmp_path):
        """``globals()`` returns a mutable dict over the caller namespace."""
        passed, details = _check_criterion_with_details(
            criterion='python: g = globals(); g["x"] = 1',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "globals" in details

    def test_locals_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="python: l = locals()",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "locals" in details

    def test_vars_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="python: v = vars()",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "vars" in details

    def test_class_bases_subclasses_chain_is_refused(self, tmp_path):
        """``().__class__.__bases__[0].__subclasses__()`` is the classic
        sandbox-escape pattern. Every link in the chain is independently
        banned via the dunder-attribute set."""
        passed, details = _check_criterion_with_details(
            criterion="python: ().__class__.__bases__[0].__subclasses__()",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        # The first banned attribute hit in AST walk order is acceptable.
        assert (
            "__class__" in details
            or "__bases__" in details
            or "__subclasses__" in details
        )

    def test_mro_method_is_refused(self, tmp_path):
        """``cls.mro()`` and ``cls.__mro__`` must both be refused."""
        passed, details = _check_criterion_with_details(
            criterion="python: x = int.mro()",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "mro" in details

    def test_dunder_mro_attribute_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion='python: x = "".__class__.__mro__',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_func_globals_attribute_is_refused(self, tmp_path):
        """``f.__globals__`` exposes the caller's globals — refused."""
        passed, details = _check_criterion_with_details(
            criterion="python: f = lambda: 0; g = f.__globals__",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "__globals__" in details

    def test_builtins_getattribute_is_refused(self, tmp_path):
        """``__builtins__.__getattribute__("eval")`` must be refused.

        Both ``__builtins__`` (the namespace) and ``__getattribute__``
        (the dunder accessor) are independently banned.
        """
        passed, details = _check_criterion_with_details(
            criterion=(
                'python: f = __builtins__.__getattribute__("eval")'
            ),
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()

    def test_dict_attribute_is_refused(self, tmp_path):
        """``obj.__dict__`` is a mutable namespace and is refused."""
        passed, details = _check_criterion_with_details(
            criterion="python: x = object(); d = x.__dict__",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "__dict__" in details

    def test_benign_json_dumps_still_works(self, tmp_path):
        """``import json; json.dumps(...)`` is a normal benign use case."""
        passed, details = _check_criterion_with_details(
            criterion='python: import json; assert json.dumps({"a": 1}) == \'{"a": 1}\'',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"benign json criterion incorrectly refused: {details!r}"
        assert details == ""

    def test_benign_sum_assertion_still_works(self, tmp_path):
        """``assert sum([1,2,3]) == 6`` must not be a false positive."""
        passed, details = _check_criterion_with_details(
            criterion="python: assert sum([1,2,3]) == 6",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"benign sum criterion incorrectly refused: {details!r}"
        assert details == ""

    # ------------------------------------------------------------------
    # R4: ``os`` / ``pathlib`` / ``tempfile`` / ``glob`` ban (filesystem
    # and environment access). Closes the bypass:
    #   ``python: import os; fd=os.open(...,os.O_WRONLY|os.O_CREAT,0o600);
    #     os.write(fd, os.getenv('ANTHROPIC_API_KEY','').encode())``
    # ------------------------------------------------------------------

    def test_os_import_is_refused(self, tmp_path):
        """A bare ``import os`` is refused — closes the API-key
        exfiltration bypass that read ``os.getenv`` and wrote with
        ``os.open``/``os.write``."""
        passed, details = _check_criterion_with_details(
            criterion="python: import os; os.getenv('FOO')",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "os" in details.lower()

    def test_pathlib_is_refused(self, tmp_path):
        """``pathlib`` provides equivalent filesystem primitives
        (``Path.read_text``, ``Path.write_text``) so it must also be
        banned. Closes the ``import pathlib; pathlib.Path('/etc/passwd')
        .read_text()`` bypass."""
        passed, details = _check_criterion_with_details(
            criterion="python: import pathlib; pathlib.Path('/etc/passwd').read_text()",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "pathlib" in details.lower()

    def test_tempfile_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="python: import tempfile; tempfile.mkstemp()",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "tempfile" in details.lower()

    def test_glob_is_refused(self, tmp_path):
        passed, details = _check_criterion_with_details(
            criterion="python: import glob; glob.glob('/etc/*')",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        assert "refused" in details.lower()
        assert "glob" in details.lower()

    def test_simple_arithmetic_assertion_still_works(self, tmp_path):
        """``python: assert 1+1 == 2`` — the simplest possible passing
        criterion. No imports, no false positives."""
        passed, details = _check_criterion_with_details(
            criterion="python: assert 1+1 == 2",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"benign arithmetic criterion refused: {details!r}"
        assert details == ""

    def test_json_dumps_empty_list_still_works(self, tmp_path):
        """``import json; assert json.dumps([]) == '[]'`` — common form
        for testing serialization, must not be refused."""
        passed, details = _check_criterion_with_details(
            criterion="python: import json; assert json.dumps([]) == '[]'",
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"json.dumps criterion refused: {details!r}"
        assert details == ""

    def test_user_module_compute_assertion_still_works(self, tmp_path):
        """``from <user-module> import compute; assert compute() == 42``
        — the canonical use of the python: form. Must not be refused
        even with the expanded ban list (only stdlib filesystem/network
        modules are banned)."""
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
        assert passed is True, f"user-module compute criterion refused: {details!r}"
        assert details == ""

    def test_json_dumps_after_open_ban_still_works(self, tmp_path):
        """Pin a representative ``Allowed`` case after the ``open`` ban.

        The R5-001 / R5-006 hardening pass must not turn benign criteria
        like ``import json; assert json.dumps({"a":1}) == '{"a": 1}'``
        into refusals. ``json`` is not in the banned-modules set, no
        ``open`` call is made, no banned attribute is touched.
        """
        passed, details = _check_criterion_with_details(
            criterion='python: import json; assert json.dumps({"a": 1}) == \'{"a": 1}\'',
            workspace=tmp_path,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"benign json criterion refused after open ban: {details!r}"
        assert details == ""


# ---------------------------------------------------------------------------
# R4: pytest argument-injection — ``--`` sentinel
# ---------------------------------------------------------------------------
#
# A criterion ``pytest: --co tests/`` used to land ``--co`` in the flag
# position of pytest's argv. ``--co`` makes pytest collect-only and exit
# 0 with no failures, which our success heuristic happily accepted. The
# fix inserts a ``--`` sentinel between the fixed flags and the criterion
# expression so pytest treats every following token as a path/nodeid.


class TestPytestArgumentInjection:
    def test_co_flag_in_expression_is_treated_as_path(
        self, workspace_with_passing_test
    ):
        """``pytest: --co`` must not silently pass.

        With the ``--`` sentinel, ``--co`` is treated as a literal path
        which does not exist, so pytest's collection step fails.
        """
        passed, details = _check_criterion_with_details(
            criterion="pytest: --co",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False, (
            "regression: '--co' criterion silently passed — "
            "argument-injection sentinel '--' is missing"
        )

    def test_normal_pytest_node_still_works(
        self, workspace_with_passing_test
    ):
        """Regression: normal ``pytest: <path>::<nodeid>`` invocations
        must continue to pass after inserting the ``--`` sentinel."""
        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_passes",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, (
            f"regression: normal pytest node failed after sentinel "
            f"insertion: {details!r}"
        )
        assert details == ""


# ---------------------------------------------------------------------------
# R4-004 regression: validator must FAIL CLOSED on internal exceptions
# ---------------------------------------------------------------------------


class TestValidatorFailsClosedOnException:
    """Recurrence guard for the R1-005 / R2-002 permissive-default pattern.

    If anything inside ``validate_acceptance_criteria`` raises (including
    bugs in ``_check_criterion_with_details``), the function MUST return
    ``(False, ...)`` — not ``(True, "skipped")``. Returning True on a
    crash silently rubber-stamps every feature whose validator hits an
    exception, which is the exact failure mode that bit us twice before.
    """

    def test_returns_false_when_check_criterion_raises(self, tmp_path):
        """Patching the per-criterion check to raise must surface as a
        FAILURE from the aggregator — never a permissive pass."""
        with patch(
            "bob.enhanced_verification._check_criterion_with_details",
            side_effect=RuntimeError("simulated validator crash"),
        ):
            passed, details = validate_acceptance_criteria(
                workspace=tmp_path,
                acceptance_criteria=["pytest: tests/test_real.py::test_x"],
                is_python_project=True,
            )

        assert passed is False, (
            "Validator crashed; must NOT return True (recurrence of "
            "R1-005/R2-002 permissive default)"
        )
        assert "crashed" in details.lower() or "manual review" in details.lower(), (
            f"Expected crash-explaining details, got: {details!r}"
        )
        assert "simulated validator crash" in details

    def test_returns_false_when_criteria_list_iteration_raises(self, tmp_path):
        """Even an exception that isn't from the per-criterion check —
        e.g. raised while parsing the criteria list — must still fail
        closed. We simulate it via a custom iterable whose __iter__ blows
        up; the function should catch it and return False."""

        class _Boom:
            def __iter__(self):
                raise RuntimeError("kaboom-during-iter")

        # Pass an object that triggers the exception inside the try-block.
        # Note: we bypass the str-parse path by passing an object that
        # is_str check (False), then enters the loop and raises on iter.
        passed, details = validate_acceptance_criteria(
            workspace=tmp_path,
            acceptance_criteria=_Boom(),  # type: ignore[arg-type]
            is_python_project=True,
        )
        assert passed is False
        assert "kaboom-during-iter" in details

    def test_does_not_return_skipped_pass(self, tmp_path):
        """The OLD behaviour returned True with a 'skipped' message. The
        new behaviour must NOT include that string AND must not return
        True on exception. Verifies both halves of the contract."""
        with patch(
            "bob.enhanced_verification._check_criterion_with_details",
            side_effect=ValueError("something broke"),
        ):
            passed, details = validate_acceptance_criteria(
                workspace=tmp_path,
                acceptance_criteria=["pytest: tests/test_x.py::test_y"],
                is_python_project=True,
            )
        assert passed is False, (
            "MUST be False on exception; True is the bug we're guarding "
            "against."
        )
        assert "skipped" not in details.lower(), (
            f"Old permissive language leaked into new fail-closed path: "
            f"{details!r}"
        )


# ---------------------------------------------------------------------------
# R10-012: pytest: criterion fails on test-in-class — fallback to -k
# ---------------------------------------------------------------------------
#
# Real bob run against examples/04_swedish_circle_spec.yaml exposed this:
# specs declare strict pytest nodeids like
# ``pytest: tests/test_geometry.py::test_ground_y_interpolates_linearly``.
# When the agent (correctly, idiomatically) groups related tests in a class
# the actual nodeid becomes
# ``tests/test_geometry.py::TestGroundSurfaceInterpolation::test_ground_y_interpolates_linearly``
# and the strict path::name lookup fails with exit 4 / "not found", which
# is wrongly interpreted as a verification failure.
#
# Fix: when the strict lookup fails AND pytest output reports "not found" /
# "no tests ran" AND the expression contains ``::``, retry as
# ``pytest <file_prefix> -k <test_name>``. ``-k`` substring-matches on the
# test name, finding both free-function and class-based variants.
#
# The fallback is gated tightly: real test failures (exit 1, "FAILED" /
# "AssertionError") are NOT re-run with -k — that would mask genuine bugs.


@pytest.fixture
def workspace_with_class_based_test(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where the test the spec references lives inside a class.

    Mirrors the swedish-circle F003 case: spec writes
    ``tests/test_geometry.py::test_ground_y_interpolates_linearly`` while
    the agent organizes that test inside ``TestGroundSurfaceInterpolation``.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_geometry.py"
    test_file.write_text(
        textwrap.dedent(
            """
            class TestGroundSurfaceInterpolation:
                def test_ground_y_interpolates_linearly(self):
                    assert 1 + 1 == 2

                def test_ground_y_outside_range_raises(self):
                    raise AssertionError("intentionally failing test")
            """
        ).strip()
        + "\n"
    )
    return tmp_path


class TestPytestCriterionClassFallback:
    """R10-012 — strict nodeid + ``-k`` fallback for test-in-class."""

    def test_pytest_criterion_finds_free_function(self, workspace_with_passing_test):
        """Baseline regression: a free-function test still resolves on the
        strict path::name nodeid without any fallback."""
        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_passes",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, f"strict free-function lookup failed: {details!r}"
        assert details == ""

    def test_pytest_criterion_finds_class_based_test_via_fallback(
        self, workspace_with_class_based_test
    ):
        """The fix: the spec asks for ``test_ground_y_interpolates_linearly``
        with the bare path::name nodeid; the agent put the test in a class.
        The verifier must fall back to ``-k`` and find it.
        """
        passed, details = _check_criterion_with_details(
            criterion=(
                "pytest: tests/test_geometry.py::test_ground_y_interpolates_linearly"
            ),
            workspace=workspace_with_class_based_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, (
            f"R10-012: class-based test was not found via -k fallback: {details!r}"
        )
        assert details == ""

    def test_pytest_criterion_falls_back_only_on_not_found(
        self, workspace_with_class_based_test
    ):
        """A real test failure (assertion error) must NOT trigger the -k
        fallback. The fallback is gated on "not found" / "no tests ran" —
        actual failures should surface as failures, not get silently retried.

        We point at the class-based ``test_ground_y_outside_range_raises``
        via its full nodeid (so the strict lookup finds it and runs it);
        the test itself raises AssertionError, so it must stay a failure.
        """
        passed, details = _check_criterion_with_details(
            criterion=(
                "pytest: tests/test_geometry.py"
                "::TestGroundSurfaceInterpolation"
                "::test_ground_y_outside_range_raises"
            ),
            workspace=workspace_with_class_based_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        # We should see the strict-attempt failure surface, not a -k
        # fallback summary (the test was found and failed; no fallback
        # should have happened).
        assert "exit=" in details
        # If the fallback wrongly fired we'd see the "-k fallback" tag in
        # the message. Make sure we did not.
        assert "-k fallback" not in details, (
            f"fallback wrongly fired for a real test failure: {details!r}"
        )

    def test_pytest_criterion_reports_both_attempts_on_dual_failure(
        self, workspace_with_passing_test
    ):
        """When the strict nodeid is missing AND the -k name is also missing,
        the error message must include details from BOTH attempts so the
        spec author can tell the two failure modes apart.
        """
        # The test name "test_does_not_exist_anywhere" matches no test in
        # the workspace by either strict nodeid or -k substring.
        passed, details = _check_criterion_with_details(
            criterion=(
                "pytest: tests/test_real.py::test_does_not_exist_anywhere"
            ),
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is False
        # The dual-failure error message should mention BOTH attempts.
        assert "strict" in details.lower(), (
            f"missing strict-attempt section in dual-failure message: {details!r}"
        )
        assert "-k" in details or "fallback" in details.lower(), (
            f"missing fallback-attempt section in dual-failure message: {details!r}"
        )
        # Both exits should be reported.
        assert "strict exit=" in details
        assert "fallback exit=" in details

    def test_pytest_criterion_strict_pass_does_not_trigger_fallback(
        self, workspace_with_passing_test, monkeypatch
    ):
        """Performance/correctness: when the strict nodeid lookup succeeds,
        the fallback subprocess must NEVER be spawned. We assert this by
        counting calls into ``_run_with_pgroup_timeout``.
        """
        from bob import enhanced_verification as ev

        call_count = {"n": 0}
        original = ev._run_with_pgroup_timeout

        def counting(*args, **kwargs):
            call_count["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(ev, "_run_with_pgroup_timeout", counting)

        passed, details = _check_criterion_with_details(
            criterion="pytest: tests/test_real.py::test_passes",
            workspace=workspace_with_passing_test,
            is_python_project=True,
            is_cmake_project=False,
            is_opm_project=False,
        )
        assert passed is True, details
        assert call_count["n"] == 1, (
            f"strict pass must not spawn the -k fallback subprocess; "
            f"got {call_count['n']} pytest invocations"
        )
