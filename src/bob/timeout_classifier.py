"""Timeout classification for bob per-feature wall-clock timeout (feature 754a5020).

Classifies a timed-out feature execution as either a "charged" retry (where
actual work was persisted before the timeout) or an "exempt" retry (no
artifacts persisted — treated like the startup-crash-exempt logic so that a
legitimate infrastructure stall does not eat into the feature's retry budget).

The classification reuses the same artifact-count heuristic as the
startup-crash-exempt logic in bob.run_loop:
  - artifact_count > 0 → charged (work was done, just not finished in time)
  - artifact_count == 0 → exempt (nothing was written; transient infrastructure hang)

A TIMEOUT telemetry event is emitted for observability of chronic slow features.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

# Lifetime cap for timeout exemptions: after this many free retries the feature
# is always charged regardless of artifact state.
TIMEOUT_EXEMPT_LIFETIME_CAP: int = 10


def classify_feature_timeout(
    *,
    feature_id: str,
    elapsed_seconds: float,
    timeout_seconds: float,
    workspace: str | os.PathLike[str] | None,
    exempt_counter: int,
) -> dict:
    """Classify a timed-out feature execution for retry budget accounting.

    Decision tree
    -------------
    1. If ``exempt_counter >= TIMEOUT_EXEMPT_LIFETIME_CAP``: charge (cap reached).
    2. Count persisted artifacts in the workspace.
    3. If ``artifact_count > 0``: charge (work was started but not finished).
    4. If ``artifact_count == 0``: exempt (infrastructure hang with no progress).

    Emits a TIMEOUT telemetry WARNING log regardless of the decision.

    Parameters
    ----------
    feature_id:
        ID of the feature that timed out — included in telemetry.
    elapsed_seconds:
        Wall-clock seconds elapsed before the timeout fired.
    timeout_seconds:
        The configured timeout threshold.
    workspace:
        Workspace root directory.  May be None or non-existent.
    exempt_counter:
        Current lifetime timeout-exemption count for this feature (0-based).

    Returns
    -------
    dict with keys:
        decision: str — one of "charge", "exempt", "cap_reached"
        artifact_count: int — number of persisted files found
        exempt_counter_after: int — counter value after this decision
        elapsed_seconds: float — wall-clock seconds elapsed
        timeout_seconds: float — the configured timeout threshold
        evidence: str — human-readable explanation of the decision
    """
    if not feature_id or not feature_id.strip():
        raise ValueError("feature_id must be a non-empty string")
    if elapsed_seconds < 0:
        raise ValueError(f"elapsed_seconds must be non-negative, got {elapsed_seconds!r}")
    if timeout_seconds <= 0:
        raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds!r}")
    if exempt_counter < 0:
        raise ValueError(f"exempt_counter must be non-negative, got {exempt_counter!r}")

    logger.warning(
        "TIMEOUT feature_id=%s elapsed_seconds=%.1f timeout_seconds=%.0f",
        feature_id,
        elapsed_seconds,
        timeout_seconds,
    )

    # 1. Lifetime cap check.
    if exempt_counter >= TIMEOUT_EXEMPT_LIFETIME_CAP:
        logger.info(
            json.dumps({
                "event": "FEATURE_TIMEOUT_EXEMPT_CAPPED",
                "feature_id": feature_id,
                "exempt_counter": exempt_counter,
                "cap": TIMEOUT_EXEMPT_LIFETIME_CAP,
            })
        )
        return {
            "decision": "cap_reached",
            "artifact_count": 0,
            "exempt_counter_after": exempt_counter,
            "elapsed_seconds": elapsed_seconds,
            "timeout_seconds": timeout_seconds,
            "evidence": (
                f"lifetime_cap_reached: exempt_counter={exempt_counter} "
                f">= cap={TIMEOUT_EXEMPT_LIFETIME_CAP}; charging retry"
            ),
        }

    # 2. Count persisted artifacts.
    artifact_count = _count_workspace_artifacts(workspace)

    # 3. Artifacts present → charged retry (work was started).
    if artifact_count > 0:
        return {
            "decision": "charge",
            "artifact_count": artifact_count,
            "exempt_counter_after": exempt_counter,
            "elapsed_seconds": elapsed_seconds,
            "timeout_seconds": timeout_seconds,
            "evidence": (
                f"timeout_with_work: artifact_count={artifact_count} > 0; "
                f"elapsed={elapsed_seconds:.1f}s > timeout={timeout_seconds:.0f}s; "
                f"charging retry"
            ),
        }

    # 4. No artifacts → exempt retry (infrastructure hang).
    new_counter = exempt_counter + 1
    logger.info(
        json.dumps({
            "event": "FEATURE_TIMEOUT_EXEMPT",
            "feature_id": feature_id,
            "exempt_counter": exempt_counter,
            "exempt_counter_after": new_counter,
            "elapsed_seconds": elapsed_seconds,
        })
    )
    return {
        "decision": "exempt",
        "artifact_count": 0,
        "exempt_counter_after": new_counter,
        "elapsed_seconds": elapsed_seconds,
        "timeout_seconds": timeout_seconds,
        "evidence": (
            f"timeout_no_work: artifact_count=0; "
            f"elapsed={elapsed_seconds:.1f}s > timeout={timeout_seconds:.0f}s; "
            f"exempt_counter={exempt_counter}->{new_counter}; exempting retry"
        ),
    }


def _count_workspace_artifacts(workspace: str | os.PathLike[str] | None) -> int:
    """Count Python source/test artifacts in a workspace directory.

    Returns 0 and never raises on missing or unreadable workspace.
    Mirrors the artifact-count heuristic used by startup_crash_exempt.
    """
    if workspace is None:
        return 0
    try:
        from pathlib import Path
        root = Path(workspace)
        count = 0
        for sub in ("src", "tests"):
            sub_dir = root / sub
            if sub_dir.is_dir():
                count += sum(1 for _ in sub_dir.rglob("*.py"))
        return count
    except Exception:
        return 0


__all__ = [
    "TIMEOUT_EXEMPT_LIFETIME_CAP",
    "classify_feature_timeout",
]
