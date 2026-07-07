"""Boundary/edge-case tests for ensure_tests_package.

Verifies that empty, zero, or minimum inputs return well-defined results
rather than raising exceptions (boundary case AC).
"""

from __future__ import annotations

from bob.skeleton_tests_package import SkeletonResult, ensure_tests_package


def test_root_with_no_tests_dir_returns_empty_result(tmp_path):
    """A project root without a tests/ dir returns a result creating nothing."""
    result = ensure_tests_package(tmp_path)
    assert isinstance(result, SkeletonResult)
    assert result.created == []
    assert result.existing == []
    assert result.tests_package_ok is False


def test_empty_tests_dir_creates_only_init(tmp_path):
    """An empty tests/ dir yields exactly one created marker file."""
    (tmp_path / "tests").mkdir()
    result = ensure_tests_package(tmp_path)
    assert result.created == ["tests/__init__.py"]
    assert result.existing == []


def test_include_src_false_skips_src(tmp_path):
    """With include_src=False, src/ is never touched even if package-style."""
    (tmp_path / "tests").mkdir()
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    result = ensure_tests_package(tmp_path, include_src=False)
    assert "src/__init__.py" not in result.created
    assert not (tmp_path / "src" / "__init__.py").exists()


def test_src_dir_without_packages_not_marked(tmp_path):
    """A src/ dir with only loose files (no sub-packages) is not marked."""
    (tmp_path / "tests").mkdir()
    src = tmp_path / "src"
    src.mkdir()
    (src / "loose.py").write_text("x = 1\n", encoding="utf-8")
    result = ensure_tests_package(tmp_path)
    assert "src/__init__.py" not in result.created
    assert not (src / "__init__.py").exists()


def test_default_skeleton_result_is_empty():
    """A default-constructed SkeletonResult is well-defined and empty."""
    result = SkeletonResult()
    assert result.created == []
    assert result.existing == []
    assert result.tests_package_ok is False


def test_pathlib_path_root_accepted(tmp_path):
    """A pathlib.Path project_root (minimum valid input) is accepted."""
    (tmp_path / "tests").mkdir()
    result = ensure_tests_package(tmp_path)
    assert result.tests_package_ok is True


def test_existing_init_reported_as_existing(tmp_path):
    """A pre-existing tests/__init__.py is reported as existing, not created."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    result = ensure_tests_package(tmp_path)
    assert result.created == []
    assert result.existing == ["tests/__init__.py"]
    assert result.tests_package_ok is True
