"""Orchestrator-level regression detection entry point.

Delegates to bob.db.detect_regression while keeping the
bob.orchestrator.detect_regression namespace importable (required by
integration AC aaa5a7f7).
"""

from __future__ import annotations

from bob.db.detect_regression import detect_regression  # re-export

__all__ = ["detect_regression"]
