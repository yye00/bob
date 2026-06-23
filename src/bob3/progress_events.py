"""Structured JSONL progress event stream for bob3 orchestration."""
import json
from datetime import datetime, timezone
from pathlib import Path

from bob3.ablation import get_ablation_mode, get_telemetry_label

_DEFAULT_PROGRESS_PATH = Path(".bob3") / "progress.jsonl"


def get_progress_path() -> Path:
    """Return the path to the JSONL progress event log."""
    return _DEFAULT_PROGRESS_PATH


def emit_event(
    event_type: str,
    payload: dict,
    project_id: str,
    feature_id: str,
    attempt_number: int,
) -> None:
    """Write one JSON event record per call, appending to .bob3/progress.jsonl.

    Event types: feature_started, feature_completed, verification_started,
    verification_check_finished, evaluator_verdict, security_finding,
    cost_checkpoint, error.
    """
    path = get_progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event_type": event_type,
        "project_id": project_id,
        "feature_id": feature_id,
        "attempt_number": attempt_number,
        "ablation_mode": get_telemetry_label(get_ablation_mode()),
        "payload": payload,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
