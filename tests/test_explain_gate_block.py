"""Tests for bob.enhanced_verification.explain_gate_block and the CLI command.

Acceptance criteria:
  - CLI command: bob explain-gate-block
  - Function defined: bob.enhanced_verification.explain_gate_block
  - File exists: src/bob/enhanced_verification.py
  - pytest: tests/test_explain_gate_block.py
  - integration: bob.cli
"""

from __future__ import annotations

import json
import uuid

import pytest
from click.testing import CliRunner

from bob.cli import main
from bob.enhanced_verification import explain_gate_block


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def low_score_acs():
    """ACs that will score below the 0.85 threshold."""
    return [
        "The system works correctly",
        "All cases are handled",
    ]


@pytest.fixture()
def high_score_acs():
    """ACs that will score above the 0.85 threshold."""
    return [
        "File exists: src/bob/enhanced_verification.py",
        "Function defined: bob.enhanced_verification.explain_gate_block",
        "pytest: tests/test_explain_gate_block.py",
        "integration: bob.cli",
    ]


# ---------------------------------------------------------------------------
# explain_gate_block function tests
# ---------------------------------------------------------------------------

class TestExplainGateBlock:
    def test_returns_dict_with_required_keys(self, low_score_acs):
        result = explain_gate_block(
            feature_id="test-id-001",
            feature_name="Test Feature",
            description="A test feature",
            acceptance_criteria=low_score_acs,
        )
        assert isinstance(result, dict)
        assert "feature_id" in result
        assert "feature_name" in result
        assert "score" in result
        assert "threshold" in result
        assert "components" in result
        assert "remediation_hints" in result

    def test_score_is_float_in_range(self, low_score_acs):
        result = explain_gate_block(
            feature_id="test-id-002",
            feature_name="Test Feature",
            description=None,
            acceptance_criteria=low_score_acs,
        )
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0

    def test_threshold_is_085_by_default(self, low_score_acs):
        result = explain_gate_block(
            feature_id="test-id-003",
            feature_name="Test Feature",
            description=None,
            acceptance_criteria=low_score_acs,
        )
        assert result["threshold"] == 0.85

    def test_components_has_all_four_sub_dimensions(self, low_score_acs):
        result = explain_gate_block(
            feature_id="test-id-004",
            feature_name="Test Feature",
            description=None,
            acceptance_criteria=low_score_acs,
        )
        components = result["components"]
        assert "ambiguity_score" in components
        assert "reachability_score" in components
        assert "ears_score" in components
        assert "ac_coverage_score" in components

    def test_component_scores_are_floats_in_range(self, low_score_acs):
        result = explain_gate_block(
            feature_id="test-id-005",
            feature_name="Test Feature",
            description=None,
            acceptance_criteria=low_score_acs,
        )
        for key, val in result["components"].items():
            assert isinstance(val, float), f"{key} should be float"
            assert 0.0 <= val <= 1.0, f"{key}={val} out of range"

    def test_low_score_acs_produce_remediation_hints(self, low_score_acs):
        result = explain_gate_block(
            feature_id="test-id-006",
            feature_name="Vague Feature",
            description=None,
            acceptance_criteria=low_score_acs,
        )
        assert isinstance(result["remediation_hints"], list)
        assert len(result["remediation_hints"]) > 0

    def test_high_score_acs_may_have_empty_hints(self, high_score_acs):
        result = explain_gate_block(
            feature_id="test-id-007",
            feature_name="Good Feature",
            description="Feature with structured ACs",
            acceptance_criteria=high_score_acs,
        )
        # Score should be high enough; hints may still contain some, but
        # crucially the function should work without errors.
        assert result["score"] > 0.0

    def test_feature_id_and_name_passed_through(self):
        fid = "abc-123"
        fname = "My Test Feature"
        result = explain_gate_block(
            feature_id=fid,
            feature_name=fname,
            description=None,
            acceptance_criteria=["File exists: src/foo.py"],
        )
        assert result["feature_id"] == fid
        assert result["feature_name"] == fname

    def test_accepts_json_encoded_ac_list(self):
        acs = json.dumps(["File exists: src/bob/enhanced_verification.py"])
        result = explain_gate_block(
            feature_id="test-json-001",
            feature_name="JSON ACs Feature",
            description=None,
            acceptance_criteria=acs,
        )
        assert isinstance(result["score"], float)

    def test_empty_acs_produce_zero_score(self):
        result = explain_gate_block(
            feature_id="test-empty-001",
            feature_name="Empty ACs Feature",
            description=None,
            acceptance_criteria=[],
        )
        assert result["score"] == 0.0


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------

class TestExplainGateBlockCLI:
    def _make_temp_db(self, tmp_path, acs, feature_name="Test Feature", description="A test"):
        """Create a temporary bob.db with one feature for testing."""
        import os
        import sys
        sys.path.insert(0, str(tmp_path))

        db_path = tmp_path / "bob.db"
        import sqlite3
        import pathlib

        # Use the schema from the real project
        schema_path = pathlib.Path(__file__).parent.parent / "src" / "bob" / "schema.sql"
        schema = schema_path.read_text()
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema)

        project_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO projects (id, name, workspace_path, status) VALUES (?, ?, ?, ?)",
            (project_id, "Test Project", str(tmp_path), "planning"),
        )

        feature_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO features
               (id, project_id, name, description, acceptance_criteria, status,
                decomposition_depth, priority, risk_category,
                conf_spec_understanding, conf_impl_correctness, conf_test_adequacy,
                readiness_score, refinement_attempts, max_refinement_attempts,
                tasks_completed, tasks_total, permanent_forward_carry, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (feature_id, project_id, feature_name, description,
             json.dumps(acs), "pending",
             0, 100, "medium",
             0.0, 0.0, 0.0,
             0.0, 0, 3, 0, 0, 0),
        )
        conn.commit()
        conn.close()
        return db_path, feature_id

    def test_cli_command_exists(self, runner):
        result = runner.invoke(main, ["explain-gate-block", "--help"])
        assert result.exit_code == 0
        assert "explain-gate-block" in result.output.lower() or "gate" in result.output.lower()

    def test_cli_text_output_contains_score(self, runner, tmp_path):
        low_acs = ["The system works correctly", "All cases are handled"]
        db_path, fid = self._make_temp_db(tmp_path, low_acs)

        result = runner.invoke(main, ["explain-gate-block", fid[:8]], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code == 0, result.output
        assert "Score" in result.output or "score" in result.output

    def test_cli_text_output_contains_threshold(self, runner, tmp_path):
        low_acs = ["The system works correctly", "All cases are handled"]
        db_path, fid = self._make_temp_db(tmp_path, low_acs)

        result = runner.invoke(main, ["explain-gate-block", fid[:8]], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code == 0, result.output
        assert "0.85" in result.output or "threshold" in result.output.lower()

    def test_cli_text_output_contains_components(self, runner, tmp_path):
        low_acs = ["The system works correctly", "All cases are handled"]
        db_path, fid = self._make_temp_db(tmp_path, low_acs)

        result = runner.invoke(main, ["explain-gate-block", fid[:8]], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code == 0, result.output
        # Should show sub-dimension breakdown
        assert any(kw in result.output for kw in [
            "ambiguity", "reachability", "ears", "ac_coverage"
        ])

    def test_cli_json_flag_returns_json(self, runner, tmp_path):
        low_acs = ["The system works correctly", "All cases are handled"]
        db_path, fid = self._make_temp_db(tmp_path, low_acs)

        result = runner.invoke(main, ["explain-gate-block", "--json", fid[:8]], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "feature_id" in data
        assert "score" in data
        assert "components" in data
        assert "remediation_hints" in data

    def test_cli_json_contains_all_required_keys(self, runner, tmp_path):
        low_acs = ["The system works correctly"]
        db_path, fid = self._make_temp_db(tmp_path, low_acs)

        result = runner.invoke(main, ["explain-gate-block", "--json", fid[:8]], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "feature_id" in data
        assert "feature_name" in data
        assert "score" in data
        assert "threshold" in data
        components = data["components"]
        assert "ambiguity_score" in components
        assert "reachability_score" in components
        assert "ears_score" in components
        assert "ac_coverage_score" in components

    def test_cli_prefix_lookup_works(self, runner, tmp_path):
        """Feature ID prefix (first 8 chars) should resolve to full feature."""
        low_acs = ["The system works correctly"]
        db_path, fid = self._make_temp_db(tmp_path, low_acs, feature_name="Prefix Test Feature")

        result = runner.invoke(main, ["explain-gate-block", "--json", fid[:8]], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["feature_id"] == fid
        assert data["feature_name"] == "Prefix Test Feature"

    def test_cli_full_id_lookup_works(self, runner, tmp_path):
        """Full feature ID should also resolve."""
        low_acs = ["File exists: src/foo.py"]
        db_path, fid = self._make_temp_db(tmp_path, low_acs, feature_name="Full ID Feature")

        result = runner.invoke(main, ["explain-gate-block", "--json", fid], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["feature_id"] == fid

    def test_cli_not_found_exits_nonzero(self, runner, tmp_path):
        """Unknown feature ID prefix should exit with error."""
        db_path = tmp_path / "bob.db"
        import sqlite3, pathlib
        schema_path = pathlib.Path(__file__).parent.parent / "src" / "bob" / "schema.sql"
        schema = schema_path.read_text()
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema)
        conn.commit()
        conn.close()

        result = runner.invoke(main, ["explain-gate-block", "nonexist"], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code != 0

    def test_cli_ambiguous_prefix_exits_nonzero(self, runner, tmp_path):
        """Ambiguous prefix (matches multiple features) should exit with error."""
        import sqlite3, pathlib
        db_path = tmp_path / "bob.db"
        schema_path = pathlib.Path(__file__).parent.parent / "src" / "bob" / "schema.sql"
        schema = schema_path.read_text()
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema)

        project_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO projects (id, name, workspace_path, status) VALUES (?, ?, ?, ?)",
            (project_id, "Test Project", str(tmp_path), "planning"),
        )
        for i in range(2):
            fid = f"aaaaaaaa-0000-0000-0000-{i:012d}"
            conn.execute(
                """INSERT INTO features
                   (id, project_id, name, description, acceptance_criteria, status,
                    decomposition_depth, priority, risk_category,
                    conf_spec_understanding, conf_impl_correctness, conf_test_adequacy,
                    readiness_score, refinement_attempts, max_refinement_attempts,
                    tasks_completed, tasks_total, permanent_forward_carry, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (fid, project_id, f"Feature {i}", "desc",
                 json.dumps(["File exists: src/foo.py"]), "pending",
                 0, 100, "medium", 0.0, 0.0, 0.0, 0.0, 0, 3, 0, 0, 0),
            )
        conn.commit()
        conn.close()

        result = runner.invoke(main, ["explain-gate-block", "aaaaaaaa"], env={
            "BOB_DATABASE_PATH": str(db_path),
        })
        assert result.exit_code != 0
