"""Tests verifying that a feature with 20 sibling-failing test files still passes
its own verification when its own tests are green and scoping is applied.

The key invariant: build_scoped_pytest_argv returns ONLY the current feature's
own paths, so sibling failures never contaminate the per-feature pytest run.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path
import textwrap

import pytest

from bob.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    assert_no_sibling_collection,
)

FEATURE_ID = "aaaaaaaa-0000-0000-0000-000000000001"


def _uuid(n: int) -> str:
    """Generate a deterministic sibling UUID for test n."""
    hex_n = format(n, "x").zfill(8)
    return f"{hex_n}-1111-1111-1111-111111111111"


class TestExcludesSiblings:
    """Scoped argv never includes sibling subtrees even with 20 failing siblings."""

    def _make_workspace(self, tmp_path: Path, n_siblings: int = 20) -> tuple[Path, str]:
        """Create a workspace with n_siblings failing subtrees + one green feature."""
        # Feature under test has one green test
        feature_dir = tmp_path / "tests" / FEATURE_ID
        feature_dir.mkdir(parents=True)
        green_test = feature_dir / "test_green.py"
        green_test.write_text(textwrap.dedent("""\
            def test_passes():
                assert 1 + 1 == 2
        """))

        # Sibling feature subtrees each with one failing test
        for i in range(n_siblings):
            sid = _uuid(i)
            sibling_dir = tmp_path / "tests" / sid
            sibling_dir.mkdir(parents=True)
            (sibling_dir / "__init__.py").write_text("")
            failing_test = sibling_dir / "test_fail.py"
            failing_test.write_text(textwrap.dedent("""\
                import pytest
                def test_always_fails():
                    pytest.fail("sibling stub not implemented")
            """))

        return tmp_path, FEATURE_ID

    def test_scoped_argv_excludes_all_siblings(self, tmp_path):
        ws, fid = self._make_workspace(tmp_path, n_siblings=20)
        argv = build_scoped_pytest_argv(fid, [], ws)
        # Must include own subtree
        assert f"tests/{fid}" in argv
        # Must not include any sibling
        for i in range(20):
            sid = _uuid(i)
            assert not any(sid in token for token in argv), (
                f"sibling {sid} found in argv: {argv}"
            )

    def test_scoped_argv_never_includes_bare_tests(self, tmp_path):
        ws, fid = self._make_workspace(tmp_path, n_siblings=20)
        argv = build_scoped_pytest_argv(fid, [], ws)
        # Bare "tests" or "tests/" must not appear
        assert "tests" not in argv
        assert "tests/" not in argv

    def test_own_feature_passes_with_green_tests(self, tmp_path):
        """Run pytest on scoped argv; expect exit 0 despite 20 sibling failures."""
        ws, fid = self._make_workspace(tmp_path, n_siblings=20)
        argv = build_scoped_pytest_argv(fid, [], ws)

        cmd = [sys.executable, "-m", "pytest"] + argv + ["--tb=short", "-q", "--color=no"]
        result = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # The scoped run should pass (only green test runs)
        assert result.returncode == 0, (
            f"Expected exit 0 (scoped run), got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_whole_suite_would_fail(self, tmp_path):
        """Sanity check: running the whole tests/ tree DOES fail (confirms the fix matters)."""
        ws, fid = self._make_workspace(tmp_path, n_siblings=20)

        cmd = [
            sys.executable, "-m", "pytest",
            "tests/",
            "--tb=no", "-q", "--color=no", "--maxfail=25",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Whole-suite should fail due to 20 sibling failures
        assert result.returncode != 0, (
            "Expected whole-suite run to fail (has 20 sibling failing tests), "
            f"but it exited {result.returncode}."
        )

    def test_assert_no_sibling_collection_blocks_contaminants(self, tmp_path):
        ws, fid = self._make_workspace(tmp_path, n_siblings=5)
        contaminated_argv = [f"tests/{_uuid(0)}", f"tests/{fid}"]
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(fid, contaminated_argv, ws)

    def test_scoped_pytest_acs_also_excluded_if_sibling(self, tmp_path):
        """If a pytest: AC accidentally names a sibling path, assert_no_sibling_collection catches it."""
        ws, fid = self._make_workspace(tmp_path, n_siblings=1)
        sibling_id = _uuid(0)
        # A malformed AC that references the sibling
        acs = [f"pytest: tests/{sibling_id}/test_fail.py"]
        argv = collect_feature_test_paths(fid, acs, ws)
        argv_list = sorted(argv)
        with pytest.raises(SiblingTestCollectionError):
            assert_no_sibling_collection(fid, argv_list, ws)
