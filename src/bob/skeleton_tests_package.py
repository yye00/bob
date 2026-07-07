"""Ensure the project skeleton makes ``tests/`` an importable package.

Shared audit/registry helper modules live under ``tests/`` and are imported
by other tests as ``from tests.<mod> import ...``. For pytest to resolve
``tests`` as a package, ``tests/__init__.py`` must exist. When it is missing,
every importing test fails collection with
``ModuleNotFoundError: No module named 'tests'`` (exit=2), which masquerades
as an acceptance-criteria failure rather than a skeleton gap.

This module provides :func:`ensure_tests_package`, which the project-skeleton
feature uses to create the (empty) ``tests/__init__.py`` (and, for a
package-style layout, the ``src`` package ``__init__``) idempotently.

Behaviour: WHEN a test does ``from tests.X import Y`` THEN collection
succeeds because ``tests/`` is a package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkeletonResult:
    """Outcome of ensuring test/source packages exist.

    ``created`` lists the ``__init__.py`` paths that this call created;
    ``existing`` lists those that were already present. Both are relative
    to the project root and use forward slashes.
    """

    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)

    @property
    def tests_package_ok(self) -> bool:
        """True when ``tests/__init__.py`` exists after this call."""
        return "tests/__init__.py" in self.created or "tests/__init__.py" in self.existing


def _coerce_root(project_root: str | Path) -> Path:
    """Validate and normalise a project-root argument.

    Raises ValueError for None, empty, non-path-like, or non-directory
    inputs so callers cannot silently operate on a bogus location.
    """
    if project_root is None:
        raise ValueError("project_root must not be None")
    if isinstance(project_root, Path):
        root = project_root
    elif isinstance(project_root, str):
        if project_root.strip() == "":
            raise ValueError("project_root must not be an empty string")
        root = Path(project_root)
    else:
        raise ValueError(
            f"project_root must be a str or Path, got {type(project_root).__name__}"
        )
    if not root.exists():
        raise ValueError(f"project_root does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"project_root is not a directory: {root}")
    return root


def ensure_tests_package(
    project_root: str | Path,
    *,
    include_src: bool = True,
) -> SkeletonResult:
    """Ensure ``tests/`` (and optionally ``src``) are importable packages.

    Creates an empty ``tests/__init__.py`` under ``project_root`` if the
    ``tests/`` directory exists but lacks an ``__init__.py``. When
    ``include_src`` is true and a package-style ``src/`` layout is present
    (``src/`` contains at least one sub-package directory), ensures
    ``src/__init__.py`` too.

    Idempotent: calling it when the files already exist creates nothing and
    reports them under ``existing``.

    :raises ValueError: if ``project_root`` is None, empty, not a str/Path,
        does not exist, or is not a directory.
    """
    root = _coerce_root(project_root)
    result = SkeletonResult()

    tests_dir = root / "tests"
    if tests_dir.is_dir():
        _ensure_init(tests_dir / "__init__.py", "tests/__init__.py", result)

    if include_src:
        src_dir = root / "src"
        if src_dir.is_dir() and _is_package_style_src(src_dir):
            _ensure_init(src_dir / "__init__.py", "src/__init__.py", result)

    return result


def _ensure_init(init_path: Path, rel: str, result: SkeletonResult) -> None:
    if init_path.exists():
        result.existing.append(rel)
        return
    init_path.write_text("", encoding="utf-8")
    result.created.append(rel)


def _is_package_style_src(src_dir: Path) -> bool:
    """True when ``src/`` holds package directories (each with __init__.py)."""
    for child in src_dir.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            return True
    return False
