"""Orchestrator shim for ownership-evidenced regression detection.

Feature 9e8d5cac-28f6-4dfe-9f21-c2f565cd4af3

Re-exports ``detect_regression_with_evidence`` and ``validate_causal_link``
from ``bob3.regression_detector`` under the ``bob3.orchestrator`` namespace so
that orchestrator call-sites have a single, consistent import path.
"""

from __future__ import annotations

from bob3.regression_detector import (  # noqa: F401
    detect_regression_with_evidence,
    validate_causal_link,
    verify_causal_link,
)

__all__ = ["detect_regression_with_evidence", "validate_causal_link", "verify_causal_link"]
