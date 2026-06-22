"""Tests for bob3.pytest_scoper (F-R6-301).

Covers:
* direct-importer scoping
* transitive closure (A imports B imports C; change C → both test_a and
  test_b are selected)
* depth limit prevents runaway expansion
* fewer than 3 test files → returns None
* critical-path change → returns None
* missing files / missing repo roots do not crash
* smoke test against the real bob8 checkout (a known small leaf module)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.pytest_scoper import scope_tests_for_diff


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_fake_repo(tmp_path: Path) -> Path:
    """Create an empty src/bob3 + tests skeleton under ``tmp_path``."""
    (tmp_path / "src" / "bob3").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "bob3" / "__init__.py").write_text("")
    return tmp_path


def _src(repo: Path, name: str, body: str) -> None:
    (repo / "src" / "bob3" / name).write_text(body)


def _test(repo: Path, name: str, body: str) -> None:
    (repo / "tests" / name).write_text(body)


# ---------------------------------------------------------------------------
# Direct-importer case
# ---------------------------------------------------------------------------


def test_direct_importer_selects_only_relevant_tests(tmp_path: Path) -> None:
    repo = _mk_fake_repo(tmp_path)

    _src(repo, "leaf.py", "VALUE = 1\n")
    _src(repo, "user_a.py", "from bob3.leaf import VALUE\n")
    _src(repo, "user_b.py", "import bob3.leaf\n")
    _src(repo, "unrelated.py", "X = 2\n")

    _test(repo, "test_leaf.py", "from bob3.leaf import VALUE\n\ndef test_x():\n    assert VALUE == 1\n")
    _test(repo, "test_user_a.py", "from bob3.user_a import VALUE\n\ndef test_y():\n    pass\n")
    _test(repo, "test_user_b.py", "from bob3.user_b import bob3 as _\n\ndef test_b():\n    pass\n")
    _test(repo, "test_unrelated.py", "from bob3.unrelated import X\n\ndef test_z():\n    pass\n")

    result = scope_tests_for_diff(["src/bob3/leaf.py"], repo)

    assert result is not None
    names = {Path(p).name for p in result}
    assert "test_leaf.py" in names
    assert "test_user_a.py" in names  # direct importer (from-form)
    assert "test_user_b.py" in names  # direct importer (import-form)
    assert "test_unrelated.py" not in names


# ---------------------------------------------------------------------------
# Transitive closure
# ---------------------------------------------------------------------------


def test_transitive_closure_a_imports_b_imports_c(tmp_path: Path) -> None:
    repo = _mk_fake_repo(tmp_path)

    # Chain: a -> b -> c. Changing c should bring in both test_a and test_b.
    _src(repo, "c_mod.py", "C = 3\n")
    _src(repo, "b_mod.py", "from bob3.c_mod import C\nB = C + 1\n")
    _src(repo, "a_mod.py", "from bob3.b_mod import B\nA = B + 1\n")
    _src(repo, "spectator.py", "S = 9\n")  # uninvolved

    _test(repo, "test_a_mod.py", "from bob3.a_mod import A\n\ndef test():\n    pass\n")
    _test(repo, "test_b_mod.py", "from bob3.b_mod import B\n\ndef test():\n    pass\n")
    _test(repo, "test_c_mod.py", "from bob3.c_mod import C\n\ndef test():\n    pass\n")
    _test(repo, "test_spectator.py", "from bob3.spectator import S\n\ndef test():\n    pass\n")

    result = scope_tests_for_diff(["src/bob3/c_mod.py"], repo)

    assert result is not None
    names = {Path(p).name for p in result}
    assert names == {"test_a_mod.py", "test_b_mod.py", "test_c_mod.py"}


def test_max_depth_limits_expansion(tmp_path: Path) -> None:
    """With max_depth=1 we should NOT pull in grand-importers."""
    repo = _mk_fake_repo(tmp_path)

    _src(repo, "c_mod.py", "C = 3\n")
    _src(repo, "b_mod.py", "from bob3.c_mod import C\nB = 1\n")
    _src(repo, "a_mod.py", "from bob3.b_mod import B\nA = 1\n")

    _test(repo, "test_a_mod.py", "from bob3.a_mod import A\ndef test(): pass\n")
    _test(repo, "test_b_mod.py", "from bob3.b_mod import B\ndef test(): pass\n")
    _test(repo, "test_c_mod.py", "from bob3.c_mod import C\ndef test(): pass\n")

    # depth=1: from c we reach b but not a.
    result = scope_tests_for_diff(["src/bob3/c_mod.py"], repo, max_depth=1)

    # Need at least 3 to pass the fallback threshold; with depth=1 we get
    # only test_b_mod and test_c_mod → returns None.
    assert result is None


# ---------------------------------------------------------------------------
# Safety fallbacks
# ---------------------------------------------------------------------------


def test_few_tests_returns_none(tmp_path: Path) -> None:
    """Fewer than 3 test files discovered → return None (run full suite)."""
    repo = _mk_fake_repo(tmp_path)

    _src(repo, "lonely.py", "X = 0\n")
    _test(repo, "test_lonely.py", "from bob3.lonely import X\ndef test(): pass\n")
    # No other tests reference lonely / no other importer chain → only 1 test.

    result = scope_tests_for_diff(["src/bob3/lonely.py"], repo)
    assert result is None


@pytest.mark.parametrize(
    "critical_path",
    [
        "src/bob3/superpowers.py",
        "src/bob3/enhanced_verification.py",
        "src/bob3/evaluator.py",
        "src/bob3/orchestrator/run_loop.py",
        "src/bob3/orchestrator/claude_executor.py",
    ],
)
def test_critical_path_returns_none(tmp_path: Path, critical_path: str) -> None:
    """Critical-path files force a full pytest run."""
    repo = _mk_fake_repo(tmp_path)
    # Provide enough innocuous tests so a non-critical scope would succeed.
    _src(repo, "x.py", "X = 1\n")
    for i in range(5):
        _test(repo, f"test_x_{i}.py", "from bob3.x import X\ndef test(): pass\n")

    # A diff that includes both a critical-path file AND benign files still
    # bails to None.
    result = scope_tests_for_diff([critical_path, "src/bob3/x.py"], repo)
    assert result is None


def test_missing_file_does_not_crash(tmp_path: Path) -> None:
    """A changed file that no longer exists on disk must not raise."""
    repo = _mk_fake_repo(tmp_path)

    _src(repo, "alive.py", "A = 1\n")
    _test(repo, "test_alive.py", "from bob3.alive import A\ndef test(): pass\n")
    _test(repo, "test_alive_two.py", "from bob3.alive import A\ndef test(): pass\n")
    _test(repo, "test_alive_three.py", "from bob3.alive import A\ndef test(): pass\n")

    # ``ghost.py`` was deleted; we still pass it as a changed file.
    result = scope_tests_for_diff(
        ["src/bob3/ghost.py", "src/bob3/alive.py"], repo
    )

    # We should still scope on the surviving file (3+ tests).
    assert result is not None
    assert any("test_alive" in p for p in result)


def test_missing_repo_root_returns_none(tmp_path: Path) -> None:
    """If src/bob3 or tests/ are missing, scoping is impossible."""
    # tmp_path is empty — no src/, no tests/.
    result = scope_tests_for_diff(["src/bob3/foo.py"], tmp_path)
    assert result is None


def test_non_python_changed_files_are_ignored(tmp_path: Path) -> None:
    """README / yaml / etc. changes don't seed module scoping but also
    don't crash. With no real source seeds, we should return None."""
    repo = _mk_fake_repo(tmp_path)
    _src(repo, "x.py", "X = 1\n")
    _test(repo, "test_x.py", "from bob3.x import X\ndef test(): pass\n")

    result = scope_tests_for_diff(["README.md", "docs/x.rst"], repo)
    # Zero seeds → empty closure → zero tests → None.
    assert result is None


def test_changed_test_file_is_included(tmp_path: Path) -> None:
    """A modified test file should always be in the run set."""
    repo = _mk_fake_repo(tmp_path)
    _src(repo, "leaf.py", "VALUE = 1\n")
    _src(repo, "user_a.py", "from bob3.leaf import VALUE\n")
    _test(repo, "test_leaf.py", "from bob3.leaf import VALUE\ndef test(): pass\n")
    _test(repo, "test_user_a.py", "from bob3.user_a import VALUE\ndef test(): pass\n")
    _test(repo, "test_my_new.py", "def test(): pass\n")  # no module reference

    result = scope_tests_for_diff(
        ["src/bob3/leaf.py", "tests/test_my_new.py"], repo
    )
    assert result is not None
    names = {Path(p).name for p in result}
    assert "test_my_new.py" in names


# ---------------------------------------------------------------------------
# Real-codebase smoke test
# ---------------------------------------------------------------------------


def test_smoke_against_real_bob8(tmp_path: Path) -> None:
    """Run the scoper against the real bob8 worktree on a known leaf module.

    ``calibration_aware_budget_allocator.py`` has a dedicated test file
    and at least a handful of importers in the source tree, so scoping
    should produce >= 3 test files (i.e. NOT fall back to None).
    """
    # Walk up to find the worktree root (the dir containing src/bob3).
    here = Path(__file__).resolve()
    repo = here.parent.parent  # tests/ -> repo root
    src_root = repo / "src" / "bob3"
    if not src_root.is_dir():
        pytest.skip("Not running inside a bob3 checkout")

    # Use a well-isolated leaf module as the smoke target. ``container_runner``
    # has a small importer footprint and a dedicated test file
    # (``test_container_runner.py``), so the scoper should land on a small,
    # focused subset — neither None (indexing miss) nor the entire suite
    # (over-broad pattern).
    target = "src/bob3/container_runner.py"
    if not (repo / target).is_file():
        pytest.skip(f"{target} not present in this checkout")

    result = scope_tests_for_diff([target], repo)

    # We don't want to over-specify which tests get picked (the source
    # graph evolves), but we DO want to assert that the scoper found a
    # plausible non-empty result for a real module with a real test.
    assert result is not None, "smoke test expected scoping to succeed"
    names = {Path(p).name for p in result}
    assert "test_container_runner.py" in names, (
        f"missing container_runner test in scope: {sorted(names)[:10]}"
    )
    # Sanity bound: don't degenerate into "the whole suite". The real bob8
    # has ~200 test files; a leaf module like container_runner should
    # produce a small focused set (definitely well under half the suite).
    assert len(result) < 50, (
        f"scope exploded to {len(result)} tests — pattern may be too broad"
    )


def test_smoke_critical_path_real_bob8_returns_none() -> None:
    """A diff touching the real enhanced_verification.py must bail out."""
    here = Path(__file__).resolve()
    repo = here.parent.parent
    src_root = repo / "src" / "bob3"
    if not src_root.is_dir():
        pytest.skip("Not running inside a bob3 checkout")
    ev = repo / "src" / "bob3" / "enhanced_verification.py"
    if not ev.is_file():
        pytest.skip("enhanced_verification.py not present")
    assert scope_tests_for_diff(["src/bob3/enhanced_verification.py"], repo) is None


# ---------------------------------------------------------------------------
# Integration: capture_pytest_snapshot and enhanced_verification bridge
# ---------------------------------------------------------------------------


def test_enhanced_verification_bridge_helper_returns_scope() -> None:
    """``pytest_scope_for_feature_diff`` is the documented entry point in
    enhanced_verification that callers use to get a scope without
    invoking pytest. It must forward to scope_tests_for_diff and accept
    the same critical-path bail-out contract."""
    from bob3.enhanced_verification import pytest_scope_for_feature_diff

    here = Path(__file__).resolve()
    repo = here.parent.parent
    if not (repo / "src" / "bob3").is_dir():
        pytest.skip("Not running inside a bob3 checkout")

    # Critical-path → None (bail to full suite).
    assert pytest_scope_for_feature_diff(
        ["src/bob3/enhanced_verification.py"], repo
    ) is None

    # Leaf module → real scope.
    leaf = "src/bob3/container_runner.py"
    if not (repo / leaf).is_file():
        pytest.skip(f"{leaf} not present in this checkout")
    scope = pytest_scope_for_feature_diff([leaf], repo)
    assert scope is not None
    assert any("test_container_runner.py" in p for p in scope)


def test_capture_pytest_snapshot_accepts_changed_files_kw(tmp_path: Path) -> None:
    """Regression test for the F-R6-301 wiring in capture_pytest_snapshot.

    We don't run pytest here (that would take minutes) — we only assert
    the new ``changed_files`` keyword is accepted, that critical-path
    diffs still flow through, and that an empty/missing workspace short
    -circuits before any pytest invocation. This protects the integration
    seam from accidental signature regressions in future refactors.
    """
    from bob3.orchestrator.run_loop import capture_pytest_snapshot

    # No workspace → None, regardless of changed_files content. This
    # exercises the kwarg without spawning pytest.
    assert capture_pytest_snapshot(None, changed_files=["src/bob3/foo.py"]) is None
    assert capture_pytest_snapshot(
        "", changed_files=["src/bob3/enhanced_verification.py"]
    ) is None

    # Non-existent workspace path → None (file-system guard fires before
    # we ever call into the scoper, but signature must still accept kw).
    fake_ws = tmp_path / "no_such_workspace"
    assert capture_pytest_snapshot(
        str(fake_ws), changed_files=["src/bob3/foo.py"]
    ) is None

    # Workspace without a tests/ directory → None.
    empty_ws = tmp_path / "empty_ws"
    empty_ws.mkdir()
    assert capture_pytest_snapshot(
        str(empty_ws), changed_files=["src/bob3/foo.py"]
    ) is None


def test_capture_pytest_snapshot_scopes_real_workspace(tmp_path: Path) -> None:
    """End-to-end-ish: build a tiny fake "workspace" with one source file
    and three passing tests, then verify that calling
    ``capture_pytest_snapshot`` with ``changed_files`` produces a snapshot
    keyed by the scoped tests (not the full suite, since there is no full
    suite here). This is the only F-R6-301 test that actually invokes
    pytest, so it stays very small.
    """
    from bob3.orchestrator.run_loop import capture_pytest_snapshot

    ws = tmp_path / "workspace"
    (ws / "src" / "bob3").mkdir(parents=True)
    (ws / "tests").mkdir()
    (ws / "src" / "bob3" / "__init__.py").write_text("")
    (ws / "src" / "bob3" / "leaf.py").write_text("VALUE = 1\n")
    (ws / "src" / "bob3" / "user_a.py").write_text(
        "from bob3.leaf import VALUE\n"
    )
    (ws / "src" / "bob3" / "user_b.py").write_text(
        "import bob3.leaf\n"
    )
    (ws / "tests" / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))\n"
    )
    (ws / "tests" / "test_leaf.py").write_text(
        "from bob3.leaf import VALUE\n"
        "def test_v():\n"
        "    assert VALUE == 1\n"
    )
    (ws / "tests" / "test_user_a.py").write_text(
        "from bob3.user_a import VALUE\n"
        "def test_a():\n"
        "    assert VALUE == 1\n"
    )
    (ws / "tests" / "test_user_b.py").write_text(
        "import bob3.user_b\n"
        "def test_b():\n"
        "    assert True\n"
    )
    (ws / "tests" / "test_off_topic.py").write_text(
        "def test_off():\n"
        "    assert True\n"
    )

    snap = capture_pytest_snapshot(
        str(ws), changed_files=["src/bob3/leaf.py"]
    )
    # Snapshot succeeds and contains the scoped tests but NOT the
    # off-topic test (which the scoper should have excluded).
    assert snap is not None
    nodeids = " ".join(snap.keys())
    assert "test_leaf.py" in nodeids
    assert "test_user_a.py" in nodeids
    assert "test_user_b.py" in nodeids
    assert "test_off_topic.py" not in nodeids
    # All scoped tests should pass (the source is trivially correct).
    assert all(snap.values()), f"unexpected failures: {snap}"
