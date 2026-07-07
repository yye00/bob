"""tests_pass MUST be scoped to the feature's own tests, never the whole tree.

Verifies that ``scope_pytest_to_feature`` resolves a feature's own test paths
(its ``pytest:`` ACs plus ``tests/<feature_id>/``) and NEVER returns the bare
``tests/`` tree or a sibling feature subtree — so a sibling's collection error
cannot fail this feature's tests_pass step.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from bob.verification.per_feature_test_scope import (
    SiblingTestCollectionError,
    build_scoped_pytest_argv,
    collect_feature_test_paths,
    scope_pytest_to_feature,
)

FEATURE_ID = "5a2360d6-1d50-45bd-acf5-2e6090937b7c"
SIBLING_ID = "deadbeef-1111-2222-3333-444455556666"


def test_pytest_ac_path_is_scoped(tmp_path: Path) -> None:
    acs = ["pytest: tests/test_myfeature.py", "File exists: src/bob/x.py"]
    scoped = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert scoped == ["tests/test_myfeature.py"]


def test_node_id_suffix_stripped(tmp_path: Path) -> None:
    acs = ["pytest: tests/test_myfeature.py::TestX::test_ok"]
    scoped = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert scoped == ["tests/test_myfeature.py"]


def test_feature_subtree_included_when_present(tmp_path: Path) -> None:
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    (feature_dir / "test_a.py").write_text("def test_ok():\n    assert True\n")
    scoped = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert f"tests/{FEATURE_ID}" in scoped


def test_never_returns_bare_tests_tree(tmp_path: Path) -> None:
    acs = ["pytest: tests/test_myfeature.py"]
    scoped = scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)
    assert "tests" not in scoped
    assert "tests/" not in scoped


def test_sibling_pytest_ac_is_rejected(tmp_path: Path) -> None:
    """A pytest: AC pointing at a sibling subtree must raise, not contaminate."""
    acs = [f"pytest: tests/{SIBLING_ID}/test_fail.py"]
    with pytest.raises(SiblingTestCollectionError):
        scope_pytest_to_feature(FEATURE_ID, acs, tmp_path)


def test_collect_feature_test_paths_returns_set(tmp_path: Path) -> None:
    acs = ["pytest: tests/test_myfeature.py"]
    paths = collect_feature_test_paths(FEATURE_ID, acs, tmp_path)
    assert isinstance(paths, set)
    assert "tests/test_myfeature.py" in paths


def test_build_scoped_argv_uses_only_feature_paths(tmp_path: Path) -> None:
    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    (feature_dir / "test_a.py").write_text("def test_ok():\n    assert True\n")
    argv = build_scoped_pytest_argv(FEATURE_ID, [], tmp_path)
    assert any(FEATURE_ID in tok for tok in argv)
    assert "tests" not in argv


def test_scoped_run_ignores_sibling_collection_errors(tmp_path: Path) -> None:
    """End-to-end: a broken sibling stub does not fail this feature's scoped run."""
    import subprocess
    import sys

    feature_dir = tmp_path / "tests" / FEATURE_ID
    feature_dir.mkdir(parents=True)
    (feature_dir / "test_green.py").write_text(
        textwrap.dedent(
            """\
            def test_passes():
                assert 1 + 1 == 2
            """
        )
    )
    sibling_dir = tmp_path / "tests" / SIBLING_ID
    sibling_dir.mkdir(parents=True)
    (sibling_dir / "test_broken.py").write_text(
        "import a_module_that_does_not_exist_anywhere  # noqa\n"
    )

    scoped = scope_pytest_to_feature(FEATURE_ID, [], tmp_path)
    assert scoped == [f"tests/{FEATURE_ID}"]

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *scoped, "-p", "no:cacheprovider"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
