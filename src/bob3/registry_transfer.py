"""Cross-project registry transfer for Bob3.

Provides export_registry() and import_registry() to move registry entries
(skill lessons, bug ledger entries, calibration data) between projects.

When BOB3_REGISTRY_TRANSFER_PATH is set, load_transfer_registry_if_configured()
automatically loads the exported registry into a new project at startup.

When BOB3_FROZEN_REGISTRY=1 (or --frozen-registry flag), freeze_registry() pins
the registry state at process start and disables all writes during the run.

Collision resolution: prefer imported entries when local count < 3.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
import warnings
from pathlib import Path

from bob3.db import get_connection

logger = logging.getLogger(__name__)

# Module-level flag indicating whether frozen-registry mode is active.
_FROZEN: bool = False


def is_registry_frozen() -> bool:
    """Return True if frozen-registry mode is currently active."""
    return _FROZEN


def freeze_registry(*, warn: bool = True) -> None:
    """Pin the registry state at call time and disable all subsequent writes.

    After this call, export_registry() still works (reads are allowed), but
    import_registry() and load_transfer_registry_if_configured() become no-ops.
    All telemetry lines emitted while frozen will include ``frozen_registry=true``.

    Emits a UserWarning at startup when ``warn=True`` (the default).

    This function is idempotent: calling it when already frozen is safe.
    """
    global _FROZEN
    _FROZEN = True
    if warn:
        warnings.warn(
            "BOB3 FROZEN-REGISTRY MODE ACTIVE: registry writes are disabled for this run. "
            "Registry state is pinned to the snapshot at process start.",
            UserWarning,
            stacklevel=2,
        )
    logger.warning(
        "Frozen-registry mode active: all registry writes disabled for this process."
    )


def _check_not_frozen(operation: str) -> None:
    """Raise RuntimeError if the registry is frozen."""
    if _FROZEN:
        raise RuntimeError(
            f"Registry is frozen: {operation} is disabled in frozen-registry mode. "
            "Unset BOB3_FROZEN_REGISTRY or remove --frozen-registry to allow writes."
        )

_ENTRY_SEPARATOR = "\n---\n"
_ENTRY_START = "## Learning Entry"


def export_registry(
    project_id: str,
    out_path: Path,
    *,
    db_path: Path | None = None,
    skills_dir: Path | None = None,
) -> None:
    """Export registry entries for project_id to a JSON file at out_path.

    Exported sections:
    - bug_ledger: all bug ledger entries for the project
    - calibration_data: all calibration data for the project
    - skill_lessons: dict mapping skill name -> list of parsed learning entries

    Args:
        project_id: The source project ID.
        out_path: Destination file path for the export JSON.
        db_path: Optional override for database path.
        skills_dir: Optional override for the skills directory. Defaults to
            the package's built-in skills directory.
    """
    out_path = Path(out_path)
    conn = get_connection(db_path=db_path)
    try:
        bug_ledger = _export_bug_ledger(conn, project_id)
        calibration = _export_calibration(conn, project_id)
    finally:
        conn.close()

    skill_lessons = _export_skill_lessons(skills_dir)

    payload = {
        "project_id": project_id,
        "bug_ledger": bug_ledger,
        "calibration_data": calibration,
        "skill_lessons": skill_lessons,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Exported registry for project %s to %s "
        "(bugs=%d, calibration=%d, skill_sets=%d)",
        project_id, out_path, len(bug_ledger), len(calibration), len(skill_lessons),
    )


def import_registry(
    in_path: Path,
    project_id: str,
    *,
    db_path: Path | None = None,
    skills_dir: Path | None = None,
) -> dict:
    """Import registry entries from in_path into project_id.

    Collision resolution: for each table, if the destination project already
    has >= 3 entries, the import for that table is skipped. Otherwise entries
    are appended (duplicates by id are ignored via INSERT OR IGNORE).

    Raises RuntimeError if the registry is frozen.

    Args:
        in_path: Path to the exported JSON file.
        project_id: The destination project ID.
        db_path: Optional override for database path.
        skills_dir: Optional override for the skills directory.

    Returns:
        Summary dict with keys: bug_ledger_imported, calibration_imported,
        skill_lessons_imported.
    """
    _check_not_frozen("import_registry")
    in_path = Path(in_path)
    payload = json.loads(in_path.read_text(encoding="utf-8"))

    conn = get_connection(db_path=db_path)
    try:
        bugs_imported = _import_bug_ledger(conn, project_id, payload.get("bug_ledger", []))
        cal_imported = _import_calibration(conn, project_id, payload.get("calibration_data", []))
    finally:
        conn.close()

    skills_imported = _import_skill_lessons(payload.get("skill_lessons", {}), skills_dir)

    summary = {
        "bug_ledger_imported": bugs_imported,
        "calibration_imported": cal_imported,
        "skill_lessons_imported": skills_imported,
    }
    logger.info(
        "Imported registry into project %s: bugs=%d, calibration=%d, skills=%d",
        project_id, bugs_imported, cal_imported, skills_imported,
    )
    return summary


def load_transfer_registry_if_configured(
    project_id: str,
    *,
    db_path: Path | None = None,
    skills_dir: Path | None = None,
) -> dict | None:
    """Load registry from BOB3_REGISTRY_TRANSFER_PATH if set.

    Call this at project startup. Returns an import summary dict if the env
    var is set and the file exists, or None otherwise.

    Returns None immediately if the registry is frozen (writes are disabled).
    """
    if _FROZEN:
        logger.info(
            "load_transfer_registry_if_configured: skipped (frozen-registry mode active)"
        )
        return None

    transfer_path = os.environ.get("BOB3_REGISTRY_TRANSFER_PATH")
    if not transfer_path:
        return None

    in_path = Path(transfer_path)
    if not in_path.is_file():
        logger.warning("BOB3_REGISTRY_TRANSFER_PATH=%s is not a file; skipping", transfer_path)
        return None

    logger.info("Loading transfer registry from %s for project %s", in_path, project_id)
    return import_registry(in_path, project_id, db_path=db_path, skills_dir=skills_dir)


def activate_frozen_registry_if_configured() -> bool:
    """Activate frozen-registry mode from env var BOB3_FROZEN_REGISTRY if set.

    Call this at process/CLI startup (alongside --frozen-registry flag handling).
    Returns True if frozen mode was activated, False otherwise.
    """
    value = os.environ.get("BOB3_FROZEN_REGISTRY", "").strip()
    if value in ("1", "true", "yes"):
        freeze_registry(warn=True)
        return True
    return False


# ---------------------------------------------------------------------------
# Private helpers — export
# ---------------------------------------------------------------------------

def _export_bug_ledger(conn, project_id: str) -> list[dict]:
    cursor = conn.execute(
        "SELECT * FROM bug_ledger WHERE project_id = ?", (project_id,)
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _export_calibration(conn, project_id: str) -> list[dict]:
    cursor = conn.execute(
        "SELECT * FROM calibration_data WHERE project_id = ?", (project_id,)
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _export_skill_lessons(skills_dir: Path | None) -> dict[str, list[dict]]:
    if skills_dir is None:
        skills_dir = Path(__file__).parent / "skills"

    if not skills_dir.is_dir():
        return {}

    result: dict[str, list[dict]] = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        ledger = skill_dir / "LEARNINGS.md"
        if not ledger.exists():
            continue
        entries = _parse_learnings(ledger)
        if entries:
            result[skill_dir.name] = entries
    return result


def _parse_learnings(ledger_path: Path) -> list[dict]:
    content = ledger_path.read_text(encoding="utf-8")
    raw_entries = [block.strip() for block in content.split(_ENTRY_SEPARATOR.strip())]
    results = []
    for block in raw_entries:
        if not block.startswith(_ENTRY_START):
            continue
        entry = _parse_learning_entry(block)
        if entry is not None:
            results.append(entry)
    return results


def _parse_learning_entry(block: str) -> dict | None:
    lines = block.splitlines()
    fields: dict = {}
    for line in lines:
        if line.startswith("- **timestamp**:"):
            fields["timestamp"] = line[len("- **timestamp**:"):].strip()
        elif line.startswith("- **source_feature_id**:"):
            raw = line[len("- **source_feature_id**:"):].strip()
            fields["source_feature_id"] = None if raw == "None" else raw
        elif line.startswith("- **lesson**:"):
            fields["lesson"] = line[len("- **lesson**:"):].strip()
        elif line.startswith("- **evidence**:"):
            raw = line[len("- **evidence**:"):].strip()
            try:
                fields["evidence"] = json.loads(raw)
            except json.JSONDecodeError:
                fields["evidence"] = {}

    required = {"timestamp", "lesson", "evidence", "source_feature_id"}
    if not required.issubset(fields):
        return None
    return fields


# ---------------------------------------------------------------------------
# Private helpers — import
# ---------------------------------------------------------------------------

def _local_count(conn, table: str, project_id: str) -> int:
    cursor = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE project_id = ?",  # noqa: S608
        (project_id,),
    )
    return cursor.fetchone()[0]


def _import_bug_ledger(conn, project_id: str, entries: list[dict]) -> int:
    if not entries:
        return 0
    if _local_count(conn, "bug_ledger", project_id) >= 3:
        logger.debug("bug_ledger: local count >=3, skipping import for project %s", project_id)
        return 0

    # Use a deterministic id derived from the source id + dest project_id so
    # that importing the same export twice is idempotent.
    imported = 0
    for entry in entries:
        source_id = entry.get("id") or str(uuid.uuid4())
        stable_id = f"xfer-{project_id[:8]}-{source_id}"
        try:
            conn.execute(
                """INSERT OR IGNORE INTO bug_ledger
                   (id, project_id, error_type, error_message, error_context,
                    evidence_artifacts, blame_target, root_cause, fix_action,
                    fix_details, fix_evidence, resolved, resolution_attempts,
                    titans_memory_id, created_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    stable_id,
                    project_id,
                    entry.get("error_type", ""),
                    entry.get("error_message", ""),
                    entry.get("error_context"),
                    entry.get("evidence_artifacts", "[]"),
                    entry.get("blame_target"),
                    entry.get("root_cause"),
                    entry.get("fix_action", ""),
                    entry.get("fix_details"),
                    entry.get("fix_evidence"),
                    entry.get("resolved", False),
                    entry.get("resolution_attempts", 1),
                    entry.get("titans_memory_id"),
                    entry.get("created_at"),
                    entry.get("resolved_at"),
                ),
            )
            imported += 1
        except Exception:
            logger.exception("Failed to import bug_ledger entry")
    conn.commit()
    return imported


def _import_calibration(conn, project_id: str, entries: list[dict]) -> int:
    if not entries:
        return 0
    if _local_count(conn, "calibration_data", project_id) >= 3:
        logger.debug("calibration_data: local count >=3, skipping import for project %s", project_id)
        return 0

    # Use a stable id derived from source id + dest project so double-import is
    # idempotent. The UNIQUE(project_id, task_class, confidence_bucket) constraint
    # also guards against semantic duplicates.
    imported = 0
    for entry in entries:
        source_id = entry.get("id") or str(uuid.uuid4())
        stable_id = f"xfer-{project_id[:8]}-{source_id}"
        try:
            conn.execute(
                """INSERT OR IGNORE INTO calibration_data
                   (id, project_id, task_class, confidence_bucket, total_attempts,
                    total_passes, total_failures, empirical_pass_rate, expected_pass_rate,
                    drift, adjusted_threshold, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    stable_id,
                    project_id,
                    entry.get("task_class", ""),
                    entry.get("confidence_bucket", ""),
                    entry.get("total_attempts", 0),
                    entry.get("total_passes", 0),
                    entry.get("total_failures", 0),
                    entry.get("empirical_pass_rate"),
                    entry.get("expected_pass_rate"),
                    entry.get("drift"),
                    entry.get("adjusted_threshold"),
                    entry.get("last_updated"),
                ),
            )
            imported += 1
        except Exception:
            logger.exception("Failed to import calibration_data entry")
    conn.commit()
    return imported


def _import_skill_lessons(lessons: dict[str, list[dict]], skills_dir: Path | None) -> int:
    if not lessons:
        return 0
    if skills_dir is None:
        skills_dir = Path(__file__).parent / "skills"

    total_imported = 0
    for skill_name, entries in lessons.items():
        if not entries:
            continue
        skill_path = skills_dir / skill_name
        ledger_path = skill_path / "LEARNINGS.md"

        # Check local lesson count for collision resolution
        local_count = 0
        if ledger_path.exists():
            local_count = len(_parse_learnings(ledger_path))

        if local_count >= 3:
            logger.debug(
                "skill_lessons[%s]: local count >=3, skipping import", skill_name
            )
            continue

        skill_path.mkdir(parents=True, exist_ok=True)
        blocks = []
        for entry in entries:
            feat = entry.get("source_feature_id") or "None"
            evidence_json = json.dumps(entry.get("evidence", {}), ensure_ascii=False)
            block = (
                f"{_ENTRY_START}\n"
                f"- **timestamp**: {entry.get('timestamp', '')}\n"
                f"- **source_feature_id**: {feat}\n"
                f"- **lesson**: {entry.get('lesson', '')}\n"
                f"- **evidence**: {evidence_json}\n"
            )
            blocks.append(block)

        if ledger_path.exists() and ledger_path.stat().st_size > 0:
            with ledger_path.open("a", encoding="utf-8") as f:
                for block in blocks:
                    f.write(_ENTRY_SEPARATOR)
                    f.write(block)
        else:
            ledger_path.write_text(_ENTRY_SEPARATOR.join(blocks), encoding="utf-8")

        total_imported += len(entries)

    return total_imported
