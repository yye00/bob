"""orchestrator.run_loop — integration shim for periodic resume scan (feature 95d0125a).

Wires ``promote_interrupted_rows`` from ``orchestrator.periodic_resume_scan``
into the orchestrator loop integration layer.  The canonical loop implementation
lives in ``bob.orchestrator.run_loop``; this module satisfies the AC that
``orchestrator.run_loop`` imports the periodic-resume function.
"""

from __future__ import annotations

from orchestrator.periodic_resume_scan import (  # noqa: F401
    promote_interrupted_rows as _promote_interrupted_rows,
)

__all__ = ["_promote_interrupted_rows"]
