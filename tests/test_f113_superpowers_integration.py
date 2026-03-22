"""Tests for F113: Superpowers Full Integration.

Validates that all four Superpowers skills are properly integrated:

Step 1: TDD mode added to feature execution (tests written first)
Step 2: Verification-before-completion checklist runs on feature completion
Step 3: Sub-agent driven development option for complex features
Step 4: All skills documented in orientation prompt
Step 5: Execute feature with TDD mode, verify tests-first prompt present
Step 6: Complete feature, verify verification checklist runs
"""

import asyncio
import json
import pathlib
import textwrap
from unittest.mock import patch

import pytest

from bob3 import db
from bob3.models import Feature


SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Set up an isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project():
    """Create a test project."""
    return db.create_project(
        name="Superpowers Integration Test",
        workspace_path="/tmp/test-superpowers",
    )


@pytest.fixture()
def feature_with_criteria(project):
    """Create a feature with acceptance criteria (should trigger TDD)."""
    return db.create_feature(
        project_id=project.id,
        name="Feature With Criteria",
        description="Implement a new validation module",
        acceptance_criteria=json.dumps([
            "Step 1: Create validation module",
            "Step 2: Add input validation functions",
            "Step 3: Write unit tests",
        ]),
    )


@pytest.fixture()
def simple_feature(project):
    """Create a simple feature without criteria (may not trigger TDD)."""
    return db.create_feature(
        project_id=project.id,
        name="Config Update",
        description="Update config file",
    )


@pytest.fixture()
def complex_feature(project):
    """Create a complex feature that should trigger sub-agent mode."""
    return db.create_feature(
        project_id=project.id,
        name="Complex Feature",
        description="Build a comprehensive reporting system",
        acceptance_criteria=json.dumps([
            "Step 1: Create data models",
            "Step 2: Add aggregation queries",
            "Step 3: Build report generator",
            "Step 4: Add export to PDF",
            "Step 5: Write integration tests",
        ]),
    )


@pytest.fixture()
def workspace_with_files(tmp_path):
    """Create a workspace with src and test files for verification testing."""
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)

    # Create a real source file (no stubs)
    (src_dir / "__init__.py").write_text("")
    (src_dir / "example.py").write_text(textwrap.dedent("""\
        def add(a, b):
            return a + b

        def multiply(a, b):
            return a * b
    """))

    # Create a test file with real assertions
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_example.py").write_text(textwrap.dedent("""\
        from unittest.mock import patch
        from bob3.example import add, multiply

        def test_add():
            assert add(2, 3) == 5

        def test_multiply():
            assert multiply(4, 5) == 20
    """))

    return tmp_path


@pytest.fixture()
def workspace_with_stubs(tmp_path):
    """Create a workspace with stub functions for verification failure testing."""
    src_dir = tmp_path / "src" / "bob3"
    src_dir.mkdir(parents=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True)

    (src_dir / "__init__.py").write_text("")
    (src_dir / "stub_module.py").write_text(textwrap.dedent("""\
        def real_function():
            return 42

        def stub_function():
            pass

        def another_stub():
            raise NotImplementedError
    """))

    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_stub.py").write_text(textwrap.dedent("""\
        def test_placeholder():
            assert True
    """))

    return tmp_path


# ===================================================================
# Step 1: TDD mode in feature execution
# ===================================================================


class TestTddMode:
    """Step 1: TDD mode is added to feature execution with tests-first approach."""

    def test_tdd_prompt_contains_red_green_refactor(self):
        """TDD prompt includes the red-green-refactor cycle."""
        from bob3.superpowers import get_tdd_prompt

        prompt = get_tdd_prompt()
        assert "RED" in prompt
        assert "GREEN" in prompt
        assert "REFACTOR" in prompt

    def test_tdd_prompt_instructs_tests_first(self):
        """TDD prompt instructs writing tests BEFORE implementation."""
        from bob3.superpowers import get_tdd_prompt

        prompt = get_tdd_prompt()
        assert "Write Failing Tests First" in prompt
        assert "BEFORE" in prompt or "before" in prompt.lower()

    def test_tdd_prompt_instructs_confirm_failure(self):
        """TDD prompt instructs confirming tests fail first (red phase)."""
        from bob3.superpowers import get_tdd_prompt

        prompt = get_tdd_prompt()
        assert "FAIL" in prompt or "fail" in prompt.lower()

    def test_should_use_tdd_with_acceptance_criteria(self):
        """Features with acceptance criteria should use TDD."""
        from bob3.superpowers import should_use_tdd

        result = should_use_tdd(
            acceptance_criteria=json.dumps(["Step 1: Do this", "Step 2: Do that"]),
        )
        assert result is True

    def test_should_use_tdd_with_implementation_description(self):
        """Features with implementation-related descriptions should use TDD."""
        from bob3.superpowers import should_use_tdd

        result = should_use_tdd(description="Implement a new data validation module")
        assert result is True

    def test_should_not_use_tdd_for_config_only(self):
        """Config-only features without criteria should not trigger TDD."""
        from bob3.superpowers import should_use_tdd

        result = should_use_tdd(description="update")
        assert result is False

    def test_should_use_tdd_with_test_keyword(self):
        """Features mentioning tests should use TDD."""
        from bob3.superpowers import should_use_tdd

        result = should_use_tdd(description="Write comprehensive test suite")
        assert result is True

    def test_tdd_rules_section_present(self):
        """TDD prompt includes clear rules about test-first approach."""
        from bob3.superpowers import get_tdd_prompt

        prompt = get_tdd_prompt()
        assert "NEVER write implementation code before" in prompt


# ===================================================================
# Step 2: Verification-before-completion checklist
# ===================================================================


class TestVerificationChecklist:
    """Step 2: Verification-before-completion checklist runs on feature completion."""

    def test_verification_prompt_contains_all_checks(self):
        """Verification prompt lists all required checks."""
        from bob3.superpowers import get_verification_prompt

        prompt = get_verification_prompt()
        assert "Files exist" in prompt
        assert "No stubs" in prompt
        assert "No mocks in production" in prompt
        assert "Tests pass" in prompt
        assert "Real tests" in prompt

    def test_verification_checklist_passes_clean_workspace(self, workspace_with_files):
        """Verification passes on a clean workspace with real code."""
        from bob3.superpowers import run_verification_checklist

        result = run_verification_checklist(workspace=str(workspace_with_files))
        assert result["passed"] is True
        assert len(result["checks"]) >= 4
        for check in result["checks"]:
            assert check["passed"] is True

    def test_verification_checklist_detects_stubs(self, workspace_with_stubs):
        """Verification fails when source files contain stub functions."""
        from bob3.superpowers import run_verification_checklist

        result = run_verification_checklist(workspace=str(workspace_with_stubs))
        assert result["passed"] is False
        # The no_stubs_in_source check should fail
        stub_check = next(
            c for c in result["checks"] if c["name"] == "no_stubs_in_source"
        )
        assert stub_check["passed"] is False
        assert "stub" in stub_check["details"].lower()

    def test_verification_checklist_returns_summary(self, workspace_with_files):
        """Verification returns a human-readable summary."""
        from bob3.superpowers import run_verification_checklist

        result = run_verification_checklist(workspace=str(workspace_with_files))
        assert "summary" in result
        assert "Verification checklist" in result["summary"]

    def test_verification_checklist_handles_empty_workspace(self, tmp_path):
        """Verification handles a workspace with no src or test files.

        When no project type is detected, source_files_exist and
        code_changes_made are treated as warnings (non-fatal), so the
        overall result still passes.
        """
        from bob3.superpowers import run_verification_checklist

        result = run_verification_checklist(workspace=str(tmp_path))
        # Overall passes because unknown-project-type checks are warnings
        assert result["passed"] is True
        # The individual source check still reports not-passed
        src_check = next(
            c for c in result["checks"] if c["name"] == "source_files_exist"
        )
        assert src_check["passed"] is False
        assert src_check.get("severity") == "warning"

    def test_verification_result_structure(self, workspace_with_files):
        """Verification result has the expected structure."""
        from bob3.superpowers import run_verification_checklist

        result = run_verification_checklist(workspace=str(workspace_with_files))
        assert "passed" in result
        assert "checks" in result
        assert "summary" in result
        assert isinstance(result["passed"], bool)
        assert isinstance(result["checks"], list)
        assert isinstance(result["summary"], str)
        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "details" in check


# ===================================================================
# Step 3: Sub-agent driven development for complex features
# ===================================================================


class TestSubagentDrivenDevelopment:
    """Step 3: Sub-agent driven development option for complex features."""

    def test_subagent_prompt_contains_guidelines(self):
        """Sub-agent prompt includes guidelines for parallel work."""
        from bob3.superpowers import get_subagent_prompt

        prompt = get_subagent_prompt()
        assert "independent" in prompt.lower()
        assert "parallel" in prompt.lower()

    def test_should_use_subagents_with_many_criteria(self):
        """Features with 3+ acceptance criteria should use sub-agents."""
        from bob3.superpowers import should_use_subagents

        criteria = json.dumps(["Step 1", "Step 2", "Step 3"])
        result = should_use_subagents(acceptance_criteria=criteria)
        assert result is True

    def test_should_not_use_subagents_with_few_criteria(self):
        """Features with fewer than 3 criteria should not use sub-agents."""
        from bob3.superpowers import should_use_subagents

        criteria = json.dumps(["Step 1", "Step 2"])
        result = should_use_subagents(acceptance_criteria=criteria)
        assert result is False

    def test_should_use_subagents_with_many_files(self):
        """Features touching 5+ files should use sub-agents."""
        from bob3.superpowers import should_use_subagents

        result = should_use_subagents(estimated_files_touched=5)
        assert result is True

    def test_should_not_use_subagents_with_few_files(self):
        """Features touching fewer than 5 files should not use sub-agents."""
        from bob3.superpowers import should_use_subagents

        result = should_use_subagents(estimated_files_touched=3)
        assert result is False

    def test_should_use_subagents_with_high_complexity(self):
        """Features with complexity >= 8 should use sub-agents."""
        from bob3.superpowers import should_use_subagents

        result = should_use_subagents(estimated_complexity=8)
        assert result is True

    def test_should_not_use_subagents_with_low_complexity(self):
        """Features with complexity < 8 should not use sub-agents."""
        from bob3.superpowers import should_use_subagents

        result = should_use_subagents(estimated_complexity=5)
        assert result is False

    def test_should_not_use_subagents_with_no_info(self):
        """Features with no criteria or estimates should not use sub-agents."""
        from bob3.superpowers import should_use_subagents

        result = should_use_subagents()
        assert result is False


# ===================================================================
# Step 4: Skills documented in orientation prompt
# ===================================================================


class TestOrientationDocumentation:
    """Step 4: All four skills documented in orientation prompt."""

    def test_orientation_documents_systematic_debugging(self):
        """Orientation includes systematic debugging skill documentation."""
        from bob3.superpowers import get_superpowers_orientation

        orientation = get_superpowers_orientation()
        assert "Systematic Debugging" in orientation
        assert "IRON LAW" in orientation
        assert "Phase 1" in orientation
        assert "Phase 2" in orientation
        assert "Phase 3" in orientation
        assert "Phase 4" in orientation

    def test_orientation_documents_tdd(self):
        """Orientation includes TDD skill documentation."""
        from bob3.superpowers import get_superpowers_orientation

        orientation = get_superpowers_orientation()
        assert "Test-Driven Development" in orientation
        assert "red-green-refactor" in orientation.lower()

    def test_orientation_documents_verification(self):
        """Orientation includes verification-before-completion documentation."""
        from bob3.superpowers import get_superpowers_orientation

        orientation = get_superpowers_orientation()
        assert "Verification Before Completion" in orientation
        assert "No stubs" in orientation

    def test_orientation_documents_subagent(self):
        """Orientation includes sub-agent driven development documentation."""
        from bob3.superpowers import get_superpowers_orientation

        orientation = get_superpowers_orientation()
        assert "Sub-Agent Driven Development" in orientation
        assert "parallel" in orientation.lower()

    def test_orientation_documents_when_to_use(self):
        """Orientation documents when to use each skill."""
        from bob3.superpowers import get_superpowers_orientation

        orientation = get_superpowers_orientation()
        assert "When to use" in orientation

    def test_wrap_prompt_includes_superpowers_orientation(self):
        """wrap_prompt_with_orientation includes Superpowers skills documentation."""
        from bob3.orientation import wrap_prompt_with_orientation

        result = wrap_prompt_with_orientation(
            prompt="Test prompt",
            feature_id="F999",
            workspace="/tmp/test",
            feature_name="Test",
            feature_description="A test feature",
        )
        assert "Superpowers Skills Available" in result
        assert "Systematic Debugging" in result
        assert "Test-Driven Development" in result
        assert "Verification Before Completion" in result
        assert "Sub-Agent Driven Development" in result

    def test_wrap_prompt_includes_tdd_when_enabled(self):
        """wrap_prompt_with_orientation includes TDD section when enabled."""
        from bob3.orientation import wrap_prompt_with_orientation

        result = wrap_prompt_with_orientation(
            prompt="Test prompt",
            feature_id="F999",
            workspace="/tmp/test",
            enable_tdd=True,
        )
        assert "TDD Mode" in result
        assert "Write Failing Tests First" in result

    def test_wrap_prompt_excludes_tdd_when_disabled(self):
        """wrap_prompt_with_orientation excludes TDD section when disabled."""
        from bob3.orientation import wrap_prompt_with_orientation

        result = wrap_prompt_with_orientation(
            prompt="Test prompt",
            feature_id="F999",
            workspace="/tmp/test",
            enable_tdd=False,
        )
        assert "TDD Mode: Write Tests BEFORE" not in result

    def test_wrap_prompt_includes_verification_by_default(self):
        """wrap_prompt_with_orientation includes verification by default."""
        from bob3.orientation import wrap_prompt_with_orientation

        result = wrap_prompt_with_orientation(
            prompt="Test prompt",
            feature_id="F999",
            workspace="/tmp/test",
        )
        assert "Verification Before Completion Checklist" in result

    def test_wrap_prompt_includes_subagent_when_enabled(self):
        """wrap_prompt_with_orientation includes sub-agent section when enabled."""
        from bob3.orientation import wrap_prompt_with_orientation

        result = wrap_prompt_with_orientation(
            prompt="Test prompt",
            feature_id="F999",
            workspace="/tmp/test",
            enable_subagent=True,
        )
        assert "Sub-Agent Driven Development" in result
        assert "independent tasks" in result.lower()


# ===================================================================
# Step 5: Execute feature with TDD mode
# ===================================================================


class TestTddModeInExecution:
    """Step 5: Execute feature with TDD mode, verify tests-first prompt present."""

    @pytest.mark.asyncio
    async def test_execute_feature_with_tdd_prompt(self, project, feature_with_criteria):
        """Feature with acceptance criteria gets TDD prompt in execution."""
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        captured_prompt = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_prompt["prompt"] = prompt
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=5,
                session_id="tdd-test",
                total_cost_usd=0.50,
                usage=None,
                result=None,
            )

        # Set feature to ready so it can be executed
        db.update_feature(
            feature_with_criteria.id,
            status="ready",
            readiness_score=0.85,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )

        loop = OrchestrationLoop(
            project_id=project.id,
            workspace="/tmp/test-tdd",
        )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            feature = db.get_feature(feature_with_criteria.id)
            await loop.execute_feature(feature)

        # Verify TDD instructions are in the prompt
        prompt_text = captured_prompt["prompt"]
        assert "TDD Mode" in prompt_text
        assert "Write Failing Tests First" in prompt_text

    @pytest.mark.asyncio
    async def test_execute_feature_without_tdd_for_simple_feature(self, project, simple_feature):
        """Simple feature without criteria does not get TDD prompt."""
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        captured_prompt = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_prompt["prompt"] = prompt
            yield ResultMessage(
                subtype="success",
                duration_ms=2000,
                duration_api_ms=1500,
                is_error=False,
                num_turns=3,
                session_id="no-tdd",
                total_cost_usd=0.20,
                usage=None,
                result=None,
            )

        db.update_feature(
            simple_feature.id,
            status="ready",
            readiness_score=0.85,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )

        loop = OrchestrationLoop(
            project_id=project.id,
            workspace="/tmp/test-no-tdd",
        )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            feature = db.get_feature(simple_feature.id)
            await loop.execute_feature(feature)

        prompt_text = captured_prompt["prompt"]
        # TDD-specific prompt section should NOT be present (but orientation docs will mention TDD)
        assert "TDD Mode: Write Tests BEFORE" not in prompt_text

    @pytest.mark.asyncio
    async def test_execute_complex_feature_gets_subagent_prompt(self, project, complex_feature):
        """Complex feature with many criteria gets sub-agent prompt."""
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        captured_prompt = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_prompt["prompt"] = prompt
            yield ResultMessage(
                subtype="success",
                duration_ms=10000,
                duration_api_ms=8000,
                is_error=False,
                num_turns=10,
                session_id="subagent-test",
                total_cost_usd=1.00,
                usage=None,
                result=None,
            )

        db.update_feature(
            complex_feature.id,
            status="ready",
            readiness_score=0.85,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )

        loop = OrchestrationLoop(
            project_id=project.id,
            workspace="/tmp/test-subagent",
        )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            feature = db.get_feature(complex_feature.id)
            await loop.execute_feature(feature)

        prompt_text = captured_prompt["prompt"]
        # Should have sub-agent driven development section
        assert "Sub-Agent Driven Development" in prompt_text
        assert "independent tasks" in prompt_text.lower() or "independent" in prompt_text.lower()


# ===================================================================
# Step 6: Verification checklist runs on feature completion
# ===================================================================


class TestVerificationOnCompletion:
    """Step 6: Complete feature, verify verification checklist runs."""

    @pytest.mark.asyncio
    async def test_verification_evidence_created_on_success(self, project, feature_with_criteria):
        """Successful execution creates verification checklist evidence."""
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success",
                duration_ms=5000,
                duration_api_ms=4000,
                is_error=False,
                num_turns=5,
                session_id="verify-test",
                total_cost_usd=0.50,
                usage=None,
                result=None,
            )

        db.update_feature(
            feature_with_criteria.id,
            status="ready",
            readiness_score=0.85,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )

        # Use a real workspace with files for verification
        import tempfile
        with tempfile.TemporaryDirectory() as ws:
            src_dir = pathlib.Path(ws) / "src" / "bob3"
            src_dir.mkdir(parents=True)
            tests_dir = pathlib.Path(ws) / "tests"
            tests_dir.mkdir(parents=True)

            (src_dir / "__init__.py").write_text("")
            (src_dir / "module.py").write_text("def func():\n    return 42\n")
            (tests_dir / "__init__.py").write_text("")
            (tests_dir / "test_module.py").write_text(
                "def test_func():\n    assert True\n"
            )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=ws,
            )

            with patch("bob3.orchestrator.claude_executor.query", mock_query):
                feature = db.get_feature(feature_with_criteria.id)
                await loop.execute_feature(feature)

        # Check that verification evidence was created
        evidence_list = db.query_evidence(project_id=project.id)
        verification_evidence = [
            e for e in evidence_list if e.type == "verification_checklist"
        ]
        assert len(verification_evidence) >= 1

        # Parse and check the verification content
        content = json.loads(verification_evidence[0].content)
        assert "passed" in content
        assert "checks" in content
        assert "summary" in content

    @pytest.mark.asyncio
    async def test_verification_not_run_on_failure(self, project, feature_with_criteria):
        """Verification checklist should NOT run when execution fails."""
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="error",
                duration_ms=2000,
                duration_api_ms=1500,
                is_error=True,
                num_turns=1,
                session_id="fail-test",
                total_cost_usd=0.10,
                usage=None,
                result="Execution failed",
            )

        db.update_feature(
            feature_with_criteria.id,
            status="ready",
            readiness_score=0.85,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )

        loop = OrchestrationLoop(
            project_id=project.id,
            workspace="/tmp/test-no-verify",
        )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            feature = db.get_feature(feature_with_criteria.id)
            await loop.execute_feature(feature)

        # On failure, there should be no verification_checklist evidence
        evidence_list = db.query_evidence(project_id=project.id)
        verification_evidence = [
            e for e in evidence_list if e.type == "verification_checklist"
        ]
        assert len(verification_evidence) == 0

    @pytest.mark.asyncio
    async def test_all_prompts_include_verification_section(self, project, feature_with_criteria):
        """All feature execution prompts include the verification checklist section."""
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        captured_prompt = {}

        async def mock_query(*, prompt, options=None, transport=None):
            captured_prompt["prompt"] = prompt
            yield ResultMessage(
                subtype="success",
                duration_ms=3000,
                duration_api_ms=2000,
                is_error=False,
                num_turns=3,
                session_id="verify-prompt",
                total_cost_usd=0.30,
                usage=None,
                result=None,
            )

        db.update_feature(
            feature_with_criteria.id,
            status="ready",
            readiness_score=0.85,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )

        loop = OrchestrationLoop(
            project_id=project.id,
            workspace="/tmp/test-verify-prompt",
        )

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            feature = db.get_feature(feature_with_criteria.id)
            await loop.execute_feature(feature)

        prompt_text = captured_prompt["prompt"]
        assert "Verification Before Completion Checklist" in prompt_text


# ===================================================================
# Build superpowers prompt combination tests
# ===================================================================


class TestBuildSuperpowersPrompt:
    """Test the combined superpowers prompt builder."""

    def test_all_skills_combined(self):
        """Enabling all skills combines their prompts."""
        from bob3.superpowers import build_superpowers_prompt

        result = build_superpowers_prompt(
            enable_tdd=True,
            enable_verification=True,
            enable_subagent=True,
        )
        assert "TDD Mode" in result
        assert "Verification Before Completion" in result
        assert "Sub-Agent Driven Development" in result

    def test_only_verification(self):
        """Enabling only verification produces just that section."""
        from bob3.superpowers import build_superpowers_prompt

        result = build_superpowers_prompt(
            enable_tdd=False,
            enable_verification=True,
            enable_subagent=False,
        )
        assert "Verification Before Completion" in result
        assert "TDD Mode" not in result
        assert "Sub-Agent Driven Development" not in result

    def test_no_skills_returns_empty(self):
        """Disabling all skills returns empty string."""
        from bob3.superpowers import build_superpowers_prompt

        result = build_superpowers_prompt(
            enable_tdd=False,
            enable_verification=False,
            enable_subagent=False,
        )
        assert result == ""

    def test_tdd_and_verification(self):
        """TDD + verification is the common combination for new features."""
        from bob3.superpowers import build_superpowers_prompt

        result = build_superpowers_prompt(
            enable_tdd=True,
            enable_verification=True,
            enable_subagent=False,
        )
        assert "TDD Mode" in result
        assert "Verification Before Completion" in result
        assert "Sub-Agent Driven Development" not in result


# ===================================================================
# No forbidden patterns
# ===================================================================


class TestNoForbiddenPatterns:
    """Ensure superpowers module follows Bob3 conventions."""

    def test_no_subprocess_in_superpowers(self):
        """No subprocess calls in superpowers.py."""
        source_path = SRC_DIR / "bob3" / "superpowers.py"
        source = source_path.read_text()
        forbidden = ["subprocess", "os.system(", "os.popen(", "Popen("]
        for pattern in forbidden:
            assert pattern not in source, (
                f"Found forbidden '{pattern}' in superpowers.py"
            )

    def test_no_anthropic_import_in_superpowers(self):
        """No direct anthropic SDK import in superpowers.py."""
        source_path = SRC_DIR / "bob3" / "superpowers.py"
        source = source_path.read_text()
        assert "from anthropic" not in source
        assert "import anthropic" not in source

    def test_superpowers_module_exists(self):
        """The superpowers.py module exists in the package."""
        source_path = SRC_DIR / "bob3" / "superpowers.py"
        assert source_path.exists()

    def test_run_loop_imports_superpowers(self):
        """run_loop.py imports from superpowers module."""
        run_loop_path = SRC_DIR / "bob3" / "orchestrator" / "run_loop.py"
        source = run_loop_path.read_text()
        assert "from bob3.superpowers import" in source
