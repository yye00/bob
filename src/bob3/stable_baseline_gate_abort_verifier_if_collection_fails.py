"""Stable baseline gate — abort verifier if collection fails.

When baseline pytest crashes at collection (e.g. ImportError in a test file),
the "before" snapshot is invalid.  Any "after" diff computed against that
snapshot fabricates regressions that do not exist.

This module provides :func:`stable_baseline_gate_abort_verifier_if_collection_fails`
as the single public entry-point.  It delegates to
:mod:`bob3.verifier.baseline_capture` and returns a plain dict result so
callers can branch on ``result["status"]`` without importing internal types.

Usage::

    from bob3.stable_baseline_gate_abort_verifier_if_collection_fails import (
        stable_baseline_gate_abort_verifier_if_collection_fails,
    )

    result = stable_baseline_gate_abort_verifier_if_collection_fails(
        workspace="/path/to/workspace",
        test_dir="tests",
    )
    if result["aborted"]:
        raise RuntimeError(
            f"Baseline unstable — collection failed in {result['failing_file']}"
        )
    snapshot = result["snapshot"]
"""

from __future__ import annotations

import pathlib
from typing import Any

from bob3.verifier.baseline_capture import collect_and_capture


def stable_baseline_gate_abort_verifier_if_collection_fails(
    workspace: str | pathlib.Path | None,
    *,
    test_dir: str = "tests",
    changed_files: list[str] | None = None,
    collect_timeout: int = 120,
) -> dict[str, Any]:
    """Run the stable baseline collection gate and return a result dict.

    Delegates to :func:`bob3.verifier.baseline_capture.collect_and_capture`.
    The verifier MUST NOT use ``snapshot`` for regression comparison when
    ``aborted`` is True — the baseline is invalid.

    Returns a dict with keys:
      ``status``       — ``"ok"`` or ``"baseline_unstable"``
      ``aborted``      — True when collection failed and the baseline was rejected
      ``snapshot``     — per-test pass/fail mapping, or None when aborted
      ``failing_file`` — first test file that caused a collection error, or None
    """
    result = collect_and_capture(
        workspace,
        test_dir=test_dir,
        changed_files=changed_files,
        collect_timeout=collect_timeout,
    )
    aborted = result.status == "baseline_unstable"
    return {
        "status": result.status,
        "aborted": aborted,
        "snapshot": result.snapshot,
        "failing_file": result.failing_collection_file,
    }
