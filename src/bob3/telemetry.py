"""Unified telemetry exporter — writes one fixed-schema JSON line per attempt to run.jsonl."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bob3.ablation import get_ablation_mode, get_telemetry_label
from bob3.learnings import get_promote_on_n
from bob3.version_probe import get_model_id, get_sdk_version
from bob3.registry_transfer import is_registry_frozen

_DEFAULT_RUN_JSONL_PATH = Path(".bob3") / "run.jsonl"

_SCHEMA_DEFAULTS: dict[str, Any] = {
    "run_id": None,
    "variant": None,
    "spec_id": None,
    "spec_version": None,
    "seed": None,
    "feature_id": None,
    "attempt_number": None,
    "completion_status": None,
    "cost_usd": None,
    "tokens_in": None,
    "tokens_out": None,
    "duration_ms": None,
    "hack_verdict": None,
    "confidence_predicted": None,
    "calibrated_confidence": None,
    "timestamp_utc": None,
    "sdk_version": None,
    "model_id": None,
    "frozen_registry": False,
    "promote_on_n": None,
}


def get_run_jsonl_path() -> Path:
    """Return the path to the unified telemetry run.jsonl file."""
    return _DEFAULT_RUN_JSONL_PATH


def emit_telemetry_line(run_id: str, **fields: Any) -> None:
    """Append one fixed-schema JSON record to <workspace>/.bob3/run.jsonl.

    All schema fields are present in every record; unspecified optional fields
    are written as null. The ``variant`` field is always derived from the active
    BOB3_ABLATION_MODE unless explicitly overridden in ``fields``.
    """
    path = get_run_jsonl_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = dict(_SCHEMA_DEFAULTS)
    record["run_id"] = run_id
    record["variant"] = get_telemetry_label(get_ablation_mode())
    record["timestamp_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record["sdk_version"] = get_sdk_version()
    record["model_id"] = get_model_id()
    record["frozen_registry"] = is_registry_frozen()
    record["promote_on_n"] = get_promote_on_n()
    record.update(fields)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
