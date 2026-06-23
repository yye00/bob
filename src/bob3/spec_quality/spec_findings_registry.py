"""Persistent spec-critic findings registry with regression detection (F-9f58051a).

Keyed by (spec_hash, slot_id, defect_type). On re-run with the same defect
type at the same slot, ``detect_regression`` flags it as REGRESSION and
escalates severity by one level. Tracks ``critic_repeat_rate``; halt-gate
fires when rate > 0.30 over 3 runs.

Mirrors reviews/findings.yaml (code-review registry) but for the spec layer.

Public API::

    from bob3.spec_quality.spec_findings_registry import record, detect_regression

    record(
        spec_hash="abc123",
        slot_id="AC-0",
        defect_type="ambiguity",
        feature_id="feat-001",
        name="My feature",
        rationale="...",
        suggested_fix="...",
    )

    regressions = detect_regression(spec_hash="abc123", slot_id="AC-0",
                                    defect_type="ambiguity")
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_SPEC_FINDINGS_PATH = _WORKSPACE_ROOT / "reviews" / "spec_findings.yaml"
_METRICS_PATH = _WORKSPACE_ROOT / "reviews" / "metrics.yaml"

SEVERITY_ORDER = ["info", "warning", "error", "critical"]

_HALT_GATE_THRESHOLD = 0.30
_HALT_GATE_WINDOW = 3  # runs

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _findings_path(path: Path | None) -> Path:
    return Path(path) if path is not None else _SPEC_FINDINGS_PATH


def _metrics_path(path: Path | None) -> Path:
    return Path(path) if path is not None else _METRICS_PATH


def _load_yaml(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh)
        except yaml.YAMLError:
            from bob3.spec_findings_writer import quarantine_corrupt_findings

            logger.error(
                "spec_findings_corrupt: YAMLError at %s — quarantining and continuing",
                p,
                exc_info=True,
            )
            quarantine_corrupt_findings(p)
            return {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_yaml(data: dict[str, Any], p: Path) -> None:
    from bob3.spec_findings_writer import write_atomic_yaml

    write_atomic_yaml(data, p)


def _escalate_severity(severity: str) -> str:
    """Return the next-higher severity level, capped at 'critical'."""
    try:
        idx = SEVERITY_ORDER.index(severity)
    except ValueError:
        idx = 0
    return SEVERITY_ORDER[min(idx + 1, len(SEVERITY_ORDER) - 1)]


def _validate_str_arg(value: Any, name: str) -> None:
    if value is None:
        raise TypeError(f"{name} must be a string, got None")
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")


def _entry_key(spec_hash: str, slot_id: str, defect_type: str) -> str:
    return f"{spec_hash}:{slot_id}:{defect_type}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record(
    spec_hash: str,
    slot_id: str,
    defect_type: str,
    *,
    feature_id: str = "",
    name: str = "",
    rationale: str = "",
    suggested_fix: str = "",
    severity: str = "warning",
    run_id: str | None = None,
    findings_path: Path | None = None,
    metrics_path: Path | None = None,
) -> dict[str, Any]:
    """Record a spec-critic finding in the persistent registry.

    Parameters
    ----------
    spec_hash:
        Hash of the spec that produced this defect (from spec_critic._spec_hash).
    slot_id:
        Identifier for the acceptance-criterion slot, e.g. ``"AC-0"`` or
        ``f"AC-{ac_index}"``. Use ``"FEATURE"`` for feature-level defects.
    defect_type:
        One of the canonical defect types (ambiguity, missing_edge_case, …).
    feature_id, name, rationale, suggested_fix:
        Metadata stored with the finding.
    severity:
        Initial severity level (info | warning | error | critical).
        Escalated automatically on regression.
    run_id:
        Opaque identifier for the current run (defaults to ISO timestamp).
    findings_path, metrics_path:
        Override output paths; mainly for testing.

    Returns
    -------
    dict
        The stored finding entry, including ``is_regression`` and
        ``escalated_severity`` fields.
    """
    _validate_str_arg(spec_hash, "spec_hash")
    _validate_str_arg(slot_id, "slot_id")
    _validate_str_arg(defect_type, "defect_type")
    if severity not in SEVERITY_ORDER:
        raise ValueError(
            f"severity must be one of {SEVERITY_ORDER!r}, got {severity!r}"
        )

    fp = _findings_path(findings_path)
    mp = _metrics_path(metrics_path)

    data = _load_yaml(fp)
    if "schema_version" not in data:
        data["schema_version"] = 2
    if "findings" not in data:
        data["findings"] = {}
    if "run_history" not in data:
        data["run_history"] = []

    key = _entry_key(spec_hash, slot_id, defect_type)
    now_run_id = run_id or datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    existing = data["findings"].get(key)
    is_regression = existing is not None
    if is_regression:
        escalated = _escalate_severity(existing.get("severity", severity))
        occurrence = existing.get("occurrence_count", 1) + 1
    else:
        escalated = severity
        occurrence = 1

    entry: dict[str, Any] = {
        "spec_hash": spec_hash,
        "slot_id": slot_id,
        "defect_type": defect_type,
        "feature_id": feature_id,
        "feature_name": name,
        "rationale": rationale,
        "suggested_fix": suggested_fix,
        "severity": escalated,
        "first_seen": existing.get("first_seen", today) if existing else today,
        "last_seen": today,
        "occurrence_count": occurrence,
        "is_regression": is_regression,
        "run_id": now_run_id,
    }

    data["findings"][key] = entry

    # Track per-run stats for critic_repeat_rate
    data["run_history"].append(
        {
            "run_id": now_run_id,
            "date": today,
            "key": key,
            "is_regression": is_regression,
        }
    )

    _save_yaml(data, fp)
    _update_metrics(data, mp)

    logger.debug(
        "spec-findings-registry: recorded %s@%s type=%s regression=%s severity=%s",
        spec_hash[:8],
        slot_id,
        defect_type,
        is_regression,
        escalated,
    )
    return entry


def detect_regression(
    spec_hash: str,
    slot_id: str,
    defect_type: str,
    *,
    findings_path: Path | None = None,
) -> bool:
    """Return True if (spec_hash, slot_id, defect_type) has been seen before.

    Parameters
    ----------
    spec_hash, slot_id, defect_type:
        Composite key identifying the finding.
    findings_path:
        Override path; mainly for testing.
    """
    _validate_str_arg(spec_hash, "spec_hash")
    _validate_str_arg(slot_id, "slot_id")
    _validate_str_arg(defect_type, "defect_type")
    fp = _findings_path(findings_path)
    data = _load_yaml(fp)
    key = _entry_key(spec_hash, slot_id, defect_type)
    existing = data.get("findings", {}).get(key)
    if existing is None:
        return False
    return existing.get("occurrence_count", 1) > 1


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _compute_critic_repeat_rate(data: dict[str, Any], window: int = _HALT_GATE_WINDOW) -> float:
    """Compute critic_repeat_rate over the last *window* distinct run_ids."""
    run_history = data.get("run_history", [])
    if not run_history:
        return 0.0

    # Collect the last N distinct run_ids in order
    seen_runs: list[str] = []
    for record_entry in reversed(run_history):
        rid = record_entry.get("run_id", "")
        if rid not in seen_runs:
            seen_runs.insert(0, rid)
        if len(seen_runs) >= window:
            break

    if not seen_runs:
        return 0.0

    # Count regression events within the window
    window_entries = [e for e in run_history if e.get("run_id") in seen_runs]
    if not window_entries:
        return 0.0

    regression_count = sum(1 for e in window_entries if e.get("is_regression", False))
    return regression_count / len(window_entries)


def _update_metrics(data: dict[str, Any], metrics_path: Path) -> dict[str, Any]:
    """Update metrics.yaml with the current critic_repeat_rate and halt status."""
    rate = _compute_critic_repeat_rate(data)
    halt = rate > _HALT_GATE_THRESHOLD

    metrics_data = _load_yaml(metrics_path)
    metrics_data["critic_repeat_rate"] = round(rate, 4)
    metrics_data["critic_repeat_rate_window"] = _HALT_GATE_WINDOW
    metrics_data["critic_repeat_rate_threshold"] = _HALT_GATE_THRESHOLD
    metrics_data["halt_gate_fired"] = halt
    metrics_data["last_updated"] = date.today().isoformat()

    _save_yaml(metrics_data, metrics_path)

    if halt:
        logger.warning(
            "spec-findings-registry: HALT GATE FIRED — critic_repeat_rate=%.3f > %.2f "
            "(the spec extractor is likely broken)",
            rate,
            _HALT_GATE_THRESHOLD,
        )

    return metrics_data


def compute_critic_repeat_rate(
    *,
    findings_path: Path | None = None,
    window: int = _HALT_GATE_WINDOW,
) -> float:
    """Return the current critic_repeat_rate from the findings registry.

    Parameters
    ----------
    findings_path:
        Override path; mainly for testing.
    window:
        Number of distinct run_ids to consider.
    """
    fp = _findings_path(findings_path)
    data = _load_yaml(fp)
    return _compute_critic_repeat_rate(data, window=window)


def is_halt_gate_fired(
    *,
    findings_path: Path | None = None,
    metrics_path: Path | None = None,
) -> bool:
    """Return True if critic_repeat_rate > threshold over the last 3 runs.

    Reads from metrics.yaml if available; recomputes from findings otherwise.
    """
    mp = _metrics_path(metrics_path)
    if mp.exists():
        metrics_data = _load_yaml(mp)
        return bool(metrics_data.get("halt_gate_fired", False))
    # Fall back to computing from findings
    rate = compute_critic_repeat_rate(findings_path=findings_path)
    return rate > _HALT_GATE_THRESHOLD


# ---------------------------------------------------------------------------
# Diff / CLI helpers
# ---------------------------------------------------------------------------


def diff_findings_since(
    since_ref: str,
    *,
    findings_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return findings that first appeared or were last seen since *since_ref*.

    Parameters
    ----------
    since_ref:
        A run_id string, ISO date string (YYYY-MM-DD), or git-ref.
        Findings whose ``first_seen >= since_ref`` are returned.
    findings_path:
        Override path; mainly for testing.

    Returns
    -------
    list[dict]
        Filtered list of findings (full entry dicts), sorted by last_seen desc.
    """
    fp = _findings_path(findings_path)
    data = _load_yaml(fp)
    findings = data.get("findings", {})

    results = []
    for key, entry in findings.items():
        first_seen = entry.get("first_seen", "")
        last_seen = entry.get("last_seen", "")
        # Compare as strings — ISO dates sort correctly lexicographically
        if first_seen >= since_ref or last_seen >= since_ref:
            results.append(dict(entry, _key=key))

    results.sort(key=lambda e: e.get("last_seen", ""), reverse=True)
    return results


# ---------------------------------------------------------------------------
# Public aliases required by acceptance criteria
# ---------------------------------------------------------------------------

def escalate_severity(severity: str) -> str:
    """Return the next-higher severity level (public alias for _escalate_severity)."""
    return _escalate_severity(severity)


def diff_since_ref(
    since_ref: str,
    *,
    findings_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return findings first/last seen >= since_ref (alias for diff_findings_since)."""
    return diff_findings_since(since_ref, findings_path=findings_path)


def halt_gate_fires(
    *,
    findings_path: Path | None = None,
    metrics_path: Path | None = None,
) -> bool:
    """Return True iff critic_repeat_rate > 0.30 over last 3 runs."""
    return is_halt_gate_fired(findings_path=findings_path, metrics_path=metrics_path)


def handle_empty_registry(
    *,
    findings_path: Path | None = None,
) -> float:
    """Return repeat_rate=0.0 when registry is empty; safe to call on missing file."""
    fp = _findings_path(findings_path)
    data = _load_yaml(fp)
    findings = data.get("findings", {})
    run_history = data.get("run_history", [])
    if not findings and not run_history:
        return 0.0
    return _compute_critic_repeat_rate(data)
