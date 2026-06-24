"""BF-5 — Resurrection gate (Tier-1 partial-work detector).

Before bob3 dispatches a fresh implementer for a "new" feature, this module
checks whether someone already started the work and abandoned it.

Three Tier-1 signals are checked (Signal A always; B/C only when
include_deep_signals=True):
  Signal A -- Stale PR/branch (GitHub graveyard)
  Signal B -- Export-without-impl (AST: symbol exported but body is pass/stub)
  Signal C -- Disk-scoped TODO clusters (>=3 TODO/FIXME refs in touch-set)

If any signal fires, the feature should be demoted to needs_human with
reason='partial_work_detected' and a resurrection_report.md written.
"""

from __future__ import annotations

from typing import Any, Optional

from bob3.brownfield.resurrection import (
    ResurrectionSignal,
    detect_resurrection_signals,
    filter_signals_by_feature_flags,
    write_resurrection_report,
)


def bf_5_resurrection_gate_tier_1_partial_work_detector(
    workspace_root: str = ".",
    touches: Optional[list[str]] = None,
    feature_keywords: Optional[list[str]] = None,
    feature_id: str = "",
    repo: str = "",
    github_token: Optional[str] = None,
    pr_lookback_days: int = 90,
    branch_diverge_days: int = 30,
    todo_cluster_min_size: int = 3,
    include_deep_signals: bool = False,
    bob3_root: str = ".bob3",
) -> dict[str, Any]:
    """Run Tier-1 resurrection signals and return a structured gate result.

    Before dispatching a fresh implementer for a "new" feature, call this to
    check for abandoned partial work.  Three signals are evaluated:

      Signal A -- Stale draft PRs or diverged branches (always evaluated).
      Signal B -- Exported symbols whose body is pass/stub (deep scan only).
      Signal C -- TODO/FIXME clusters in the touch-set (deep scan only).

    Boundary conditions:
      - Empty / None touches → returns empty result dict (no crash).
      - Invalid touches (not None and not list) → raises ValueError.
      - Invalid feature_keywords (not None and not list) → raises ValueError.

    Args:
        workspace_root:       Root directory of the brownfield workspace.
        touches:              Relative file paths the feature is expected to touch.
                              None or [] means no signals possible.
        feature_keywords:     Keywords from feature.capability for PR/branch matching.
                              None is treated as empty list.
        feature_id:           Unique feature identifier (used for report path).
        repo:                 GitHub repo slug, e.g. 'owner/repo', for Signal A PR scan.
        github_token:         Optional GitHub token for authenticated API access.
        pr_lookback_days:     Signal A -- how old a draft PR must be to fire.
        branch_diverge_days:  Signal A -- minimum branch divergence age.
        todo_cluster_min_size:Signal C -- minimum TODO count to constitute a cluster.
        include_deep_signals: When True, run Signal B and Signal C in addition to A.
        bob3_root:            Root of the .bob3 directory for report output.

    Returns:
        Dict with keys:
          signals_fired: list[dict]  -- each fired signal as a serialised dict
          should_demote: bool        -- True if any signal fired
          report_path:   str | None  -- path to resurrection_report.md (None if no signals)

    Raises:
        ValueError: If touches or feature_keywords is provided but not a list.
    """
    # Validate inputs
    if touches is not None and not isinstance(touches, list):
        raise ValueError(
            f"touches must be a list or None, got {type(touches).__name__!r}"
        )
    if feature_keywords is not None and not isinstance(feature_keywords, list):
        raise ValueError(
            f"feature_keywords must be a list or None, got {type(feature_keywords).__name__!r}"
        )

    # Normalise
    effective_touches: list[str] = touches or []
    effective_keywords: list[str] = feature_keywords or []

    # No touches → no signals possible
    if not effective_touches:
        return {
            "signals_fired": [],
            "should_demote": False,
            "report_path": None,
        }

    raw_signals: list[ResurrectionSignal] = detect_resurrection_signals(
        workspace_root=workspace_root,
        touches=effective_touches,
        feature_keywords=effective_keywords,
        repo=repo,
        github_token=github_token,
        pr_lookback_days=pr_lookback_days,
        branch_diverge_days=branch_diverge_days,
        todo_cluster_min_size=todo_cluster_min_size,
    )

    # Apply deep-scan gate: filter B/C unless explicitly requested
    signals = filter_signals_by_feature_flags(
        raw_signals,
        deep_resurrection_scan=include_deep_signals,
    )

    should_demote = len(signals) > 0
    report_path: Optional[str] = None

    if should_demote and feature_id:
        report_path = write_resurrection_report(
            feature_id=feature_id,
            signals=signals,
            bob3_root=bob3_root,
        )

    signals_serialised = [
        {
            "signal_kind": s.signal_kind,
            "evidence": s.evidence,
            "staleness_days": s.staleness_days,
            "recommended_action": s.recommended_action,
        }
        for s in signals
    ]

    return {
        "signals_fired": signals_serialised,
        "should_demote": should_demote,
        "report_path": report_path,
    }
