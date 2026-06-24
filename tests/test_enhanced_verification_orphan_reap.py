"""Tests for _run_shell_with_pgroup_timeout in bob.enhanced_verification.

This test suite verifies that the pgroup-killing shell runner:
1. Returns the expected (stdout, stderr, returncode, timed_out) tuple shape.
2. Actually kills the entire process group on timeout — not just the shell —
   so grandchildren (orphans) are reaped rather than accumulating.
3. Does not time out on fast-completing commands.
4. Passes stdout/stderr through correctly on success.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import pathlib

import pytest

from bob.enhanced_verification import _run_shell_with_pgroup_timeout


# ---------------------------------------------------------------------------
# Basic return-tuple shape
# ---------------------------------------------------------------------------


class TestRunShellWithPgroupTimeoutReturnShape:
    """Verify the (stdout, stderr, returncode, timed_out) tuple contract."""

    def test_returns_four_tuple(self, tmp_path):
        result = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"print('hello')\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_return_types(self, tmp_path):
        stdout, stderr, returncode, timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"print('hi')\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert isinstance(stdout, str)
        assert isinstance(stderr, str)
        assert isinstance(returncode, int)
        assert isinstance(timed_out, bool)

    def test_successful_exit_timed_out_is_false(self, tmp_path):
        _stdout, _stderr, _rc, timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"exit(0)\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert timed_out is False

    def test_successful_exit_returncode_zero(self, tmp_path):
        _stdout, _stderr, returncode, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"exit(0)\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert returncode == 0

    def test_nonzero_exit_returncode_propagated(self, tmp_path):
        _stdout, _stderr, returncode, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"exit(42)\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert returncode == 42

    def test_stdout_captured(self, tmp_path):
        stdout, _stderr, _rc, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"print('hello-world')\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert "hello-world" in stdout

    def test_stderr_captured(self, tmp_path):
        _stdout, stderr, _rc, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"import sys; sys.stderr.write('err-output\\n')\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert "err-output" in stderr

    def test_multiline_stdout(self, tmp_path):
        stdout, _stderr, returncode, timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"print('line1'); print('line2'); print('line3')\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert returncode == 0
        assert timed_out is False
        assert "line1" in stdout
        assert "line2" in stdout
        assert "line3" in stdout


# ---------------------------------------------------------------------------
# Timeout behaviour
# ---------------------------------------------------------------------------


class TestRunShellWithPgroupTimeoutOnTimeout:
    """Verify timeout triggers and orphan reaping on POSIX."""

    def test_timeout_sets_timed_out_true(self, tmp_path):
        _stdout, _stderr, returncode, timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"import time; time.sleep(60)\"",
            cwd=tmp_path,
            timeout_s=1,
        )
        assert timed_out is True

    def test_timeout_returncode_negative_one(self, tmp_path):
        _stdout, _stderr, returncode, timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"import time; time.sleep(60)\"",
            cwd=tmp_path,
            timeout_s=1,
        )
        assert timed_out is True
        assert returncode == -1

    @pytest.mark.skipif(os.name != "posix", reason="pgroup kill is POSIX-only")
    def test_grandchild_reaped_on_timeout(self, tmp_path):
        """A shell spawning a grandchild sleep must NOT leave the grandchild alive
        after timeout.  We write a sentinel file from the grandchild, then verify
        it is reaped before it can complete a longer sleep."""
        sentinel = tmp_path / "grandchild_ran.txt"
        # Grandchild sleeps 30s — if it isn't killed it would outlive this test.
        # Shell spawns it in background so the shell itself exits quickly,
        # exposing the orphan scenario that _run_shell_with_pgroup_timeout fixes.
        cmd = (
            f"bash -c "
            f"\"({sys.executable} -c 'import time, pathlib; "
            f"pathlib.Path({str(sentinel)!r}).write_text(\\\"alive\\\"); "
            f"time.sleep(30)') & "
            f"sleep 30\""
        )
        start = time.monotonic()
        _stdout, _stderr, returncode, timed_out = _run_shell_with_pgroup_timeout(
            cmd,
            cwd=tmp_path,
            timeout_s=2,
        )
        elapsed = time.monotonic() - start

        assert timed_out is True
        # Must return within a few seconds — not hang for 30s.
        assert elapsed < 15, f"Took {elapsed:.1f}s — grandchild likely not reaped"

        # Give a moment for any lingering grandchild to complete (it shouldn't).
        time.sleep(0.5)

        # Verify no grandchild process with our sentinel is still running.
        # If the grandchild was orphaned, it would still be sleeping.
        result = subprocess.run(
            ["pgrep", "-f", str(sentinel)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            "Grandchild process is still running — pgroup kill failed to reap it"
        )

    @pytest.mark.skipif(os.name != "posix", reason="pgroup kill is POSIX-only")
    def test_popen_uses_start_new_session(self, tmp_path):
        """Indirectly verify start_new_session is used: process group of a child
        should differ from our own process group on POSIX."""
        marker_file = tmp_path / "pgid.txt"
        cmd = f"{sys.executable} -c \"import os; open({str(marker_file)!r}, 'w').write(str(os.getpgid(0)))\""
        _stdout, _stderr, returncode, timed_out = _run_shell_with_pgroup_timeout(
            cmd,
            cwd=tmp_path,
            timeout_s=5,
        )
        assert returncode == 0
        assert timed_out is False
        child_pgid = int(marker_file.read_text().strip())
        our_pgid = os.getpgid(0)
        # With start_new_session=True the child creates its own session/pgroup.
        assert child_pgid != our_pgid, (
            "Child process group matches parent — start_new_session may not be set"
        )


# ---------------------------------------------------------------------------
# Environment variable passthrough
# ---------------------------------------------------------------------------


class TestRunShellWithPgroupTimeoutEnv:
    """Verify env kwarg is forwarded to the subprocess."""

    def test_custom_env_var_available_in_command(self, tmp_path):
        env = os.environ.copy()
        env["_TEST_PGROUP_SECRET"] = "xyzzy42"
        stdout, _stderr, returncode, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"import os; print(os.environ.get('_TEST_PGROUP_SECRET', 'MISSING'))\"",
            cwd=tmp_path,
            timeout_s=10,
            env=env,
        )
        assert returncode == 0
        assert "xyzzy42" in stdout

    def test_no_env_kwarg_inherits_parent_env(self, tmp_path):
        # When env=None the child inherits the parent environment.
        # We rely on PATH existing in the parent so the shell can find commands.
        stdout, _stderr, returncode, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"import os; print(bool(os.environ.get('PATH', '')))\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert returncode == 0
        assert "True" in stdout


# ---------------------------------------------------------------------------
# cwd passthrough
# ---------------------------------------------------------------------------


class TestRunShellWithPgroupTimeoutCwd:
    """Verify cwd is applied to the subprocess."""

    def test_cwd_is_working_directory(self, tmp_path):
        # The command prints cwd; it must match tmp_path (resolved).
        stdout, _stderr, returncode, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"import os; print(os.getcwd())\"",
            cwd=tmp_path,
            timeout_s=10,
        )
        assert returncode == 0
        # Resolve both sides so /tmp vs /private/tmp differences on macOS don't bite.
        assert pathlib.Path(stdout.strip()).resolve() == tmp_path.resolve()

    def test_cwd_accepts_string(self, tmp_path):
        stdout, _stderr, returncode, _timed_out = _run_shell_with_pgroup_timeout(
            f"{sys.executable} -c \"import os; print(os.getcwd())\"",
            cwd=str(tmp_path),
            timeout_s=10,
        )
        assert returncode == 0
        assert pathlib.Path(stdout.strip()).resolve() == tmp_path.resolve()


# ---------------------------------------------------------------------------
# Integration with check_behavioral_signature / check_deterministic_output /
# check_resource_limit — smoke tests to confirm the helper is wired in.
# ---------------------------------------------------------------------------


class TestIntegrationWithVerifierChecks:
    """Smoke-test that the three verifier checks use _run_shell_with_pgroup_timeout
    and don't regress to subprocess.run(shell=True, timeout=N)."""

    def test_check_behavioral_signature_uses_shell_helper(self, tmp_path):
        from bob.enhanced_verification import check_behavioral_signature
        # A command that prints a steadily decreasing loss must pass.
        cmd = (
            f"{sys.executable} -c \""
            "for i, v in enumerate([1.0, 0.8, 0.6, 0.4, 0.2]):"
            " print(f'loss: {v}')"
            "\""
        )
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            monotone_decrease=True,
            timeout=10,
        )
        assert passed, f"Expected pass but got: {details}"

    def test_check_deterministic_output_uses_shell_helper(self, tmp_path):
        from bob.enhanced_verification import check_deterministic_output
        # A command that always prints the same output regardless of seed must pass.
        cmd = f"{sys.executable} -c \"print('constant-output')\""
        passed, details = check_deterministic_output(
            command=cmd,
            workspace=tmp_path,
            seeds=[0, 1, 2],
            timeout=10,
        )
        assert passed, f"Expected pass but got: {details}"

    def test_check_resource_limit_uses_shell_helper(self, tmp_path):
        from bob.enhanced_verification import check_resource_limit
        # A fast command with no constraints must pass.
        cmd = f"{sys.executable} -c \"print('done')\""
        passed, details = check_resource_limit(
            command=cmd,
            workspace=tmp_path,
            wall_clock_s=5,
            timeout=10,
        )
        assert passed, f"Expected pass but got: {details}"

    def test_check_behavioral_signature_timeout_fails_gracefully(self, tmp_path):
        from bob.enhanced_verification import check_behavioral_signature
        cmd = f"{sys.executable} -c \"import time; time.sleep(60)\""
        passed, details = check_behavioral_signature(
            command=cmd,
            workspace=tmp_path,
            timeout=1,
        )
        assert not passed
        assert "timed out" in details.lower()
