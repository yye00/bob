"""Tests for F110: End-to-end test - Feature generation workflow.

E2E integration test that exercises the complete generate-features workflow:

Step 1: Create test fixtures (spec YAML, mock PDF)
Step 2: Run generate-features command
Step 3: Verify output YAML structure
Step 4: Run plan command with generated features.yaml
Step 5: Verify features in database
"""

import json
import pathlib
import textwrap
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from bob3.cli import main
from bob3.db import (
    create_project,
    get_feature_dependencies,
    init_database,
    list_features,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "bob3.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path), \
         patch("bob3.cli.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def spec_file(tmp_path):
    """Create a test spec YAML with a natural language project description."""
    spec_content = textwrap.dedent("""\
        name: weather-dashboard
        version: "1.0.0"
        description: |
          A weather dashboard application that displays current conditions
          and forecasts for multiple cities. It should have a REST API backend
          with database storage, a web frontend, user authentication, and
          support for weather alerts.
        tech_stack:
          backend: Python/FastAPI
          frontend: React
          database: PostgreSQL
    """)
    spec_path = tmp_path / "weather_spec.yaml"
    spec_path.write_text(spec_content)
    return spec_path


@pytest.fixture
def mock_pdf(tmp_path):
    """Create a mock PDF file path for reference documents."""
    pdf_path = tmp_path / "requirements.pdf"
    # We don't create a real PDF; we mock the extraction
    return pdf_path


@pytest.fixture
def generated_features():
    """The features that the mocked sub-agent will return."""
    return [
        {
            "name": "Database Schema",
            "description": "Create PostgreSQL database schema with tables for cities, weather data, users, and alerts",
            "priority": 10,
            "acceptance_criteria": [
                "Cities table with name, latitude, longitude",
                "Weather data table with temperature, humidity, conditions",
                "Users table with authentication fields",
                "Alerts table with thresholds and notification preferences",
            ],
        },
        {
            "name": "REST API Backend",
            "description": "FastAPI backend with endpoints for weather data, user management, and alerts",
            "priority": 20,
            "acceptance_criteria": [
                "GET /api/weather/{city} returns current conditions",
                "GET /api/forecast/{city} returns 5-day forecast",
                "POST /api/users for registration",
                "POST /api/alerts for alert configuration",
            ],
            "depends_on": ["Database Schema"],
        },
        {
            "name": "User Authentication",
            "description": "JWT-based authentication with login, registration, and token refresh",
            "priority": 30,
            "acceptance_criteria": [
                "Users can register with email and password",
                "Users can login and receive JWT token",
                "Protected endpoints require valid JWT",
            ],
            "depends_on": ["Database Schema"],
        },
        {
            "name": "Weather Alerts",
            "description": "Configurable weather alert system with threshold-based notifications",
            "priority": 40,
            "acceptance_criteria": [
                "Users can set temperature thresholds",
                "System checks thresholds on weather updates",
                "Alerts are delivered via configured channels",
            ],
            "depends_on": ["REST API Backend", "User Authentication"],
        },
        {
            "name": "React Frontend",
            "description": "React-based dashboard showing weather data, forecasts, and alert management",
            "priority": 50,
            "acceptance_criteria": [
                "Dashboard displays current weather for selected cities",
                "Forecast view shows 5-day predictions",
                "Alert management UI for configuring thresholds",
                "Login and registration forms",
            ],
            "depends_on": ["REST API Backend", "User Authentication"],
        },
    ]


# ============================================================
# Step 1: Create test fixtures (spec, mock PDF)
# ============================================================


class TestCreateTestFixtures:
    """Step 1: Create test fixtures (spec, mock PDF)."""

    def test_spec_file_is_valid_yaml(self, spec_file):
        """The test spec file is valid YAML with expected fields."""
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        assert spec["name"] == "weather-dashboard"
        assert spec["version"] == "1.0.0"
        assert "description" in spec
        assert "weather" in spec["description"].lower()

    def test_spec_file_has_natural_language_description(self, spec_file):
        """The spec contains a natural language project description."""
        with open(spec_file) as f:
            spec = yaml.safe_load(f)

        description = spec["description"]
        assert len(description) > 50, "Description should be substantive"
        assert "REST API" in description or "api" in description.lower()
        assert "frontend" in description.lower() or "web" in description.lower()

    def test_mock_pdf_path_exists_as_fixture(self, mock_pdf):
        """The mock PDF path fixture is a Path object."""
        assert isinstance(mock_pdf, pathlib.Path)
        assert mock_pdf.name.endswith(".pdf")


# ============================================================
# Step 2: Run generate-features command
# ============================================================


class TestRunGenerateFeatures:
    """Step 2: Run generate-features command."""

    def test_generate_features_runs_successfully(
        self, spec_file, tmp_path, generated_features
    ):
        """generate-features command completes without error."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            result = runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0, f"generate-features failed: {result.output}"
        assert "5" in result.output, (
            f"Should show 5 features generated: {result.output}"
        )

    def test_generate_features_with_pdf_refs(
        self, spec_file, mock_pdf, tmp_path, generated_features
    ):
        """generate-features with --refs extracts PDF content and includes it."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        mock_pdf_content = MagicMock(
            text="Requirements: The system must support 100 concurrent users.",
            pages=["Requirements: The system must support 100 concurrent users."],
            metadata={"page_count": 1},
        )

        with patch("bob3.cli._run_generate_features") as mock_gen, \
             patch("bob3.cli.extract_pdf_text") as mock_extract:
            mock_gen.return_value = generated_features
            mock_extract.return_value = mock_pdf_content
            result = runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--refs",
                    str(mock_pdf),
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0, f"generate-features with refs failed: {result.output}"
        # The extract_pdf_text should have been called with the PDF path
        mock_extract.assert_called_once()
        # _run_generate_features should have been called with ref_texts
        mock_gen.assert_called_once()
        call_args = mock_gen.call_args
        ref_texts = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("ref_texts")
        assert ref_texts is not None, "ref_texts should be passed to _run_generate_features"

    def test_generate_features_creates_output_file(
        self, spec_file, tmp_path, generated_features
    ):
        """generate-features creates the output YAML file."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        assert output_file.exists(), "Output features.yaml should be created"

    def test_generate_features_displays_feature_table(
        self, spec_file, tmp_path, generated_features
    ):
        """generate-features displays a summary table of generated features."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            result = runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        assert result.exit_code == 0
        # Should display feature names in the table
        assert "Database Schema" in result.output
        assert "REST API Backend" in result.output


# ============================================================
# Step 3: Verify output YAML structure
# ============================================================


class TestVerifyOutputYAMLStructure:
    """Step 3: Verify output YAML structure."""

    def test_output_yaml_has_features_key(
        self, spec_file, tmp_path, generated_features
    ):
        """Output YAML file has a top-level 'features' key."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        written = yaml.safe_load(output_file.read_text())
        assert "features" in written, "Output must have 'features' key"

    def test_output_yaml_has_correct_feature_count(
        self, spec_file, tmp_path, generated_features
    ):
        """Output YAML contains the expected number of features."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        written = yaml.safe_load(output_file.read_text())
        assert len(written["features"]) == 5

    def test_output_yaml_features_have_required_fields(
        self, spec_file, tmp_path, generated_features
    ):
        """Each feature in output YAML has name, description, and priority."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        written = yaml.safe_load(output_file.read_text())
        for feat in written["features"]:
            assert "name" in feat, f"Feature missing 'name': {feat}"
            assert "description" in feat, f"Feature missing 'description': {feat}"
            assert "priority" in feat, f"Feature missing 'priority': {feat}"

    def test_output_yaml_features_have_acceptance_criteria(
        self, spec_file, tmp_path, generated_features
    ):
        """Features with acceptance_criteria have them preserved in output."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        written = yaml.safe_load(output_file.read_text())
        db_schema = written["features"][0]
        assert "acceptance_criteria" in db_schema
        assert isinstance(db_schema["acceptance_criteria"], list)
        assert len(db_schema["acceptance_criteria"]) >= 1

    def test_output_yaml_features_have_dependencies(
        self, spec_file, tmp_path, generated_features
    ):
        """Features with depends_on have dependencies preserved in output."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        written = yaml.safe_load(output_file.read_text())
        # REST API Backend depends on Database Schema
        api_feat = written["features"][1]
        assert "depends_on" in api_feat
        assert "Database Schema" in api_feat["depends_on"]

    def test_output_yaml_is_valid_for_plan_command(
        self, spec_file, tmp_path, generated_features
    ):
        """Output YAML is valid input for the plan command."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        # Now use the generated features.yaml as input to the plan command
        result = runner.invoke(main, ["plan", str(output_file)])
        assert result.exit_code == 0, f"plan command failed on generated YAML: {result.output}"
        assert "5" in result.output, (
            f"plan should show 5 features: {result.output}"
        )


# ============================================================
# Step 4: Run plan command with generated features
# ============================================================


class TestRunPlanCommand:
    """Step 4: Run plan command with generated features.yaml."""

    def test_plan_shows_generated_features(
        self, spec_file, tmp_path, generated_features
    ):
        """plan command displays all features from the generated YAML."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                ],
            )

        result = runner.invoke(main, ["plan", str(output_file)])
        assert result.exit_code == 0
        assert "Database Schema" in result.output
        assert "REST API Backend" in result.output
        assert "User Authentication" in result.output
        assert "Weather Alerts" in result.output
        assert "React Frontend" in result.output

    def test_plan_create_inserts_features_into_db(
        self, tmp_db, spec_file, tmp_path, generated_features
    ):
        """plan --create inserts generated features into the database."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Create a project first
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            # Step 1: Generate features
            with patch("bob3.cli._run_generate_features") as mock_gen:
                mock_gen.return_value = generated_features
                result = runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--output",
                        str(output_file),
                    ],
                )
            assert result.exit_code == 0

            # Step 2: Plan with --create
            result = runner.invoke(
                main, ["plan", str(output_file), "--create"]
            )
            assert result.exit_code == 0
            assert "Created 5 features" in result.output

    def test_plan_create_preserves_priorities(
        self, tmp_db, spec_file, tmp_path, generated_features
    ):
        """plan --create preserves feature priorities from generated YAML."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            with patch("bob3.cli._run_generate_features") as mock_gen:
                mock_gen.return_value = generated_features
                runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--output",
                        str(output_file),
                    ],
                )

            runner.invoke(main, ["plan", str(output_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}
            assert by_name["Database Schema"].priority == 10
            assert by_name["REST API Backend"].priority == 20
            assert by_name["User Authentication"].priority == 30
            assert by_name["Weather Alerts"].priority == 40
            assert by_name["React Frontend"].priority == 50


# ============================================================
# Step 5: Verify features in database
# ============================================================


class TestVerifyFeaturesInDatabase:
    """Step 5: Verify features in database after full workflow."""

    def test_all_five_features_in_database(
        self, tmp_db, spec_file, tmp_path, generated_features
    ):
        """All 5 generated features are persisted in the database."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            with patch("bob3.cli._run_generate_features") as mock_gen:
                mock_gen.return_value = generated_features
                runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--output",
                        str(output_file),
                    ],
                )

            runner.invoke(main, ["plan", str(output_file), "--create"])

            features = list_features(project_id=project.id)
            assert len(features) == 5

            names = {f.name for f in features}
            assert names == {
                "Database Schema",
                "REST API Backend",
                "User Authentication",
                "Weather Alerts",
                "React Frontend",
            }

    def test_acceptance_criteria_stored_correctly(
        self, tmp_db, spec_file, tmp_path, generated_features
    ):
        """Acceptance criteria are stored as JSON in the database."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            with patch("bob3.cli._run_generate_features") as mock_gen:
                mock_gen.return_value = generated_features
                runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--output",
                        str(output_file),
                    ],
                )

            runner.invoke(main, ["plan", str(output_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            # Database Schema should have 4 acceptance criteria
            db_feature = by_name["Database Schema"]
            assert db_feature.acceptance_criteria is not None
            criteria = json.loads(db_feature.acceptance_criteria)
            assert len(criteria) == 4
            assert "Cities table" in criteria[0]

    def test_dependencies_created_correctly(
        self, tmp_db, spec_file, tmp_path, generated_features
    ):
        """Feature dependencies are correctly stored in the database."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            with patch("bob3.cli._run_generate_features") as mock_gen:
                mock_gen.return_value = generated_features
                runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--output",
                        str(output_file),
                    ],
                )

            runner.invoke(main, ["plan", str(output_file), "--create"])

            features = list_features(project_id=project.id)
            by_name = {f.name: f for f in features}

            # Database Schema has no dependencies
            deps = get_feature_dependencies(by_name["Database Schema"].id)
            assert len(deps) == 0

            # REST API Backend depends on Database Schema
            deps = get_feature_dependencies(by_name["REST API Backend"].id)
            assert len(deps) == 1
            assert deps[0].depends_on_feature_id == by_name["Database Schema"].id

            # User Authentication depends on Database Schema
            deps = get_feature_dependencies(by_name["User Authentication"].id)
            assert len(deps) == 1
            assert deps[0].depends_on_feature_id == by_name["Database Schema"].id

            # Weather Alerts depends on REST API Backend and User Authentication
            deps = get_feature_dependencies(by_name["Weather Alerts"].id)
            assert len(deps) == 2
            dep_ids = {d.depends_on_feature_id for d in deps}
            assert by_name["REST API Backend"].id in dep_ids
            assert by_name["User Authentication"].id in dep_ids

            # React Frontend depends on REST API Backend and User Authentication
            deps = get_feature_dependencies(by_name["React Frontend"].id)
            assert len(deps) == 2
            dep_ids = {d.depends_on_feature_id for d in deps}
            assert by_name["REST API Backend"].id in dep_ids
            assert by_name["User Authentication"].id in dep_ids

    def test_features_ordered_by_priority(
        self, tmp_db, spec_file, tmp_path, generated_features
    ):
        """Features in the database are returned ordered by priority."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            with patch("bob3.cli._run_generate_features") as mock_gen:
                mock_gen.return_value = generated_features
                runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--output",
                        str(output_file),
                    ],
                )

            runner.invoke(main, ["plan", str(output_file), "--create"])

            features = list_features(project_id=project.id)
            names = [f.name for f in features]
            assert names == [
                "Database Schema",
                "REST API Backend",
                "User Authentication",
                "Weather Alerts",
                "React Frontend",
            ]


# ============================================================
# Full end-to-end integration
# ============================================================


class TestFullE2EWorkflow:
    """Complete end-to-end: spec -> generate-features -> plan --create -> verify DB."""

    def test_complete_workflow(
        self, tmp_db, tmp_path, generated_features
    ):
        """Full workflow from spec creation through DB verification."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # Step 1: Create project
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            # Step 1: Create spec file
            spec_content = textwrap.dedent("""\
                name: weather-dashboard
                version: "1.0.0"
                description: |
                  A weather dashboard application that displays current conditions
                  and forecasts. Needs REST API, database, auth, alerts, frontend.
            """)
            spec_file = tmp_path / "spec.yaml"
            spec_file.write_text(spec_content)

            # Step 2: Run generate-features
            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            with patch("bob3.cli._run_generate_features") as mock_gen:
                mock_gen.return_value = generated_features
                result = runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--output",
                        str(output_file),
                    ],
                )
            assert result.exit_code == 0, f"generate-features failed: {result.output}"

            # Step 3: Verify output YAML
            assert output_file.exists()
            written = yaml.safe_load(output_file.read_text())
            assert "features" in written
            assert len(written["features"]) == 5

            # Step 4: Run plan --create
            result = runner.invoke(
                main, ["plan", str(output_file), "--create"]
            )
            assert result.exit_code == 0, f"plan --create failed: {result.output}"
            assert "Created 5 features" in result.output

            # Step 5: Verify all features in database
            features = list_features(project_id=project.id)
            assert len(features) == 5

            by_name = {f.name: f for f in features}
            expected_names = {
                "Database Schema",
                "REST API Backend",
                "User Authentication",
                "Weather Alerts",
                "React Frontend",
            }
            assert set(by_name.keys()) == expected_names

            # Verify priorities are correct
            assert by_name["Database Schema"].priority == 10
            assert by_name["React Frontend"].priority == 50

            # Verify acceptance criteria are stored
            for feature in features:
                if feature.name == "Database Schema":
                    criteria = json.loads(feature.acceptance_criteria)
                    assert len(criteria) == 4

            # Verify dependency graph
            # Weather Alerts -> [REST API Backend, User Authentication]
            deps = get_feature_dependencies(by_name["Weather Alerts"].id)
            dep_ids = {d.depends_on_feature_id for d in deps}
            assert by_name["REST API Backend"].id in dep_ids
            assert by_name["User Authentication"].id in dep_ids

    def test_complete_workflow_with_pdf_refs(
        self, tmp_db, tmp_path, generated_features
    ):
        """Full workflow including PDF reference document extraction."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="weather-dashboard",
                workspace_path=str(tmp_path / "workspace"),
            )

            spec_content = textwrap.dedent("""\
                name: weather-dashboard
                version: "1.0.0"
                description: A weather dashboard application.
            """)
            spec_file = tmp_path / "spec.yaml"
            spec_file.write_text(spec_content)

            pdf_path = tmp_path / "requirements.pdf"
            output_file = tmp_path / "features.yaml"
            runner = CliRunner()

            mock_pdf_content = MagicMock(
                text="System requirements: Must support real-time data updates.",
                pages=["System requirements: Must support real-time data updates."],
                metadata={"page_count": 1},
            )

            with patch("bob3.cli._run_generate_features") as mock_gen, \
                 patch("bob3.cli.extract_pdf_text") as mock_extract:
                mock_gen.return_value = generated_features
                mock_extract.return_value = mock_pdf_content

                result = runner.invoke(
                    main,
                    [
                        "generate-features",
                        str(spec_file),
                        "--refs",
                        str(pdf_path),
                        "--output",
                        str(output_file),
                    ],
                )

            assert result.exit_code == 0, f"generate-features with refs failed: {result.output}"
            assert output_file.exists()

            # Run plan --create
            result = runner.invoke(
                main, ["plan", str(output_file), "--create"]
            )
            assert result.exit_code == 0

            # Verify features in DB
            features = list_features(project_id=project.id)
            assert len(features) == 5

    def test_auto_continue_flag_in_workflow(
        self, spec_file, tmp_path, generated_features
    ):
        """Workflow with --auto-continue flag shows appropriate message."""
        output_file = tmp_path / "features.yaml"
        runner = CliRunner()

        with patch("bob3.cli._run_generate_features") as mock_gen:
            mock_gen.return_value = generated_features
            result = runner.invoke(
                main,
                [
                    "generate-features",
                    str(spec_file),
                    "--output",
                    str(output_file),
                    "--auto-continue",
                ],
            )

        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "auto" in result.output.lower() or "plan" in result.output.lower()
