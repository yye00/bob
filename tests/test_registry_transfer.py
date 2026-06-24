"""Tests for registry transfer: export_registry and import_registry."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from bob import registry_transfer
from bob.registry_transfer import export_registry, import_registry
from bob.db import get_connection, init_database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "bob.db"
    init_database(db_path=db_path)
    return db_path


def _insert_project(conn, project_id: str = None) -> str:
    if project_id is None:
        project_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects (id, name, workspace_path, created_at) VALUES (?, ?, ?, datetime('now'))",
        (project_id, f"project-{project_id[:8]}", f"/tmp/{project_id}"),
    )
    conn.commit()
    return project_id


def _insert_bug_ledger(conn, project_id: str, n: int = 1) -> list[str]:
    ids = []
    for _ in range(n):
        eid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO bug_ledger
               (id, project_id, error_type, error_message, evidence_artifacts, fix_action, created_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (eid, project_id, "test_error", "test message", "[]", "fix_action"),
        )
        ids.append(eid)
    conn.commit()
    return ids


_TASK_CLASSES = [
    "file_manipulation",
    "algorithm_implementation",
    "integration",
    "refactor",
    "research_synthesis",
]
_CONF_BUCKETS = ["0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]


def _insert_calibration(conn, project_id: str, n: int = 1) -> list[str]:
    ids = []
    for i in range(n):
        cid = str(uuid.uuid4())
        task_class = _TASK_CLASSES[i % len(_TASK_CLASSES)]
        bucket = _CONF_BUCKETS[i % len(_CONF_BUCKETS)]
        conn.execute(
            """INSERT INTO calibration_data
               (id, project_id, task_class, confidence_bucket, total_attempts, total_passes, total_failures, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (cid, project_id, task_class, bucket, 5, 4, 1),
        )
        ids.append(cid)
    conn.commit()
    return ids


def _insert_learnings_file(skill_dir: Path, skill: str, entries: int = 1) -> None:
    """Create a learnings file with N entries."""
    import json as _json
    from datetime import datetime, timezone

    skill_path = skill_dir / skill
    skill_path.mkdir(parents=True, exist_ok=True)
    ledger = skill_path / "LEARNINGS.md"
    lines = []
    for i in range(entries):
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ev = _json.dumps({"index": i})
        block = (
            f"## Learning Entry\n"
            f"- **timestamp**: {ts}\n"
            f"- **source_feature_id**: None\n"
            f"- **lesson**: lesson-{i}\n"
            f"- **evidence**: {ev}\n"
        )
        lines.append(block)
    ledger.write_text("\n---\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests: export_registry
# ---------------------------------------------------------------------------

class TestExportRegistry:
    def test_creates_file(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        conn.close()

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path)
        assert out_path.exists()

    def test_export_is_valid_json(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        conn.close()

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path)
        data = json.loads(out_path.read_text())
        assert isinstance(data, dict)

    def test_export_contains_required_sections(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        conn.close()

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path)
        data = json.loads(out_path.read_text())
        assert "bug_ledger" in data
        assert "calibration_data" in data
        assert "skill_lessons" in data
        assert "project_id" in data

    def test_export_includes_bug_ledger_entries(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        _insert_bug_ledger(conn, project_id, n=3)
        conn.close()

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path)
        data = json.loads(out_path.read_text())
        assert len(data["bug_ledger"]) == 3

    def test_export_includes_calibration_data(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        _insert_calibration(conn, project_id, n=2)
        conn.close()

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path)
        data = json.loads(out_path.read_text())
        assert len(data["calibration_data"]) == 2

    def test_export_excludes_other_projects_data(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        other_project_id = _insert_project(conn)
        _insert_bug_ledger(conn, project_id, n=2)
        _insert_bug_ledger(conn, other_project_id, n=5)
        conn.close()

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path)
        data = json.loads(out_path.read_text())
        assert len(data["bug_ledger"]) == 2

    def test_export_includes_skill_lessons(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        conn.close()

        skills_dir = tmp_path / "skills"
        _insert_learnings_file(skills_dir, "test-driven-development", entries=2)

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path, skills_dir=skills_dir)
        data = json.loads(out_path.read_text())
        assert "test-driven-development" in data["skill_lessons"]
        assert len(data["skill_lessons"]["test-driven-development"]) == 2

    def test_export_empty_project_is_valid(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        conn.close()

        out_path = tmp_path / "export.json"
        export_registry(project_id, out_path, db_path=db_path)
        data = json.loads(out_path.read_text())
        assert data["bug_ledger"] == []
        assert data["calibration_data"] == []
        assert data["skill_lessons"] == {}


# ---------------------------------------------------------------------------
# Tests: import_registry
# ---------------------------------------------------------------------------

class TestImportRegistry:
    def _make_export(self, tmp_path, project_id: str, bug_count: int = 2,
                     cal_count: int = 2, skills: dict | None = None) -> Path:
        db_path = _make_db(tmp_path / "src")
        conn = get_connection(db_path=db_path)
        src_project_id = _insert_project(conn, project_id)
        _insert_bug_ledger(conn, src_project_id, n=bug_count)
        _insert_calibration(conn, src_project_id, n=cal_count)
        conn.close()

        export_file = tmp_path / "export.json"
        skills_dir = tmp_path / "src_skills"
        if skills:
            for skill_name, entry_count in skills.items():
                _insert_learnings_file(skills_dir, skill_name, entries=entry_count)
        export_registry(src_project_id, export_file, db_path=db_path,
                        skills_dir=skills_dir if skills else None)
        return export_file

    def test_import_creates_bug_ledger_entries(self, tmp_path):
        export_file = self._make_export(tmp_path, str(uuid.uuid4()), bug_count=3)

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        conn.close()

        import_registry(export_file, dest_project_id, db_path=db_path)

        conn = get_connection(db_path=db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM bug_ledger WHERE project_id = ?", (dest_project_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 3

    def test_import_creates_calibration_entries(self, tmp_path):
        export_file = self._make_export(tmp_path, str(uuid.uuid4()), cal_count=2)

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        conn.close()

        import_registry(export_file, dest_project_id, db_path=db_path)

        conn = get_connection(db_path=db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM calibration_data WHERE project_id = ?", (dest_project_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 2

    def test_collision_resolution_skips_import_when_local_count_gte_3(self, tmp_path):
        """When local project already has >=3 bug ledger entries, skip import."""
        export_file = self._make_export(tmp_path, str(uuid.uuid4()), bug_count=5)

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        # Insert 4 local entries (>=3) — import should be skipped for bug_ledger
        _insert_bug_ledger(conn, dest_project_id, n=4)
        conn.close()

        import_registry(export_file, dest_project_id, db_path=db_path)

        conn = get_connection(db_path=db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM bug_ledger WHERE project_id = ?", (dest_project_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        # Should still be 4 (not 4+5), because local count >= 3
        assert count == 4

    def test_collision_resolution_imports_when_local_count_lt_3(self, tmp_path):
        """When local project has <3 bug ledger entries, import proceeds."""
        export_file = self._make_export(tmp_path, str(uuid.uuid4()), bug_count=5)

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        # Insert 2 local entries (<3) — import should happen
        _insert_bug_ledger(conn, dest_project_id, n=2)
        conn.close()

        import_registry(export_file, dest_project_id, db_path=db_path)

        conn = get_connection(db_path=db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM bug_ledger WHERE project_id = ?", (dest_project_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        # 2 local + 5 imported
        assert count == 7

    def test_collision_resolution_for_calibration(self, tmp_path):
        """When local calibration_data has >=3 entries, skip import."""
        export_file = self._make_export(tmp_path, str(uuid.uuid4()), cal_count=4)

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        _insert_calibration(conn, dest_project_id, n=3)
        conn.close()

        import_registry(export_file, dest_project_id, db_path=db_path)

        conn = get_connection(db_path=db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM calibration_data WHERE project_id = ?", (dest_project_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 3

    def test_import_skill_lessons(self, tmp_path):
        export_file = self._make_export(
            tmp_path, str(uuid.uuid4()),
            skills={"test-driven-development": 3}
        )

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        conn.close()

        dest_skills_dir = tmp_path / "dest_skills"
        import_registry(export_file, dest_project_id, db_path=db_path,
                        skills_dir=dest_skills_dir)

        ledger = dest_skills_dir / "test-driven-development" / "LEARNINGS.md"
        assert ledger.exists()
        content = ledger.read_text()
        assert "## Learning Entry" in content

    def test_import_idempotent_on_duplicate_ids(self, tmp_path):
        """Importing the same export twice should not create duplicate entries."""
        export_file = self._make_export(tmp_path, str(uuid.uuid4()), bug_count=3)

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        conn.close()

        import_registry(export_file, dest_project_id, db_path=db_path)
        import_registry(export_file, dest_project_id, db_path=db_path)

        conn = get_connection(db_path=db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM bug_ledger WHERE project_id = ?", (dest_project_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 3

    def test_returns_import_summary(self, tmp_path):
        """import_registry returns a summary dict with import counts."""
        export_file = self._make_export(tmp_path, str(uuid.uuid4()),
                                        bug_count=2, cal_count=1)

        db_path = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path)
        dest_project_id = _insert_project(conn)
        conn.close()

        summary = import_registry(export_file, dest_project_id, db_path=db_path)
        assert isinstance(summary, dict)
        assert "bug_ledger_imported" in summary
        assert "calibration_imported" in summary
        assert "skill_lessons_imported" in summary


# ---------------------------------------------------------------------------
# Tests: BOB_REGISTRY_TRANSFER_PATH env var integration
# ---------------------------------------------------------------------------

class TestEnvVarIntegration:
    def test_load_from_env_when_set(self, tmp_path, monkeypatch):
        """When BOB_REGISTRY_TRANSFER_PATH is set, registry is loaded."""
        src_project_id = str(uuid.uuid4())
        db_path_src = _make_db(tmp_path / "src")
        conn = get_connection(db_path=db_path_src)
        _insert_project(conn, src_project_id)
        _insert_bug_ledger(conn, src_project_id, n=2)
        conn.close()

        export_file = tmp_path / "transfer.json"
        export_registry(src_project_id, export_file, db_path=db_path_src)

        monkeypatch.setenv("BOB_REGISTRY_TRANSFER_PATH", str(export_file))

        db_path_dest = _make_db(tmp_path / "dest")
        conn = get_connection(db_path=db_path_dest)
        dest_project_id = _insert_project(conn)
        conn.close()

        summary = registry_transfer.load_transfer_registry_if_configured(
            dest_project_id, db_path=db_path_dest
        )
        assert summary is not None
        assert summary["bug_ledger_imported"] == 2

    def test_no_load_when_env_not_set(self, tmp_path, monkeypatch):
        """When BOB_REGISTRY_TRANSFER_PATH is not set, returns None."""
        monkeypatch.delenv("BOB_REGISTRY_TRANSFER_PATH", raising=False)

        db_path = _make_db(tmp_path)
        conn = get_connection(db_path=db_path)
        project_id = _insert_project(conn)
        conn.close()

        result = registry_transfer.load_transfer_registry_if_configured(
            project_id, db_path=db_path
        )
        assert result is None
