"""Namespace-collision guard — a generated module must not shadow a real dep.

Root cause (hippy/hipsci build, invisible for many generations): one feature
created ``src/hip/__init__.py`` + ``src/hip/graph_capture.py`` to hold its code.
But the project depends on the PyPI distribution ``hip-python``, imported as
``from hip import hip, hiprtc, hipblas, ...``. With ``src/`` on ``sys.path`` the
workspace's ``src/hip/`` package SHADOWED the real ``hip`` package, so EVERY
``from hip import ...`` across the whole workspace raised ImportError. The L0
facade became unreachable and every sub-agent silently fell back to host-backed
CPU fakes — no amount of anti-cheat hardening could fix it because the real
backend was simply un-importable.

This module detects that collision: when ``src/`` contains a top-level package
or module whose name matches a real third-party dependency the project imports,
:func:`check_namespace_collisions` reports it so verification (and the root
conftest) can fail loudly with a clear message.

Boundary: the project's OWN top-level package name is allowed — a name is only a
collision when it matches an *external imported distribution*. Callers pass the
set of dependency import-names to check against; the project's own namespace
(e.g. ``hippy``) is simply not in that set.

Feature: 46744620-08fb-46e2-939e-978b22cf4d73.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

__all__ = [
    "check_namespace_collisions",
    "collision_message",
]

# Default import-names that a Python scientific/GPU project depends on and which
# must never be shadowed by a generated src/<name>. Used when a caller does not
# supply an explicit dependency set. numpy/scipy are included per the spec since
# shadowing either silently breaks array interop across the whole workspace.
DEFAULT_SHADOW_NAMES = frozenset(
    {
        "hip",
        "hiprtc",
        "hipblas",
        "hipfft",
        "hiprand",
        "hipsolver",
        "hipsparse",
        "numpy",
        "scipy",
    }
)


def check_namespace_collisions(
    src_dir,
    dependencies: Iterable[str] | None = DEFAULT_SHADOW_NAMES,
) -> list[str]:
    """Return the sorted names in *src_dir* that shadow an imported dependency.

    A collision is any top-level entry directly under *src_dir* that is importable
    as a package/module AND whose import-name matches a name in *dependencies*:

    - a directory (regular or namespace package) named ``<dep>``, or
    - a module file named ``<dep>.py``.

    Non-importable entries (e.g. ``<dep>.txt`` data files) are ignored — they do
    not participate in ``import`` resolution and therefore cannot shadow.

    Args:
        src_dir: Path (or str) to the ``src`` directory to scan. A directory that
            does not exist yields ``[]`` (a not-yet-created ``src`` is not a
            collision).
        dependencies: Iterable of dependency import-names to guard. Defaults to
            :data:`DEFAULT_SHADOW_NAMES`. An empty iterable means nothing can
            collide (returns ``[]``). The project's OWN package name should simply
            be absent from this set.

    Returns:
        A sorted list of colliding names (empty when there is no collision).

    Raises:
        ValueError: If *src_dir* is ``None`` or *dependencies* is ``None`` or not
            iterable — invalid input must not silently succeed.
    """
    if src_dir is None:
        raise ValueError("src_dir must not be None")
    if dependencies is None:
        raise ValueError("dependencies must not be None")
    try:
        dep_names = {str(d) for d in dependencies}
    except TypeError as exc:
        raise ValueError(
            f"dependencies must be an iterable of names, got {type(dependencies).__name__}"
        ) from exc

    src_path = Path(src_dir)
    if not src_path.is_dir():
        return []
    if not dep_names:
        return []

    collisions: set[str] = set()
    for child in src_path.iterdir():
        if child.is_dir():
            name = child.name
        elif child.is_file() and child.suffix == ".py":
            name = child.name[: -len(".py")]
        else:
            continue
        if name in dep_names:
            collisions.add(name)
    return sorted(collisions)


def collision_message(collisions: Iterable[str]) -> str:
    """Build the loud, actionable failure message for detected *collisions*.

    Returns an empty string when there are no collisions.
    """
    names = sorted({str(c) for c in collisions})
    if not names:
        return ""
    joined = ", ".join(names)
    return (
        f"namespace collision shadows {joined}: src/ contains module(s) whose name "
        f"matches an imported dependency, hiding the real package so "
        f"`from {names[0]} import ...` breaks workspace-wide. Move the code into the "
        f"project's own namespace (e.g. src/<project>/...)."
    )


def assert_no_namespace_collisions(
    src_dir, dependencies: Iterable[str] | None = DEFAULT_SHADOW_NAMES
) -> None:
    """Raise ``RuntimeError`` if any generated module shadows a dependency.

    Thin wrapper used at collection time (root conftest) so a collision fails the
    whole test session loudly with a clear ``namespace collision shadows <dist>``
    message.
    """
    collisions = check_namespace_collisions(src_dir, dependencies=dependencies)
    if collisions:
        raise RuntimeError(collision_message(collisions))
