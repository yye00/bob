"""Fixture package reproducing the historical hippy namespace collision.

This ``src/hip`` package is the exact shape that silently broke the hippy build:
a generated ``src/hip/`` shadows the real ``hip-python`` distribution when the
target project imports ``from hip import ...``. It exists here ONLY as a
regression fixture for :mod:`hippy.namespace_collision` — bob itself does not
depend on ``hip-python``, so this package is inert in this workspace.

The guard in :func:`hippy.namespace_collision.check_namespace_collisions` is
what detects (and fails) this pattern in a real GPU project. See feature
46744620-08fb-46e2-939e-978b22cf4d73.
"""
from __future__ import annotations

__all__ = ["SHADOWS_REAL_DEPENDENCY"]

# Marker documenting that this package name collides with the real ``hip``
# distribution in a GPU project (harmless in bob, which has no such dependency).
SHADOWS_REAL_DEPENDENCY = "hip-python"
