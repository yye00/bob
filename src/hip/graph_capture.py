"""Fixture reproducing the offending ``src/hip/graph_capture.py`` module.

In the hippy build a HIP graph-capture feature created this exact file, giving
``src/hip`` a real payload and cementing the namespace collision that hid the
real ``hip-python`` package workspace-wide. It is preserved here purely as a
regression fixture for :mod:`hippy.namespace_collision`; it performs no GPU work
and bob does not depend on ``hip-python``.

Feature: 46744620-08fb-46e2-939e-978b22cf4d73.
"""
from __future__ import annotations

__all__ = ["describe_collision"]


def describe_collision() -> str:
    """Return a one-line description of why this module is a namespace hazard."""
    return (
        "src/hip/graph_capture.py shadows the real hip-python package; in a GPU "
        "project this makes `from hip import ...` fail workspace-wide."
    )
