"""Public registry release — versioned artifact export.

Exports the findings registry (reviews/findings.yaml) as a versioned,
citable YAML artifact with a stable schema. Includes provenance metadata
(bob_version, experiment_run_ids, timestamp) suitable for paper
supplementary materials.

Public API:
    export_public_registry(out_path, *, findings_path, experiment_run_ids, bob_version)
    load_public_registry(path) -> dict
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import bob

ARTIFACT_SCHEMA_VERSION = "1.0"


def export_public_registry(
    out_path: str | Path,
    *,
    findings_path: str | Path | None = None,
    experiment_run_ids: list[str] | None = None,
    bob_version: str | None = None,
) -> Path:
    """Export the findings registry as a versioned, citable YAML artifact.

    Args:
        out_path: Destination path for the output YAML file.
        findings_path: Path to findings.yaml. If omitted, auto-discovered
            by walking up from this module to find reviews/findings.yaml.
        experiment_run_ids: List of experiment/run IDs to embed in provenance.
            If omitted, defaults to an empty list.
        bob_version: Bob version string to embed. Defaults to bob.__version__.

    Returns:
        The resolved output path.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    findings_path = _resolve_findings_path(findings_path)
    raw = yaml.safe_load(findings_path.read_text(encoding="utf-8")) or {}
    findings: list[dict] = raw.get("findings", []) or []

    if bob_version is None:
        bob_version = bob.__version__

    if experiment_run_ids is None:
        experiment_run_ids = []

    timestamp = datetime.now(tz=timezone.utc).isoformat()

    artifact: dict[str, Any] = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "provenance": {
            "bob_version": bob_version,
            "timestamp": timestamp,
            "experiment_run_ids": list(experiment_run_ids),
        },
        "summary": _build_summary(findings),
        "findings": [_normalize_finding(f) for f in findings],
    }

    out_path.write_text(
        yaml.dump(artifact, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return out_path


def load_public_registry(path: str | Path) -> dict:
    """Load and validate a previously exported public registry artifact.

    Args:
        path: Path to the exported YAML file.

    Returns:
        Parsed artifact dict.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the artifact_schema_version is unrecognised.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Registry artifact not found: {path}")

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    version = doc.get("artifact_schema_version", "")
    if version != ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported artifact schema version: {version!r}. "
            f"Expected {ARTIFACT_SCHEMA_VERSION!r}."
        )
    return doc


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_findings_path(findings_path: str | Path | None) -> Path:
    if findings_path is not None:
        p = Path(findings_path)
        if not p.exists():
            raise FileNotFoundError(f"findings.yaml not found at: {p}")
        return p

    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        candidate = parent / "reviews" / "findings.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Could not locate reviews/findings.yaml by walking up from the bob package. "
        "Pass findings_path= explicitly."
    )


def _build_summary(findings: list[dict]) -> dict[str, Any]:
    total = len(findings)
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "unknown")
        sta = f.get("status", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_status[sta] = by_status.get(sta, 0) + 1
    return {
        "total_findings": total,
        "by_severity": by_severity,
        "by_status": by_status,
    }


def _normalize_finding(f: dict) -> dict:
    """Return a copy of the finding dict with only stable, citable fields."""
    out: dict[str, Any] = {
        "id": f.get("id", ""),
        "title": f.get("title", ""),
        "pattern": f.get("pattern", ""),
        "files": list(f.get("files", [])),
        "severity": f.get("severity", ""),
        "status": f.get("status", ""),
    }
    if f.get("tags"):
        out["tags"] = list(f["tags"])
    if f.get("related"):
        out["related"] = list(f["related"])
    if f.get("fixed_in"):
        out["fixed_in"] = f["fixed_in"]
    if f.get("fixed_at"):
        out["fixed_at"] = f["fixed_at"]
    if f.get("notes"):
        out["notes"] = f["notes"]
    return out
