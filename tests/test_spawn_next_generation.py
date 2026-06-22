"""Tests for spawn_next_generation.sh bob3 init re-run behavior.

Verifies that tools/spawn_next_generation.sh invokes bob3 init after rsync
so the child generation's DB gets correct project name/spec_path metadata,
and that verify_project_metadata in run_loop detects and fixes stale metadata.
"""
from __future__ import annotations

import re
import sqlite3
import tempfile
from pathlib import Path

import pytest

SPAWN_SCRIPT = Path(__file__).parents[1] / "tools" / "spawn_next_generation.sh"


# ---------------------------------------------------------------------------
# spawn_next_generation.sh structural tests
# ---------------------------------------------------------------------------

class TestSpawnScriptFileExists:
    def test_file_exists(self):
        assert SPAWN_SCRIPT.is_file(), f"Script not found: {SPAWN_SCRIPT}"


class TestSpawnScriptContainsBob3Init:
    def test_contains_bob3_init_invocation(self):
        text = SPAWN_SCRIPT.read_text()
        has_literal = "bob3 init" in text
        has_alias = bool(
            re.search(r'bob\$?NEXT_NUM"\s+init', text)
            or re.search(r'bob\d+\s+init', text)
            or re.search(r'/bin/bob[^"]*"\s+init', text)
        )
        assert has_literal or has_alias, (
            "spawn_next_generation.sh does not contain a 'bob3 init' invocation"
        )

    def test_init_appears_after_rsync(self):
        text = SPAWN_SCRIPT.read_text()
        rsync_pos = text.find("rsync")
        assert rsync_pos != -1, "No rsync call found in spawn script"

        init_match = re.search(r'init\s+.*--name', text)
        if init_match is None:
            init_match = re.search(
                r'"\$NEXT_DIR/\.venv/bin/bob\$NEXT_NUM"\s+init', text
            )

        assert init_match is not None, "No 'init --name' call found in spawn script"
        assert init_match.start() > rsync_pos, (
            "init invocation appears before rsync block"
        )

    def test_init_passes_name_flag(self):
        text = SPAWN_SCRIPT.read_text()
        assert "--name" in text, "spawn script does not pass --name to init"

    def test_init_references_next_generation_variable(self):
        text = SPAWN_SCRIPT.read_text()
        assert "NEXT_NUM" in text or re.search(r'--name\s+bob\d+', text), (
            "spawn script --name flag does not reference next generation"
        )

    def test_init_spec_path_handling(self):
        """Script must handle the case where the spec file does or does not exist."""
        text = SPAWN_SCRIPT.read_text()
        # Script should conditionally pass --spec or skip it gracefully
        assert "--spec" in text or "SPEC_FOR_NEXT" in text, (
            "spawn script does not handle spec path for init"
        )


# ---------------------------------------------------------------------------
# verify_project_metadata unit tests
# ---------------------------------------------------------------------------

def _make_db_with_project(tmp_path: Path, name: str, spec_path: str = "") -> Path:
    db = tmp_path / "bob3.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            spec_path TEXT
        )
    """)
    conn.execute(
        "INSERT INTO projects (name, spec_path) VALUES (?, ?)",
        (name, spec_path),
    )
    conn.commit()
    conn.close()
    return db


class TestVerifyProjectMetadata:
    def test_no_update_when_name_matches(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        workspace = tmp_path / "bob59"
        workspace.mkdir()
        db = _make_db_with_project(tmp_path, "bob59")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob59"
        assert result.spec_path_was_stale is False

    def test_updates_stale_name(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        # DB still holds old parent name "bob59"
        db = _make_db_with_project(tmp_path, "bob59")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob60"
        assert result.workspace_basename == "bob60"

        # Verify it was actually written
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob60"

    def test_detects_pytest_tmpdir_spec_path(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        stale_spec = "/tmp/pytest-of-user/pytest-42/test_something0/minimal.yaml"
        db = _make_db_with_project(tmp_path, "bob60", spec_path=stale_spec)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True

    def test_no_pytest_tmpdir_flag_when_spec_clean(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        db = _make_db_with_project(
            tmp_path, "bob60", spec_path="/home/user/bob60/examples/bootstrap_v0.59.yaml"
        )

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_returns_named_tuple(self, tmp_path):
        from bob3.run_loop import verify_project_metadata, ProjectMetadataCheckResult

        workspace = tmp_path / "bob59"
        workspace.mkdir()
        db = _make_db_with_project(tmp_path, "bob59")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert hasattr(result, "name_was_stale")
        assert hasattr(result, "spec_path_was_stale")
        assert hasattr(result, "corrected_name")
        assert hasattr(result, "workspace_basename")

    def test_exported_in_all(self):
        import bob3.run_loop as rl

        assert "verify_project_metadata" in rl.__all__
        assert "ProjectMetadataCheckResult" in rl.__all__


# ---------------------------------------------------------------------------
# project_metadata_check module unit tests
# ---------------------------------------------------------------------------

class TestUpdateProjectNameIfMismatch:
    def test_returns_false_when_name_matches(self, tmp_path):
        from bob3.orchestrator.project_metadata_check import update_project_name_if_mismatch

        workspace = tmp_path / "bob59"
        workspace.mkdir()
        db = _make_db_with_project(tmp_path, "bob59")

        result = update_project_name_if_mismatch(db_path=db, workspace=workspace)
        assert result is False

    def test_returns_true_and_updates_when_stale(self, tmp_path):
        from bob3.orchestrator.project_metadata_check import update_project_name_if_mismatch

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        db = _make_db_with_project(tmp_path, "bob59")

        result = update_project_name_if_mismatch(db_path=db, workspace=workspace)
        assert result is True

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob60"

    def test_returns_false_on_empty_table(self, tmp_path):
        from bob3.orchestrator.project_metadata_check import update_project_name_if_mismatch

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, spec_path TEXT)")
        conn.commit()
        conn.close()

        result = update_project_name_if_mismatch(db_path=db, workspace=workspace)
        assert result is False


class TestRejectPytestTmpdirInSpecPath:
    def test_raises_on_pytest_tmpdir(self, tmp_path):
        from bob3.orchestrator.project_metadata_check import (
            reject_pytest_tmpdir_in_spec_path,
            StaleSpecPathError,
        )

        db = _make_db_with_project(
            tmp_path, "bob59", "/tmp/pytest-of-user/pytest-1/test_0/spec.yaml"
        )

        with pytest.raises(StaleSpecPathError):
            reject_pytest_tmpdir_in_spec_path(db_path=db)

    def test_no_raise_on_clean_spec_path(self, tmp_path):
        from bob3.orchestrator.project_metadata_check import reject_pytest_tmpdir_in_spec_path

        db = _make_db_with_project(
            tmp_path, "bob59", "/home/user/bob59/examples/bootstrap_v0.58.yaml"
        )

        reject_pytest_tmpdir_in_spec_path(db_path=db)  # should not raise

    def test_no_raise_on_empty_spec_path(self, tmp_path):
        from bob3.orchestrator.project_metadata_check import reject_pytest_tmpdir_in_spec_path

        db = _make_db_with_project(tmp_path, "bob59", "")

        reject_pytest_tmpdir_in_spec_path(db_path=db)  # should not raise


# ---------------------------------------------------------------------------
# Module-level test: projects.name matches workspace after spawn (AC2)
# ---------------------------------------------------------------------------

def test_projects_name_matches_workspace_after_spawn(tmp_path):
    """After spawn rsync, verify_project_metadata corrects stale project name.

    Simulates a child generation workspace whose bob3.db still has the parent's
    name ("bob58") after rsync, then verifies that verify_project_metadata
    detects the mismatch and updates it to match the workspace basename ("bob59").
    """
    from bob3.run_loop import verify_project_metadata

    workspace = tmp_path / "bob59"
    workspace.mkdir()
    # Simulate rsync'd DB: name still points to parent gen "bob58"
    db = _make_db_with_project(tmp_path, "bob58")

    result = verify_project_metadata(workspace=workspace, db_path=db)

    assert result.name_was_stale is True, "Expected stale name to be detected"
    assert result.corrected_name == "bob59", "Expected corrected_name to be workspace basename"
    assert result.workspace_basename == "bob59"

    # Verify the DB was actually updated
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
    conn.close()
    assert row[0] == "bob59", "DB projects.name should have been updated to bob59"


# ---------------------------------------------------------------------------
# Boundary and invalid-input tests (AC5, AC6)
# ---------------------------------------------------------------------------

def test_verify_project_metadata_empty_workspace_string_is_noop(tmp_path):
    """Empty string workspace is treated as cwd — returns a well-defined result."""
    from bob3.run_loop import verify_project_metadata

    workspace = tmp_path / "somedir"
    workspace.mkdir()
    db = _make_db_with_project(tmp_path, "somedir")

    # Empty string should not crash; returns a valid result using cwd
    result = verify_project_metadata(workspace="", db_path=db)
    assert hasattr(result, "name_was_stale")
    assert hasattr(result, "workspace_basename")
    assert isinstance(result.workspace_basename, str)


def test_verify_project_metadata_raises_on_invalid_workspace_type():
    """Passing a non-path type raises ValueError rather than crashing silently."""
    from bob3.run_loop import verify_project_metadata

    with pytest.raises(ValueError):
        verify_project_metadata(workspace=42)  # type: ignore[arg-type]


def test_verify_project_metadata_raises_on_list_workspace():
    """List workspace type raises ValueError (not silently swallowed)."""
    from bob3.run_loop import verify_project_metadata

    with pytest.raises(ValueError):
        verify_project_metadata(workspace=["bob59"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: parent-gen DB inheritance wired into spawn_next_generation.sh
# (F-R7-422 / 82231bc5)
# ---------------------------------------------------------------------------

def assert_spawn_script_invokes_parent_gen_inheritance() -> None:
    """Assert that spawn_next_generation.sh invokes parent-gen DB inheritance.

    Called from tests/test_parent_gen_db_inheritance.py to establish the
    integration link between the spawn script and the inheritance module.
    Raises AssertionError if the wiring is absent.
    """
    text = SPAWN_SCRIPT.read_text()
    assert "parent_gen_db_inheritance" in text or "inherit_from_parent_db" in text, (
        "spawn_next_generation.sh does not invoke parent-gen DB inheritance "
        "(expected 'parent_gen_db_inheritance' or 'inherit_from_parent_db')"
    )


class TestSpawnScriptInvokesParentGenInheritance:
    def test_script_calls_inherit_from_parent_db(self):
        """spawn_next_generation.sh must call the parent-gen inheritance step."""
        assert_spawn_script_invokes_parent_gen_inheritance()

    def test_inheritance_section_appears_after_init(self):
        """Inheritance stamping must happen after bob3 init (so columns exist)."""
        text = SPAWN_SCRIPT.read_text()
        init_pos = text.find("bob3 init")
        if init_pos == -1:
            # Try regex variant
            import re as _re
            m = _re.search(r'bob\$?NEXT_NUM["\s]+init', text)
            init_pos = m.start() if m else -1

        inherit_pos = text.find("inherit_from_parent_db")
        if inherit_pos == -1:
            inherit_pos = text.find("parent_gen_db_inheritance")

        assert init_pos != -1, "spawn script must invoke bob3 init"
        assert inherit_pos != -1, (
            "spawn script must invoke parent-gen DB inheritance "
            "(expected 'inherit_from_parent_db' or 'parent_gen_db_inheritance')"
        )
        assert inherit_pos > init_pos, (
            "parent-gen inheritance must appear after bob3 init in spawn script"
        )


# ---------------------------------------------------------------------------
# AC test: test_bob3_init_rerun_after_spawn
# ---------------------------------------------------------------------------

def test_bob3_init_rerun_after_spawn():
    """spawn_next_generation.sh must invoke bob3 init after rsync to fix stale metadata.

    Verifies that:
    1. The spawn script file exists.
    2. It contains a bob3 init invocation with --name flag.
    3. The init invocation appears after the rsync block.
    4. The script handles spec path conditionally.
    """
    assert SPAWN_SCRIPT.is_file(), f"spawn_next_generation.sh not found at {SPAWN_SCRIPT}"

    text = SPAWN_SCRIPT.read_text()

    # Must contain rsync
    assert "rsync" in text, "spawn script must contain rsync"

    # Must invoke bob3 init (literal or via variable expansion)
    has_init = (
        "bob3 init" in text
        or bool(re.search(r'bob\$?NEXT_NUM["\s]+init', text))
        or bool(re.search(r'bin/bob[^"]*"\s+init', text))
    )
    assert has_init, "spawn_next_generation.sh must invoke bob3 init after rsync"

    # Must pass --name flag to init
    assert "--name" in text, "bob3 init call must include --name flag"

    # init must appear after rsync
    rsync_pos = text.find("rsync")
    init_pos = text.find("bob3 init")
    if init_pos == -1:
        m = re.search(r'bin/bob[^"]*"\s+init', text)
        init_pos = m.start() if m else -1

    assert init_pos != -1, "spawn script must invoke bob3 init"
    assert init_pos > rsync_pos, "bob3 init must appear after rsync in spawn script"

    # Must reference NEXT_NUM or explicit next gen in --name
    assert "NEXT_NUM" in text or bool(re.search(r'--name\s+bob\d+', text)), (
        "--name must reference the next generation (NEXT_NUM variable or literal)"
    )

    # Must handle spec path (conditional logic or SPEC_FOR_NEXT variable)
    assert "--spec" in text or "SPEC_FOR_NEXT" in text, (
        "spawn script must conditionally handle --spec flag for bob3 init"
    )
