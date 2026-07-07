"""Root conftest — collection-time namespace-collision guard.

integration: conftest — asserts at pytest collection time that no generated
module under ``src/`` shadows a real third-party dependency this project
imports. A ``src/<dep>`` package silently hides the real distribution so
``from <dep> import ...`` breaks workspace-wide (the deepest hippy-build
defect). Failing loudly here means the collision can never silently poison a
run again.

The guard checks only against THIS project's actual imported distributions
(see :data:`_BOB_DEPENDENCY_IMPORT_NAMES`). bob does NOT depend on
``hip-python``, so the regression fixture ``src/hip/`` (kept for
:mod:`hippy.namespace_collision` tests) is correctly NOT flagged here.

Feature: 46744620-08fb-46e2-939e-978b22cf4d73.
"""
from __future__ import annotations

import pathlib

from hippy.namespace_collision import assert_no_namespace_collisions

# Import-names of the third-party distributions bob actually depends on. A
# generated src/<name> matching any of these would shadow the real package.
# NOTE: ``hip`` is intentionally absent — bob has no hip-python dependency, so
# the src/hip regression fixture is not a real collision in this workspace.
_BOB_DEPENDENCY_IMPORT_NAMES = frozenset(
    {
        "click",
        "rich",
        "pydantic",
        "fitz",  # PyMuPDF
        "yaml",  # PyYAML
        "mem0",  # mem0ai
        "mcp",
        "fastembed",
        "bandit",
        "icontract",
        "pytest",
    }
)


def pytest_configure(config) -> None:
    """Fail collection loudly if src/ shadows a real bob dependency."""
    src = pathlib.Path(__file__).parent / "src"
    assert_no_namespace_collisions(
        src, dependencies=_BOB_DEPENDENCY_IMPORT_NAMES
    )
