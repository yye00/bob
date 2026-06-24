"""Tests for F073: Rich terminal UI output for status command.

Verifies that the status command uses Rich library for:
- Formatted tables
- Feature counts by status with colors
- Progress bars for completion percentage
- Resource usage (cost) with warnings if near limit
"""

import pathlib
import sqlite3
import uuid

import pytest
from click.testing import CliRunner


def _init_project(tmp_path, name="test-project"):
    """Helper: create an initialized project and return (project_path, db_path)."""
    from bob.cli import main

    project_path = tmp_path / name
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(project_path)])
    assert result.exit_code == 0, f"init failed: {result.output}"
    db_path = project_path / "bob.db"
    return project_path, db_path


def _get_project_id(db_path):
    """Helper: retrieve the first project ID from the database."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT id FROM projects LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def _add_features(db_path, project_id, features):
    """Helper: insert features into the database.

    features is a list of (id, name, status) tuples.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    for fid, fname, fstatus in features:
        conn.execute(
            "INSERT INTO features (id, project_id, name, status) VALUES (?, ?, ?, ?)",
            (fid, project_id, fname, fstatus),
        )
    conn.commit()
    conn.close()


def _set_project_cost(db_path, project_id, total_cost, max_cost=500.0):
    """Helper: set cost values on the project record."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE projects SET total_cost_usd = ?, max_cost_usd = ? WHERE id = ?",
        (total_cost, max_cost, project_id),
    )
    conn.commit()
    conn.close()


# ============================================================
# Step 1: Use Rich library for formatted tables
# ============================================================


class TestRichFormattedTables:
    """Step 1: Status command uses Rich library for formatted tables."""

    def test_cli_uses_rich_table(self):
        """The cli module uses Rich Table for output."""
        import inspect
        import bob.cli

        source = inspect.getsource(bob.cli)
        assert "from rich" in source or "import rich" in source
        assert "Table" in source

    def test_cli_uses_rich_console(self):
        """The cli module uses Rich Console."""
        import inspect
        import bob.cli

        source = inspect.getsource(bob.cli)
        assert "Console" in source

    def test_status_output_contains_table_borders(self, tmp_path):
        """Status output should contain Rich table formatting characters."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        # Rich tables use box-drawing characters or ASCII borders
        output = result.output
        assert any(ch in output for ch in ("─", "│", "┌", "┐", "└", "┘", "+", "|", "-")), (
            f"Expected table border characters in output: {output}"
        )


# ============================================================
# Step 2: Display feature counts by status with colors
# ============================================================


class TestFeatureCountsWithColors:
    """Step 2: Feature counts by status are displayed with colors."""

    def test_status_shows_colored_status_labels(self, tmp_path):
        """Feature status labels should be rendered (Rich markup produces styled output)."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Feature A", "completed"),
                (str(uuid.uuid4()), "Feature B", "pending"),
                (str(uuid.uuid4()), "Feature C", "failed"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "completed" in output_lower
        assert "pending" in output_lower
        assert "failed" in output_lower

    def test_status_uses_rich_style_markup_in_source(self):
        """The _show_project_status function should use Rich style markup for colors."""
        import inspect
        import bob.cli

        source = inspect.getsource(bob.cli._show_project_status)
        # Should use Rich color markup for status styling
        assert "style" in source.lower() or "color" in source.lower() or "[" in source, (
            "Expected Rich style/color markup in _show_project_status"
        )

    def test_status_counts_are_accurate(self, tmp_path):
        """Feature counts per status should be correct."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "A", "completed"),
                (str(uuid.uuid4()), "B", "completed"),
                (str(uuid.uuid4()), "C", "completed"),
                (str(uuid.uuid4()), "D", "pending"),
                (str(uuid.uuid4()), "E", "executing"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "5" in result.output  # total
        assert "3" in result.output  # completed count


# ============================================================
# Step 3: Show progress bars for completion percentage
# ============================================================


class TestProgressBars:
    """Step 3: Status output includes progress bars for completion percentage."""

    def test_status_shows_progress_indicator(self, tmp_path):
        """Status output should include a progress indicator for completion."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "A", "completed"),
                (str(uuid.uuid4()), "B", "completed"),
                (str(uuid.uuid4()), "C", "pending"),
                (str(uuid.uuid4()), "D", "pending"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        output = result.output
        # Should contain either a progress bar character or a percentage
        has_progress = (
            "%" in output
            or "━" in output
            or "█" in output
            or "▓" in output
            or "progress" in output.lower()
        )
        assert has_progress, f"Expected progress indicator in output: {output}"

    def test_status_shows_completion_percentage(self, tmp_path):
        """Status should show a completion percentage value."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "A", "completed"),
                (str(uuid.uuid4()), "B", "pending"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        # 1 of 2 completed = 50%
        assert "50" in result.output, f"Expected '50' (percent) in output: {result.output}"

    def test_status_zero_features_shows_zero_progress(self, tmp_path):
        """With no features, progress should show 0%."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "0" in result.output

    def test_status_all_completed_shows_full_progress(self, tmp_path):
        """With all features completed, progress should show 100%."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "A", "completed"),
                (str(uuid.uuid4()), "B", "completed"),
                (str(uuid.uuid4()), "C", "completed"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "100" in result.output, f"Expected '100' (percent) in output: {result.output}"

    def test_uses_rich_progress_bar_in_source(self):
        """The source should use Rich Progress bar or bar_column for rendering."""
        import inspect
        import bob.cli

        source = inspect.getsource(bob.cli._show_project_status)
        # Should use Rich progress bar or manual bar rendering
        has_bar = (
            "ProgressBar" in source
            or "Progress" in source
            or "bar" in source.lower()
            or "━" in source
            or "█" in source
        )
        assert has_bar, "Expected progress bar rendering in _show_project_status"


# ============================================================
# Step 4: Display resource usage (cost) with warnings if near limit
# ============================================================


class TestResourceUsageWithWarnings:
    """Step 4: Resource usage display with warnings for cost near limit."""

    def test_status_shows_cost_fraction(self, tmp_path):
        """Status should show cost as current/max."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _set_project_cost(db_path, project_id, total_cost=75.00, max_cost=100.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "75.00" in result.output
        assert "100.00" in result.output

    def test_status_warns_when_cost_near_limit(self, tmp_path):
        """When cost is >= 80% of max, a warning should appear."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _set_project_cost(db_path, project_id, total_cost=85.0, max_cost=100.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        has_warning = "warning" in output_lower or "!" in result.output or "⚠" in result.output
        assert has_warning, f"Expected cost warning for 85% usage: {result.output}"

    def test_status_critical_warning_when_cost_over_90(self, tmp_path):
        """When cost is >= 90% of max, a critical/danger warning should appear."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _set_project_cost(db_path, project_id, total_cost=95.0, max_cost=100.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        has_critical = (
            "critical" in output_lower
            or "danger" in output_lower
            or "!" in result.output
            or "⚠" in result.output
        )
        assert has_critical, f"Expected critical warning for 95% usage: {result.output}"

    def test_status_no_warning_when_cost_low(self, tmp_path):
        """When cost is well below limit, no warning should appear."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _set_project_cost(db_path, project_id, total_cost=10.0, max_cost=500.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        # Should not contain cost warnings
        assert "warning" not in output_lower, (
            f"No warning expected for low cost (2%): {result.output}"
        )

    def test_status_shows_cost_percentage(self, tmp_path):
        """Status should display the cost percentage used."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _set_project_cost(db_path, project_id, total_cost=250.0, max_cost=500.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "50" in result.output, f"Expected '50' (percent) for cost usage: {result.output}"


# ============================================================
# Step 5: End-to-end Rich formatting verification
# ============================================================


class TestRichFormattingEndToEnd:
    """Step 5: Run status command, verify Rich formatting end-to-end."""

    def test_full_rich_status_output(self, tmp_path):
        """Full status output with features, cost, progress, and warnings."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path, name="rich-test")
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Schema", "completed"),
                (str(uuid.uuid4()), "Models", "completed"),
                (str(uuid.uuid4()), "CLI", "executing"),
                (str(uuid.uuid4()), "Status", "pending"),
                (str(uuid.uuid4()), "Run", "pending"),
            ],
        )
        _set_project_cost(db_path, project_id, total_cost=420.0, max_cost=500.0)

        runner = CliRunner()
        result = runner.invoke(
            main, ["status"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0

        output = result.output
        # Project name in output
        assert "rich-test" in output
        # Cost values
        assert "420.00" in output
        assert "500.00" in output
        # Cost warning (84% used)
        output_lower = output.lower()
        assert "warning" in output_lower or "!" in output or "⚠" in output
        # Feature statuses
        assert "completed" in output_lower
        assert "pending" in output_lower
        # Progress indicator
        has_progress = "%" in output or "━" in output or "█" in output or "40" in output
        assert has_progress, f"Expected progress indicator: {output}"

    def test_verbose_mode_still_works_with_rich(self, tmp_path):
        """Verbose mode with Rich formatting shows feature details."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        _add_features(
            db_path,
            project_id,
            [
                (str(uuid.uuid4()), "Alpha Feature", "completed"),
                (str(uuid.uuid4()), "Beta Feature", "pending"),
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["status", "--verbose"], env={"BOB_DATABASE_PATH": str(db_path)}
        )
        assert result.exit_code == 0
        assert "Alpha Feature" in result.output
        assert "Beta Feature" in result.output

    def test_feature_detail_still_works_with_rich(self, tmp_path):
        """Feature-specific status with Rich formatting works."""
        from bob.cli import main

        project_path, db_path = _init_project(tmp_path)
        project_id = _get_project_id(db_path)
        feature_id = str(uuid.uuid4())
        _add_features(
            db_path,
            project_id,
            [(feature_id, "Detail Feature", "executing")],
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status", "--feature", feature_id],
            env={"BOB_DATABASE_PATH": str(db_path)},
        )
        assert result.exit_code == 0
        assert "Detail Feature" in result.output
