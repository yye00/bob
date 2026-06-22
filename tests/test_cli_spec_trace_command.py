"""Test that `bob spec trace <feature>:<ac>` works end-to-end."""

import json
import sqlite3
import tempfile
import os

import pytest
from click.testing import CliRunner

from bob3.cli import main


@pytest.fixture()
def db_with_feature(tmp_path):
    """Create a temporary bob3.db with a project and one feature."""
    db_path = tmp_path / "bob3.db"
    from bob3.db import init_database, get_connection

    init_database(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        project_id = "test-project-001"
        conn.execute(
            "INSERT INTO projects (id, name, workspace_path, status) VALUES (?, ?, ?, ?)",
            (project_id, "test-project", str(tmp_path), "planning"),
        )

        feature_id = "F-R7-451"
        acs = json.dumps([
            "The system shall emit acceptance criteria from the feature description.",
            "Each criterion must be machine-checkable.",
        ])
        conn.execute(
            "INSERT INTO features (id, project_id, name, description, acceptance_criteria, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                feature_id,
                project_id,
                "Test feature",
                "The system shall emit acceptance criteria from the feature description. "
                "Each criterion must be machine-checkable.",
                acs,
                "ready",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return db_path, feature_id


def test_spec_trace_exits_zero_and_contains_span(db_with_feature):
    """Running `bob spec-trace F-R7-451:0` exits 0 and stdout contains 'span='."""
    db_path, feature_id = db_with_feature

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["spec-trace", f"{feature_id}:0", "--db", str(db_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, f"Non-zero exit: {result.output!r}"
    assert "span=" in result.output, (
        f"'span=' not found in output: {result.output!r}"
    )


def test_spec_trace_displays_feature_and_ac(db_with_feature):
    """Output includes the feature ID and the AC text."""
    db_path, feature_id = db_with_feature

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["spec-trace", f"{feature_id}:0", "--db", str(db_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert feature_id in result.output
    assert "emit acceptance criteria" in result.output


def test_spec_trace_second_ac(db_with_feature):
    """AC index 1 also works and references the second criterion."""
    db_path, feature_id = db_with_feature

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["spec-trace", f"{feature_id}:1", "--db", str(db_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "machine-checkable" in result.output


def test_spec_trace_missing_feature_exits_nonzero(db_with_feature):
    """Unknown feature ID exits non-zero."""
    db_path, _ = db_with_feature

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["spec-trace", "nonexistent-feature:0", "--db", str(db_path)],
    )

    assert result.exit_code != 0


def test_spec_trace_bad_index_exits_nonzero(db_with_feature):
    """Out-of-range AC index exits non-zero."""
    db_path, feature_id = db_with_feature

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["spec-trace", f"{feature_id}:99", "--db", str(db_path)],
    )

    assert result.exit_code != 0


def test_spec_trace_invalid_format_exits_nonzero(db_with_feature):
    """Missing colon in TARGET exits non-zero."""
    db_path, feature_id = db_with_feature

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["spec-trace", feature_id, "--db", str(db_path)],
    )

    assert result.exit_code != 0
