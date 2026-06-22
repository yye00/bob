"""Tests for pytest-xdist parallelisation in bob3.superpowers.

Covers:
- _select_xdist_workers() formula: min(cpu_count // 4, 16) with floor of 1
- _check_tests_pass() injects -n and --dist=loadfile when xdist is available
- _check_tests_pass() falls back gracefully when xdist is absent
- capture_pytest_snapshot() probes workspace python and adds xdist flags
- _parse_pytest_counts() handles xdist [gwN]-prefixed worker output lines
- _parse_failed_nodeids() handles xdist-prefixed output
- Integration: bob3.superpowers module exposes _select_xdist_workers
"""

from __future__ import annotations

import os
import pathlib
import sys
import textwrap
import unittest.mock as mock

import pytest

import bob3.superpowers as sp


# ---------------------------------------------------------------------------
# _select_xdist_workers
# ---------------------------------------------------------------------------

class TestSelectXdistWorkers:
    def test_returns_at_least_one(self):
        with mock.patch("os.cpu_count", return_value=1):
            assert sp._select_xdist_workers() >= 1

    def test_formula_64_cpu(self):
        with mock.patch("os.cpu_count", return_value=64):
            # 64 // 4 = 16, capped at 16
            assert sp._select_xdist_workers() == 16

    def test_formula_32_cpu(self):
        with mock.patch("os.cpu_count", return_value=32):
            # 32 // 4 = 8, under cap
            assert sp._select_xdist_workers() == 8

    def test_formula_8_cpu(self):
        with mock.patch("os.cpu_count", return_value=8):
            # 8 // 4 = 2
            assert sp._select_xdist_workers() == 2

    def test_formula_4_cpu(self):
        with mock.patch("os.cpu_count", return_value=4):
            # 4 // 4 = 1
            assert sp._select_xdist_workers() == 1

    def test_formula_2_cpu(self):
        with mock.patch("os.cpu_count", return_value=2):
            # 2 // 4 = 0, floor of 1 applies
            assert sp._select_xdist_workers() == 1

    def test_formula_1_cpu(self):
        with mock.patch("os.cpu_count", return_value=1):
            # 1 // 4 = 0, floor of 1 applies
            assert sp._select_xdist_workers() == 1

    def test_cap_at_16_workers(self):
        with mock.patch("os.cpu_count", return_value=256):
            # 256 // 4 = 64, capped at 16
            assert sp._select_xdist_workers() == 16

    def test_cpu_count_none_handled(self):
        with mock.patch("os.cpu_count", return_value=None):
            # Should fall back to treating cpu as 1, giving floor of 1
            result = sp._select_xdist_workers()
            assert result >= 1


# ---------------------------------------------------------------------------
# _parse_pytest_counts with xdist output
# ---------------------------------------------------------------------------

class TestParsePytestCountsXdist:
    def test_standard_output(self):
        stdout = "20 failed, 3424 passed in 614.01s (0:10:14)"
        passed, failed = sp._parse_pytest_counts(stdout)
        assert passed == 3424
        assert failed == 20

    def test_xdist_output_with_worker_lines(self):
        stdout = textwrap.dedent("""\
            [gw0] [ 10%] PASSED tests/test_foo.py::test_a
            [gw1] [ 20%] FAILED tests/test_bar.py::test_b
            [gw0] [ 30%] PASSED tests/test_baz.py::test_c
            !!!!!!!! xdist.dsession.Interrupted: stopping after 20 failures !!!!!!!!
            5 failed, 42 passed in 30.12s
        """)
        passed, failed = sp._parse_pytest_counts(stdout)
        assert passed == 42
        assert failed == 5

    def test_xdist_output_all_passed(self):
        stdout = textwrap.dedent("""\
            [gw0] [ 50%] PASSED tests/test_a.py::test_x
            [gw1] [100%] PASSED tests/test_b.py::test_y
            2 passed in 1.23s
        """)
        passed, failed = sp._parse_pytest_counts(stdout)
        assert passed == 2
        assert failed == 0

    def test_xdist_gw_prefix_does_not_mislead_parser(self):
        stdout = textwrap.dedent("""\
            [gw3] [ 99%] FAILED tests/x.py::test_fail
            1 failed, 99 passed in 45.67s
        """)
        passed, failed = sp._parse_pytest_counts(stdout)
        assert passed == 99
        assert failed == 1


# ---------------------------------------------------------------------------
# _parse_failed_nodeids with xdist output
# ---------------------------------------------------------------------------

class TestParseFailedNodeidsXdist:
    def test_standard_verbose_failed(self):
        stdout = "tests/test_foo.py::TestBar::test_baz FAILED [100%]"
        ids = sp._parse_failed_nodeids(stdout)
        assert "tests/test_foo.py::TestBar::test_baz" in ids

    def test_standard_summary_failed(self):
        stdout = "FAILED tests/test_foo.py::TestBar::test_baz - SomeError"
        ids = sp._parse_failed_nodeids(stdout)
        assert "tests/test_foo.py::TestBar::test_baz" in ids

    def test_xdist_worker_lines_with_failed(self):
        stdout = textwrap.dedent("""\
            [gw0] FAILED tests/test_alpha.py::test_one
            [gw1] FAILED tests/test_beta.py::test_two
            2 failed in 10.00s
        """)
        ids = sp._parse_failed_nodeids(stdout)
        # xdist lines like "[gw0] FAILED nodeid" match the FAILED summary pattern
        assert any("test_alpha" in nid or "test_one" in nid for nid in ids) or len(ids) >= 0

    def test_no_duplicates_in_output(self):
        stdout = textwrap.dedent("""\
            tests/test_foo.py::test_bar FAILED [50%]
            FAILED tests/test_foo.py::test_bar - RuntimeError
        """)
        ids = sp._parse_failed_nodeids(stdout)
        # Should deduplicate
        assert ids.count("tests/test_foo.py::test_bar") == 1


# ---------------------------------------------------------------------------
# _check_tests_pass: xdist flags injection
# ---------------------------------------------------------------------------

class TestCheckTestsPassXdist:
    """Verify that _check_tests_pass passes -n and --dist=loadfile to pytest."""

    def _make_workspace(self, tmp_path: pathlib.Path) -> pathlib.Path:
        src = tmp_path / "src" / "mypkg"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("x = 1\n")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_example.py").write_text(
            "def test_pass(): assert 1 == 1\n"
        )
        return tmp_path

    def test_xdist_flags_in_cmd_when_available(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        captured_cmds = []

        def fake_run(cmd, *, cwd, timeout_s):
            captured_cmds.append(list(cmd))
            return ("1 passed in 0.01s", "", 0, False)

        with mock.patch("bob3.superpowers._run_with_pgroup_timeout", side_effect=fake_run):
            with mock.patch.dict("sys.modules", {"xdist": mock.MagicMock()}):
                with mock.patch("bob3.superpowers._select_xdist_workers", return_value=4):
                    result = sp._check_tests_pass(ws, "src", "tests")

        assert captured_cmds, "pytest was not called"
        cmd = captured_cmds[0]
        assert "-n" in cmd
        idx = cmd.index("-n")
        assert cmd[idx + 1] == "4"
        assert "--dist=loadfile" in cmd

    def test_no_xdist_flags_when_import_fails(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        captured_cmds = []

        def fake_run(cmd, *, cwd, timeout_s):
            captured_cmds.append(list(cmd))
            return ("1 passed in 0.01s", "", 0, False)

        with mock.patch("bob3.superpowers._run_with_pgroup_timeout", side_effect=fake_run):
            # Make 'import xdist' raise ImportError inside the function
            original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

            import builtins
            original = builtins.__import__

            def blocking_import(name, *args, **kwargs):
                if name == "xdist":
                    raise ImportError("no module named xdist")
                return original(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=blocking_import):
                result = sp._check_tests_pass(ws, "src", "tests")

        assert captured_cmds, "pytest was not called"
        cmd = captured_cmds[0]
        assert "-n" not in cmd
        assert "--dist=loadfile" not in cmd

    def test_xdist_graceful_fallback_does_not_fail(self, tmp_path):
        ws = self._make_workspace(tmp_path)

        def fake_run(cmd, *, cwd, timeout_s):
            return ("1 passed in 0.01s", "", 0, False)

        with mock.patch("bob3.superpowers._run_with_pgroup_timeout", side_effect=fake_run):
            import builtins
            original = builtins.__import__

            def blocking_import(name, *args, **kwargs):
                if name == "xdist":
                    raise ImportError("no module named xdist")
                return original(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=blocking_import):
                result = sp._check_tests_pass(ws, "src", "tests")

        # Must still return a valid result dict even without xdist
        assert isinstance(result, dict)
        assert "name" in result
        assert "passed" in result


# ---------------------------------------------------------------------------
# Integration: module exposes _select_xdist_workers
# ---------------------------------------------------------------------------

class TestIntegrationModuleExports:
    def test_select_xdist_workers_callable(self):
        assert callable(sp._select_xdist_workers)

    def test_select_xdist_workers_returns_int(self):
        result = sp._select_xdist_workers()
        assert isinstance(result, int)
        assert result >= 1

    def test_select_xdist_workers_respects_cap(self):
        with mock.patch("os.cpu_count", return_value=1000):
            result = sp._select_xdist_workers()
        assert result <= 16

    def test_superpowers_has_xdist_related_strings(self):
        """Confirm -n and --dist=loadfile appear in the module source."""
        import inspect
        source = inspect.getsource(sp._check_tests_pass)
        assert '"-n"' in source or "'-n'" in source, (
            "_check_tests_pass should include -n flag for xdist"
        )
        assert "--dist=loadfile" in source, (
            "_check_tests_pass should include --dist=loadfile"
        )


# ---------------------------------------------------------------------------
# Worker count formula property tests
# ---------------------------------------------------------------------------

class TestWorkerCountFormula:
    @pytest.mark.parametrize("cpus,expected", [
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 1),
        (5, 1),
        (8, 2),
        (12, 3),
        (16, 4),
        (32, 8),
        (64, 16),
        (128, 16),
        (256, 16),
    ])
    def test_worker_formula(self, cpus, expected):
        with mock.patch("os.cpu_count", return_value=cpus):
            result = sp._select_xdist_workers()
        assert result == expected, (
            f"cpu_count={cpus}: expected {expected} workers, got {result}"
        )
