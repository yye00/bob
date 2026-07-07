"""Project-skeleton creation.

The project skeleton MUST make ``tests/`` an importable package so that
shared audit/registry helper modules under ``tests/`` can be imported as
``from tests.<mod> import ...``. When ``tests/__init__.py`` is missing,
pytest cannot resolve ``tests`` as a package and every importing test
fails collection with ``ModuleNotFoundError: No module named 'tests'``
(exit=2), masquerading as an acceptance-criteria failure.

:func:`create_project_skeleton` ensures the (empty) ``tests/__init__.py``
(and, for a package-style ``src/`` layout, ``src/__init__.py``) exist so
cross-test imports collect.

Behaviour: WHEN a test does ``from tests.X import Y`` THEN collection
succeeds because ``tests/`` is a package.
"""

from __future__ import annotations

from pathlib import Path

from bob.skeleton_tests_package import (
    SkeletonResult,
    ensure_tests_package,
)

__all__ = ["SkeletonResult", "ensure_tests_package", "create_project_skeleton"]


def create_project_skeleton(
    project_root: str | Path,
    *,
    create_tests_dir: bool = True,
    include_src: bool = True,
) -> SkeletonResult:
    """Create the project skeleton, ensuring ``tests/`` is a package.

    Ensures the ``tests/`` directory exists (when ``create_tests_dir`` is
    true) and that it holds an empty ``__init__.py`` so ``tests`` resolves
    as an importable package. When ``include_src`` is true and a
    package-style ``src/`` layout is present, ``src/__init__.py`` is created
    too.

    Idempotent: existing marker files are reported under
    :attr:`SkeletonResult.existing` and are not rewritten.

    :param project_root: root directory of the project.
    :param create_tests_dir: create ``tests/`` if it does not yet exist.
    :param include_src: also mark a package-style ``src/`` as a package.
    :returns: a :class:`SkeletonResult` describing created/existing markers.
    :raises ValueError: if ``project_root`` is None, empty, not a str/Path,
        does not exist, or is not a directory.
    """
    root = _validate_root(project_root)

    if create_tests_dir:
        (root / "tests").mkdir(exist_ok=True)

    return ensure_tests_package(root, include_src=include_src)


def _validate_root(project_root: str | Path) -> Path:
    """Validate ``project_root`` and return it as a ``Path``.

    Mirrors the validation in :mod:`bob.skeleton_tests_package` so that
    ``create_project_skeleton`` fails loudly on bogus input rather than
    silently succeeding.
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
