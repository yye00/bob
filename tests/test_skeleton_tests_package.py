"""Tests that the project skeleton makes ``tests/`` an importable package.

Covers :func:`bob.skeleton.create_project_skeleton` and the underlying
:func:`bob.skeleton_tests_package.ensure_tests_package`, proving that a
missing ``tests/__init__.py`` is created so ``from tests.X import Y``
resolves at collection time.
"""

from __future__ import annotations

import pytest

from bob.skeleton import SkeletonResult, create_project_skeleton
from bob.skeleton_tests_package import ensure_tests_package


def test_create_project_skeleton_creates_tests_init(tmp_path):
    """create_project_skeleton makes tests/ a package with an __init__.py."""
    result = create_project_skeleton(tmp_path)
    init_path = tmp_path / "tests" / "__init__.py"
    assert init_path.exists()
    assert init_path.read_text(encoding="utf-8") == ""
    assert result.tests_package_ok is True
    assert "tests/__init__.py" in result.created


def test_create_project_skeleton_makes_tests_importable(tmp_path):
    """After skeleton creation, ``from tests.<mod> import ...`` collects.

    Runs in a fresh interpreter rooted at ``tmp_path`` so the import
    resolves against the created ``tests`` package rather than this
    project's own ``tests`` package already in ``sys.modules``.
    """
    import subprocess
    import sys

    create_project_skeleton(tmp_path)
    (tmp_path / "tests" / "shared_helper.py").write_text(
        "VALUE = 42\n", encoding="utf-8"
    )

    proc = subprocess.run(
        [sys.executable, "-c", "from tests.shared_helper import VALUE; print(VALUE)"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "42"


def test_create_project_skeleton_is_idempotent(tmp_path):
    """Calling twice creates nothing the second time."""
    create_project_skeleton(tmp_path)
    second = create_project_skeleton(tmp_path)
    assert second.created == []
    assert "tests/__init__.py" in second.existing
    assert second.tests_package_ok is True


def test_create_project_skeleton_creates_tests_dir_when_absent(tmp_path):
    """A project root without a tests/ dir gets one created by default."""
    assert not (tmp_path / "tests").exists()
    result = create_project_skeleton(tmp_path)
    assert (tmp_path / "tests").is_dir()
    assert result.tests_package_ok is True


def test_create_tests_dir_false_leaves_missing_dir(tmp_path):
    """With create_tests_dir=False, an absent tests/ is not created."""
    result = create_project_skeleton(tmp_path, create_tests_dir=False)
    assert not (tmp_path / "tests").exists()
    assert result.tests_package_ok is False
    assert result.created == []


def test_create_project_skeleton_marks_package_style_src(tmp_path):
    """A package-style src/ layout gets an src/__init__.py."""
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    result = create_project_skeleton(tmp_path)
    assert (tmp_path / "src" / "__init__.py").exists()
    assert "src/__init__.py" in result.created


def test_create_project_skeleton_invalid_root_raises():
    """Invalid project_root raises ValueError, not a silent success."""
    with pytest.raises(ValueError):
        create_project_skeleton(None)


def test_returns_skeleton_result(tmp_path):
    """The return value is a SkeletonResult instance."""
    result = create_project_skeleton(tmp_path)
    assert isinstance(result, SkeletonResult)


def test_ensure_tests_package_alias_available(tmp_path):
    """ensure_tests_package is re-exported and works via bob.skeleton path."""
    (tmp_path / "tests").mkdir()
    result = ensure_tests_package(tmp_path)
    assert result.tests_package_ok is True
