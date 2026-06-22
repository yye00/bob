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
import os
import pathlib
import signal
import subprocess
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
    """Create a workspace with src and test files for verification testing.

    Tests in this workspace are self-contained -- they don't import from
    the workspace's src/ tree (which wouldn't be on sys.path under the
    bob3 verifier's pytest invocation anyway). This way the verifier's
    auto-run of pytest succeeds.
    """
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

    # Create a test file with real assertions. We use the unittest.mock
    # import so the test still exercises the patterns the verifier expects
    # in test files, but the assertions are self-contained so pytest can
    # run them without configuring sys.path for the workspace.
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_example.py").write_text(textwrap.dedent("""\
        from unittest.mock import patch  # noqa: F401

        def add(a, b):
            return a + b

        def multiply(a, b):
            return a * b

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
    async def test_verification_evidence_created_on_success(self, project):
        """Successful execution creates verification checklist evidence.

        Uses a freshly-created feature WITHOUT acceptance criteria so
        the verifier's ``acceptance_criteria_met`` check is skipped (it
        only runs when ``acceptance_criteria`` is provided). The
        previous version of this test used ``feature_with_criteria``,
        whose criteria ("Step 1: Create validation module", ...) are
        not satisfiable by the synthetic workspace below — so
        verification reported ``passed=False`` and the test only
        green-passed because it didn't ASSERT ``passed`` was True.

        This rewrite tests the actual contract: on a clean workspace
        with real source + real tests and no extraneous criteria,
        verification MUST report ``passed=True`` with a non-empty
        summary.
        """
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        # Create a feature WITHOUT acceptance_criteria to keep the
        # acceptance_criteria_met verifier path out of the picture.
        feature = db.create_feature(
            project_id=project.id,
            name="Verification-success feature",
            description="Implement a small utility",
        )

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
            feature.id,
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
            # Use a function with a non-trivial body so the AST
            # stub-detector does not flag it as a heuristic stub
            # (single ``return <literal>`` triggers a warning even
            # though warnings don't fail ``passed``; using a real
            # body is the safer assertion).
            (src_dir / "module.py").write_text(
                "def add(a, b):\n"
                "    total = a + b\n"
                "    if total < 0:\n"
                "        return 0\n"
                "    return total\n"
            )
            (tests_dir / "__init__.py").write_text("")
            (tests_dir / "test_module.py").write_text(
                "def test_func():\n    assert True\n"
            )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=ws,
            )

            with patch("bob3.orchestrator.claude_executor.query", mock_query):
                feat_db = db.get_feature(feature.id)
                await loop.execute_feature(feat_db)

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
        # Successful execution against a workspace with real source +
        # real test files MUST result in ``passed=True`` and a
        # non-empty human-readable summary. Without these assertions
        # the test green-passes even when verification silently
        # reports ``passed=False`` — the exact false-confidence the
        # adversarial-review-cycle test-fidelity finding called out.
        assert content["passed"] is True, (
            f"Verification should pass on a clean workspace; "
            f"summary was: {content.get('summary')!r}"
        )
        assert content["summary"], (
            "Verification summary must be non-empty for downstream "
            "rendering / human review"
        )

    @pytest.mark.asyncio
    async def test_verification_runs_on_failure_to_check_for_prior_work(
        self, project, feature_with_criteria
    ):
        """R10-014: Verification IS run when the sub-agent reports
        ``is_error=True`` because the workspace may already contain
        correct work from a prior attempt. The feature stays not-completed
        when verification fails (this test exercises the failure path),
        but the verification evidence MUST be recorded so the operator
        can see what the verifier found.
        """
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

        # R10-014: verification now runs on failure too, so the evidence
        # IS produced. The feature is not promoted to 'completed' because
        # the verification fails substantively (acceptance criteria not
        # met) — the failure path still applies.
        evidence_list = db.query_evidence(project_id=project.id)
        verification_evidence = [
            e for e in evidence_list if e.type == "verification_checklist"
        ]
        assert len(verification_evidence) == 1, (
            "R10-014: verification runs even on sub-agent error so the "
            "operator can see whether the workspace already has the work; "
            "evidence must be recorded."
        )
        # Feature is NOT completed (verification failed substantively).
        updated = db.get_feature(feature_with_criteria.id)
        assert updated.status != "completed"

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
# Bug 2: A crash in run_verification_checklist must NOT silently
# promote the feature to 'completed'
# ===================================================================


class TestVerificationCrashIsHardFailure:
    """If run_verification_checklist raises, the feature must be marked
    needs_human (not completed) and dependents must NOT cascade to ready.
    """

    @pytest.mark.asyncio
    async def test_verification_exception_marks_feature_needs_human(
        self, project, feature_with_criteria
    ):
        """Bug 2 regression: an exception in verification means hard fail.

        Set up a sub-agent that succeeds, but make
        run_verification_checklist raise. The feature must end up in
        'needs_human', NOT 'completed'.
        """
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=2,
                session_id="verify-crash",
                total_cost_usd=0.10,
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

        # Workspace must be set so that verification is attempted.
        loop = OrchestrationLoop(
            project_id=project.id,
            workspace="/tmp/test-verify-crash",
        )

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated pytest crash")

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            with patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_boom,
            ):
                feature = db.get_feature(feature_with_criteria.id)
                await loop.execute_feature(feature)

        updated = db.get_feature(feature_with_criteria.id)
        assert updated.status == "needs_human", (
            f"Verification crash must NOT silently mark the feature "
            f"completed; got status={updated.status}"
        )

    @pytest.mark.asyncio
    async def test_verification_exception_does_not_cascade_dependents(
        self, project
    ):
        """Bug 2 regression: a verification crash must not unlock dependents.

        Build A -> B (B depends on A). Verification crashes for A; A goes
        to needs_human. B must remain pending (NOT promoted to ready).
        """
        from bob3.orchestrator.run_loop import OrchestrationLoop
        from claude_code_sdk import ResultMessage

        feat_a = db.create_feature(
            project_id=project.id,
            name="Feature A",
            description="A — its verification will crash",
            acceptance_criteria=json.dumps(["Step 1: do thing"]),
        )
        feat_b = db.create_feature(
            project_id=project.id,
            name="Feature B",
            description="B — must NOT cascade to ready",
        )
        db.update_feature(
            feat_a.id,
            status="ready",
            readiness_score=0.85,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )
        db.update_feature(feat_b.id, status="pending", readiness_score=0.85)
        db.add_feature_dependency(
            feature_id=feat_b.id, depends_on_feature_id=feat_a.id
        )

        async def mock_query(*, prompt, options=None, transport=None):
            yield ResultMessage(
                subtype="success",
                duration_ms=1000,
                duration_api_ms=900,
                is_error=False,
                num_turns=2,
                session_id="cascade-test",
                total_cost_usd=0.10,
                usage=None,
                result=None,
            )

        loop = OrchestrationLoop(
            project_id=project.id,
            workspace="/tmp/test-cascade-crash",
        )

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated verification crash")

        with patch("bob3.orchestrator.claude_executor.query", mock_query):
            with patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                side_effect=_boom,
            ):
                a_loaded = db.get_feature(feat_a.id)
                await loop.execute_feature(a_loaded)

        # A is needs_human (not completed).
        assert db.get_feature(feat_a.id).status == "needs_human"
        # B was not unlocked.
        assert db.get_feature(feat_b.id).status == "pending"


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
# Auto test-execution check (_check_tests_pass)
# ===================================================================


def _make_python_workspace(
    root: pathlib.Path,
    *,
    test_body: str | None = None,
    create_tests_dir: bool = True,
) -> pathlib.Path:
    """Build a minimal Python workspace under ``root`` for tests_pass tests.

    By default writes one passing test (``assert 1 + 1 == 2``). Callers can
    override the test body or skip the tests/ directory entirely.
    """
    src_dir = root / "src" / "demo"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    (src_dir / "core.py").write_text("def add(a, b):\n    return a + b\n")

    if create_tests_dir:
        tests_dir = root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "__init__.py").write_text("")
        if test_body is None:
            test_body = (
                "def test_passes():\n"
                "    assert 1 + 1 == 2\n"
            )
        (tests_dir / "test_smoke.py").write_text(test_body)
    return root


class TestTestsPassCheck:
    """Auto-discovery + execution check (`tests_pass`) inside the verifier."""

    def test_passing_workspace_check_passes(self, tmp_path):
        """Workspace with passing tests -> tests_pass check passes."""
        from bob3.superpowers import run_verification_checklist

        ws = _make_python_workspace(tmp_path)
        result = run_verification_checklist(workspace=str(ws))

        tests_check = next(
            c for c in result["checks"] if c["name"] == "tests_pass"
        )
        assert tests_check["passed"] is True
        assert tests_check.get("severity") != "warning"
        assert "passed" in tests_check["details"].lower()

    def test_failing_test_makes_check_fail_hard(self, tmp_path):
        """One failing test -> tests_pass is a hard error, not a warning."""
        from bob3.superpowers import run_verification_checklist

        ws = _make_python_workspace(
            tmp_path,
            test_body=(
                "def test_will_fail():\n"
                "    assert 1 == 2\n"
            ),
        )
        result = run_verification_checklist(workspace=str(ws))

        tests_check = next(
            c for c in result["checks"] if c["name"] == "tests_pass"
        )
        assert tests_check["passed"] is False
        assert tests_check.get("severity") == "error"
        # Failure count parsed from output
        assert "failed" in tests_check["details"].lower()
        # The overall verifier should fail because tests_pass is a hard error.
        assert result["passed"] is False

    def test_no_test_directory_is_warning(self, tmp_path):
        """Workspace without a tests/ dir -> warning, not error."""
        from bob3.superpowers import run_verification_checklist

        ws = _make_python_workspace(tmp_path, create_tests_dir=False)
        result = run_verification_checklist(workspace=str(ws))

        tests_check = next(
            c for c in result["checks"] if c["name"] == "tests_pass"
        )
        assert tests_check["passed"] is True
        assert tests_check.get("severity") == "warning"
        assert "no test directory" in tests_check["details"].lower()

    def test_empty_tests_directory_is_hard_failure(self, tmp_path):
        """tests/ dir exists but has no test files -> hard failure (no tests collected)."""
        from bob3.superpowers import run_verification_checklist

        # Build a Python workspace, then wipe the tests directory clean (keep
        # the directory but remove all collected test files, including
        # __init__.py to avoid pytest picking up nothing-but-init).
        ws = _make_python_workspace(tmp_path)
        tests_dir = ws / "tests"
        for f in tests_dir.iterdir():
            f.unlink()
        # Sanity: directory still exists and is empty.
        assert tests_dir.exists()
        assert not list(tests_dir.iterdir())

        result = run_verification_checklist(workspace=str(ws))
        tests_check = next(
            c for c in result["checks"] if c["name"] == "tests_pass"
        )
        # pytest exits with code 5 when no tests are collected; we treat
        # that as a hard failure (an agent claiming "complete" with zero
        # tests run is exactly what this check is meant to catch).
        assert tests_check["passed"] is False
        assert tests_check.get("severity") == "error"

    def test_non_python_workspace_is_warning(self, tmp_path):
        """Workspace without Python sources under src/ -> warning, not error."""
        from bob3.superpowers import run_verification_checklist

        # Build a CMake-style workspace -- no Python source files.
        (tmp_path / "CMakeLists.txt").write_text("project(demo)\n")
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.cpp").write_text("int main() { return 0; }\n")
        # Even with a tests/ dir, a non-Python project should be a warning.
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.cpp").write_text("int main() { return 0; }\n")

        result = run_verification_checklist(workspace=str(tmp_path))
        tests_check = next(
            c for c in result["checks"] if c["name"] == "tests_pass"
        )
        assert tests_check["passed"] is True
        assert tests_check.get("severity") == "warning"

    def test_timeout_fails_without_hanging_runner(self, tmp_path, monkeypatch):
        """A timed-out test must be killed (not orphaned) and verifier returns fast.

        Beyond just returning a "timed out" result, this test also verifies
        the spawned pytest process tree was actually killed -- we use an
        uncommon sleep duration as a unique marker so we can ``pgrep`` for
        leaked processes after the verifier returns. Without the
        process-group kill behavior, the inner ``time.sleep(31419)`` would
        survive the verifier returning.
        """
        import os as _os
        import time as _time
        from bob3.superpowers import run_verification_checklist

        if _os.name != "posix":
            pytest.skip("process-group kill / pgrep are POSIX-only")

        # Uncommon sleep duration so pgrep below cannot false-positive on
        # unrelated ``sleep N`` processes that happen to be running on the
        # host. Distinct from the ``31419`` marker used by the
        # ``TestGrandchildKillAndAnsiOutput`` test in this same file so the
        # two tests can't false-positive each other when run sequentially
        # if cleanup is racy.
        sleep_marker = "27182"
        ws = _make_python_workspace(
            tmp_path,
            test_body=(
                f"import time\n"
                f"def test_sleeps_forever():\n"
                f"    time.sleep({sleep_marker})\n"
            ),
        )
        # Override the configured timeout to 10s so the test runner doesn't
        # actually wait 5 minutes for the default. This also exercises the
        # BOB3_TEST_RUN_TIMEOUT env override path.
        monkeypatch.setenv("BOB3_TEST_RUN_TIMEOUT", "10")

        start = _time.monotonic()
        result = run_verification_checklist(workspace=str(ws))
        elapsed = _time.monotonic() - start

        # The full verifier must return well before the marker sleep
        # duration. Allow generous headroom for slow CI: 10s timeout +
        # ~30s of overhead.
        assert elapsed < 60, (
            f"Verifier did not honor pytest timeout (took {elapsed:.1f}s)"
        )
        tests_check = next(
            c for c in result["checks"] if c["name"] == "tests_pass"
        )
        assert tests_check["passed"] is False
        assert tests_check.get("severity") == "error"
        assert "timed out" in tests_check["details"].lower()

        # Verify the pytest subprocess (and its sleeping grandchild test
        # function) were actually killed -- not orphaned. If the
        # process-group kill machinery regresses we'd find a leaked
        # ``python ... -c`` running ``time.sleep(<marker>)`` here.
        # Give the OS a beat to reap killed processes.
        _time.sleep(0.5)
        try:
            check = subprocess.run(  # noqa: S603 - test-only
                ["pgrep", "-f", sleep_marker],
                capture_output=True,
                text=True,
                timeout=2,
            )
            leaked = check.stdout.strip()
            if leaked:
                # Best-effort cleanup so we don't leave a long sleep
                # running for hours on dev machines, then fail loudly.
                for pid_str in leaked.splitlines():
                    try:
                        os.kill(int(pid_str), signal.SIGKILL)
                    except (ProcessLookupError, ValueError, PermissionError):
                        pass
                pytest.fail(
                    f"pytest subprocess sleeping for {sleep_marker}s was "
                    f"orphaned, not killed: leaked pids={leaked!r}"
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # pgrep not available -- skip the leak check rather than fail.
            pass

    def test_check_returns_warning_when_workspace_missing(self, tmp_path):
        """Pointing the verifier at a nonexistent path doesn't crash."""
        from bob3.superpowers import _check_tests_pass

        missing = tmp_path / "does_not_exist"
        result = _check_tests_pass(missing, "src", "tests")
        assert result["name"] == "tests_pass"
        assert result["passed"] is True
        assert result.get("severity") == "warning"


# ===================================================================
# Grandchild-kill + ANSI-output regression tests
# ===================================================================


class TestGrandchildKillAndAnsiOutput:
    """Regressions for two long-standing verifier hang/parse bugs.

    Bug 1: ``subprocess.run(..., timeout=...)`` only kills the direct child.
    A test that does ``subprocess.Popen(["sleep", "30"])`` causes the
    grandchild to inherit the stdout/stderr pipes -- the verifier's
    ``communicate()`` then blocks forever waiting for EOF on those pipes
    even after the timeout fires. We fix this by launching pytest in a new
    process group and SIGKILLing the whole group on timeout.

    Bug 2: ANSI color escapes (FORCE_COLOR=1, PY_COLORS=1, pytest-sugar,
    etc.) emit codes like ``\\x1b[32m5 passed\\x1b[0m`` that break the
    ``\\d+\\s+passed`` regex in ``_parse_pytest_counts``. We fix this by
    forcing ``--color=no`` on every pytest invocation in the verifier.
    """

    def test_subprocess_grandchild_does_not_hang_verifier(
        self, tmp_path, monkeypatch
    ):
        """A test that spawns a long-running grandchild does not hang the verifier.

        Runs the verifier with a 3-second timeout against a workspace whose
        single test passes immediately but spawns a ``sleep 30`` grandchild
        before returning. Without the process-group kill fix, the verifier
        would hang for the full 30 seconds because the grandchild keeps the
        inherited stdout/stderr pipes open. With the fix it returns within a
        handful of seconds.
        """
        import os as _os
        import time as _time

        if _os.name != "posix":
            pytest.skip("process-group kill is POSIX-only")

        # Use a unique sleep duration string so the leak check below can
        # distinguish OUR grandchild from any unrelated ``sleep 30`` /
        # ``sleep 60`` processes running on the host (e.g. shell watch
        # loops).
        sleep_marker = "31419"  # uncommon -- vanishingly unlikely to collide
        ws = _make_python_workspace(
            tmp_path,
            test_body=(
                f"import subprocess\n"
                f"import time\n"
                f"def test_spawns_grandchild_then_hangs():\n"
                f"    # Spawn a long-running grandchild that INHERITS pytest's\n"
                f"    # stdout/stderr (no pipe redirection). The grandchild keeps\n"
                f"    # those pipe FDs open even after pytest exits, which is\n"
                f"    # exactly what makes communicate() block forever in\n"
                f"    # subprocess.run with timeout.\n"
                f"    subprocess.Popen(['sleep', '{sleep_marker}'])\n"
                f"    # Make pytest itself hang too so the timeout path fires.\n"
                f"    # Without this, pytest exits in <1s and the grandchild's\n"
                f"    # inherited FDs are the only thing keeping pipes open --\n"
                f"    # we still want to exercise the timeout/kill code path.\n"
                f"    time.sleep(120)\n"
                f"    assert True\n"
            ),
        )
        # 3-second pytest timeout. Grandchild sleeps 31419s, pytest sleeps 120s --
        # without the pgroup-kill fix, communicate() hangs at least until the
        # grandchild exits.
        monkeypatch.setenv("BOB3_TEST_RUN_TIMEOUT", "3")

        from bob3.superpowers import _check_tests_pass

        start = _time.monotonic()
        # Call the inner check directly so we measure only the pytest run,
        # not unrelated AST work.
        result = _check_tests_pass(ws, "src", "tests")
        elapsed = _time.monotonic() - start

        # With the pgroup-kill fix: ~3s timeout + ~5s drain = well under 20s.
        # Without the fix: at least 30s (until the grandchild exits) and
        # often 60s+ depending on plumbing.
        assert elapsed < 20, (
            f"verifier did not kill grandchild on timeout (took {elapsed:.1f}s)"
        )
        # We hit the timeout path: result should be a hard timeout failure.
        assert result["name"] == "tests_pass"
        assert result["passed"] is False
        assert result.get("severity") == "error"
        assert "timed out" in result["details"].lower()

        # Verify the sleep grandchild was actually killed (no leaked
        # processes). Give the OS a beat to reap, then check for our
        # unique sleep marker. Using a uncommon duration avoids false
        # positives from unrelated ``sleep N`` processes on the host.
        _time.sleep(0.5)
        try:
            check = subprocess.run(  # noqa: S603 - test-only
                ["pgrep", "-f", f"^sleep {sleep_marker}$"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            # pgrep returns 1 (no match) on success-of-leak-check. Any
            # stdout content means our specific grandchild survived the
            # process-group kill.
            leaked = check.stdout.strip()
            if leaked:
                # Best-effort cleanup so we don't leave a 31419s sleep
                # running for hours on dev machines, then fail loudly.
                for pid_str in leaked.splitlines():
                    try:
                        os.kill(int(pid_str), signal.SIGKILL)
                    except (ProcessLookupError, ValueError, PermissionError):
                        pass
                pytest.fail(
                    f"sleep grandchild leaked after verifier returned: "
                    f"pids={leaked!r}"
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # pgrep not available -- skip the leak check rather than fail.
            pass

    def test_force_color_does_not_break_pass_parsing(self, tmp_path, monkeypatch):
        """FORCE_COLOR=1 in the env must not flip a passing run into a hard fail.

        Before the fix, pytest emits ANSI escape codes like
        ``\\x1b[32m5 passed\\x1b[0m``. The ``\\d+\\s+passed`` regex in
        ``_parse_pytest_counts`` requires whitespace between the digit and
        ``passed``, so the escape code in between makes the match fail and
        the verifier reports "no tests collected" -- a hard error.

        With ``--color=no`` forced on the pytest command, the output is
        plain text regardless of the env, and the regex matches.
        """
        ws = _make_python_workspace(tmp_path)  # one passing test
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.setenv("PY_COLORS", "1")

        from bob3.superpowers import _check_tests_pass

        result = _check_tests_pass(ws, "src", "tests")

        assert result["name"] == "tests_pass"
        assert result["passed"] is True, (
            f"FORCE_COLOR=1 broke pass parsing: details={result.get('details')!r}"
        )
        assert result.get("severity") != "warning"
        assert "passed" in result["details"].lower()


# ===================================================================
# Recursion guard: workspace == bob3 itself
# ===================================================================


class TestSelfTestRecursionGuard:
    """Bug 3: ``_check_tests_pass`` must skip when the workspace IS bob3."""

    def test_workspace_equal_to_bob3_src_is_skipped(self):
        """Running the verifier on bob3's own src tree returns a warning skip."""
        import bob3
        bob3_src_root = pathlib.Path(bob3.__file__).resolve().parents[1]

        from bob3.superpowers import _check_tests_pass

        result = _check_tests_pass(bob3_src_root, "bob3", "tests")
        assert result["name"] == "tests_pass"
        assert result["passed"] is True
        assert result.get("severity") == "warning"
        assert "recursion guard" in result["details"].lower()

    def test_workspace_inside_bob3_src_is_skipped(self):
        """A path inside bob3's src tree also triggers the guard."""
        import bob3
        bob3_pkg_dir = pathlib.Path(bob3.__file__).resolve().parent

        from bob3.superpowers import _check_tests_pass

        result = _check_tests_pass(bob3_pkg_dir, "src", "tests")
        assert result["name"] == "tests_pass"
        assert result["passed"] is True
        assert result.get("severity") == "warning"
        assert "recursion guard" in result["details"].lower()

    def test_workspace_at_bob3_repo_root_fires_guard(self):
        """Bug 4 (off-by-one): workspace at bob3 repo root must trip the guard.

        Previously the guard was anchored at ``parents[1]`` (``src/``), so
        passing the bob3 *repo root* (``parents[2]``) — which is NOT under
        ``src/`` — would NOT trigger the guard and the verifier would
        recursively run bob3's own pytest suite. Anchoring the guard at the
        repo root fixes that.
        """
        import bob3
        bob3_repo_root = pathlib.Path(bob3.__file__).resolve().parents[2]

        from bob3.superpowers import _check_tests_pass

        result = _check_tests_pass(bob3_repo_root, "src", "tests")
        assert result["name"] == "tests_pass"
        assert result["passed"] is True
        assert result.get("severity") == "warning"
        assert "recursion guard" in result["details"].lower()

    def test_workspace_at_bob3_src_subdirectory_fires_guard(self):
        """A real subdirectory of the bob3 repo (``<bob3>/src``) triggers the guard."""
        import bob3
        bob3_src_dir = pathlib.Path(bob3.__file__).resolve().parents[1]
        # Sanity: this is a real path on disk inside the repo.
        assert bob3_src_dir.is_dir()
        assert bob3_src_dir.name == "src"

        from bob3.superpowers import _check_tests_pass

        result = _check_tests_pass(bob3_src_dir, "bob3", "tests")
        assert result["name"] == "tests_pass"
        assert result["passed"] is True
        assert result.get("severity") == "warning"
        assert "recursion guard" in result["details"].lower()

    def test_unrelated_project_src_does_not_fire_guard(self, tmp_path):
        """An unrelated project whose workspace is its own ``src/`` must NOT be skipped.

        Previous off-by-one anchored the guard at bob3's ``src/``. Any
        workspace whose resolved path was an unrelated ``.../src`` would
        compare unequal to bob3's specific ``src/`` and not trip — that's
        fine — but the regression case it allowed was a workspace like
        ``<bob3>/src/another_thing/`` (a child of bob3's ``src/``) being
        treated as bob3 itself even when it was an unrelated nested
        project. We assert here that an unrelated workspace at
        ``<unrelated>/src/`` outside the bob3 repo does NOT fire the
        guard, regardless of being named ``src``.
        """
        # Build an unrelated project at <tmp>/unrelated_project with a real
        # src/ and a tiny passing test under tests/. _check_tests_pass on
        # the unrelated src/ must NOT short-circuit on the recursion guard;
        # since unrelated_src has no Python sources of its own under "src",
        # the natural exit is the "no Python source files" warning, NOT
        # the recursion-guard warning.
        unrelated = tmp_path / "unrelated_project"
        unrelated_src = unrelated / "src"
        unrelated_src.mkdir(parents=True)

        from bob3.superpowers import _check_tests_pass

        result = _check_tests_pass(unrelated_src, "src", "tests")
        assert result["name"] == "tests_pass"
        # Must not have hit the recursion guard.
        assert "recursion guard" not in result["details"].lower()


# ===================================================================
# No forbidden patterns
# ===================================================================


class TestNoForbiddenPatterns:
    """Ensure superpowers module follows Bob3 conventions."""

    def test_subprocess_use_in_superpowers_is_scoped(self):
        """Subprocess use in superpowers.py is scoped to the tests_pass check.

        Verification is allowed to invoke pytest as part of running the
        verification checklist (that's its job). The actual subprocess
        invocation now lives in the shared ``_run_with_pgroup_timeout``
        helper in ``enhanced_verification.py`` (which kills the entire
        process group on timeout so grandchildren can't hang the verifier
        via inherited stdout/stderr pipe FDs -- bpo-31935 / bpo-38207).
        ``superpowers.py`` only imports that helper; it must not contain any
        direct subprocess.run / Popen / os.system / shell=True calls of its
        own.
        """
        source_path = SRC_DIR / "bob3" / "superpowers.py"
        source = source_path.read_text()
        # These patterns are forbidden in superpowers.py -- the only
        # subprocess use must go through the shared helper.
        forbidden = [
            "os.system(",
            "os.popen(",
            "subprocess.Popen(",
            "subprocess.run(",
            "shell=True",
        ]
        for pattern in forbidden:
            assert pattern not in source, (
                f"Found forbidden '{pattern}' in superpowers.py"
            )
        # The shared helper must be imported (single source of truth).
        assert "_run_with_pgroup_timeout" in source, (
            "superpowers.py must use the shared "
            "_run_with_pgroup_timeout helper"
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


# ===================================================================
# R10-005: __init__.py is a real source file
# ===================================================================


class TestR10005InitPyIsSource:
    """R10-005: source_files_exist must include ``__init__.py``.

    Pre-fix bug: a feature whose acceptance criterion was
    ``"File exists: src/foo/__init__.py"`` had the agent correctly
    create the file, but the verifier filtered ``__init__.py`` out of
    the source-file count, returned 0 source files, FAILed the check,
    and the feature was wrongly marked ``needs_human``.
    """

    def test_package_only_workspace_passes_source_check(self, tmp_path):
        """A workspace whose only Python file is ``__init__.py`` (10 LOC
        of real code) must pass ``source_files_exist``.
        """
        from bob3.superpowers import run_verification_checklist

        src_dir = tmp_path / "src" / "calculator"
        src_dir.mkdir(parents=True)
        # 10 lines of real code in __init__.py — this IS the package.
        (src_dir / "__init__.py").write_text(textwrap.dedent("""\
            \"\"\"calculator package.\"\"\"

            def add(a, b):
                return a + b

            def subtract(a, b):
                return a - b

            def multiply(a, b):
                return a * b
        """))
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_basic.py").write_text(textwrap.dedent("""\
            def test_truth():
                assert True
        """))

        result = run_verification_checklist(workspace=str(tmp_path))
        src_check = next(
            c for c in result["checks"] if c["name"] == "source_files_exist"
        )
        assert src_check["passed"] is True, (
            f"source_files_exist must pass when only __init__.py is present, "
            f"got: {src_check}"
        )

    def test_empty_init_only_warns_does_not_fail(self, tmp_path):
        """A package whose only file is an EMPTY ``__init__.py`` still
        passes source_files_exist, but emits a ``package_has_substance``
        warning so a real implementation feature isn't masked.
        """
        from bob3.superpowers import run_verification_checklist

        src_dir = tmp_path / "src" / "stub_pkg"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_basic.py").write_text("def test_t(): assert True\n")

        result = run_verification_checklist(workspace=str(tmp_path))

        src_check = next(
            c for c in result["checks"] if c["name"] == "source_files_exist"
        )
        assert src_check["passed"] is True

        # The warning check should be present and FAIL with severity warning.
        substance_check = next(
            (c for c in result["checks"] if c["name"] == "package_has_substance"),
            None,
        )
        assert substance_check is not None, (
            "package_has_substance warning check must be present when "
            "only an empty __init__.py exists"
        )
        assert substance_check["passed"] is False
        assert substance_check.get("severity") == "warning"
        # Warnings must NOT cause overall failure.
        assert result["passed"] is True


class TestR10020ScaledTestRunTimeout:
    """R10-020: pytest timeout must scale with project test count.

    Regression: a fixed 300 s default rejected verifier-correct features on
    real V&V suites (swedish-circle) that legitimately take >5 minutes for
    the full suite. Failure mode: every acceptance criterion individually
    passes but the bundled tests_pass sub-check times out.
    """

    def test_count_tests_in_counts_def_test_lines(self, tmp_path):
        from bob3.superpowers import _count_tests_in

        td = tmp_path / "tests"
        td.mkdir()
        (td / "test_a.py").write_text(
            "def test_one():\n    pass\n"
            "def test_two():\n    pass\n"
            "async def test_three():\n    pass\n"
        )
        (td / "test_b.py").write_text(
            "class TestX:\n"
            "    def test_x_one(self):\n        pass\n"
            "    def test_x_two(self):\n        pass\n"
        )
        # Non-test file should be ignored.
        (td / "helper.py").write_text("def test_should_not_count():\n    pass\n")
        # __pycache__ should be skipped.
        cache = td / "__pycache__"
        cache.mkdir()
        (cache / "test_x.cpython.py").write_text("def test_pyc():\n    pass\n")

        assert _count_tests_in(td) == 5

    def test_count_tests_in_handles_missing_dir(self, tmp_path):
        from bob3.superpowers import _count_tests_in

        assert _count_tests_in(tmp_path / "nope") == 0

    def test_floor_when_target_dir_is_none(self, monkeypatch):
        from bob3.superpowers import _test_run_timeout, DEFAULT_TEST_RUN_TIMEOUT_S

        monkeypatch.delenv("BOB3_TEST_RUN_TIMEOUT", raising=False)
        monkeypatch.delenv("BOB3_TEST_RUN_PER_TEST_S", raising=False)
        monkeypatch.delenv("BOB3_TEST_RUN_CAP", raising=False)
        assert _test_run_timeout() == DEFAULT_TEST_RUN_TIMEOUT_S

    def test_explicit_env_override_wins(self, tmp_path, monkeypatch):
        from bob3.superpowers import _test_run_timeout

        td = tmp_path / "tests"
        td.mkdir()
        (td / "test_x.py").write_text(
            "\n".join(f"def test_{i}(): pass" for i in range(50)) + "\n"
        )
        monkeypatch.setenv("BOB3_TEST_RUN_TIMEOUT", "42")
        # Even with 50 tests, the verbatim override wins.
        assert _test_run_timeout(td) == 42

    def test_small_project_uses_floor(self, tmp_path, monkeypatch):
        from bob3.superpowers import _test_run_timeout, DEFAULT_TEST_RUN_TIMEOUT_S

        td = tmp_path / "tests"
        td.mkdir()
        (td / "test_x.py").write_text("def test_one(): pass\n")
        monkeypatch.delenv("BOB3_TEST_RUN_TIMEOUT", raising=False)
        monkeypatch.setenv("BOB3_TEST_RUN_PER_TEST_S", "60")
        monkeypatch.delenv("BOB3_TEST_RUN_CAP", raising=False)
        # 60 * 1 = 60s, far below the 300s floor.
        assert _test_run_timeout(td) == DEFAULT_TEST_RUN_TIMEOUT_S

    def test_medium_project_scales_above_floor(self, tmp_path, monkeypatch):
        from bob3.superpowers import _test_run_timeout

        td = tmp_path / "tests"
        td.mkdir()
        (td / "test_x.py").write_text(
            "\n".join(f"def test_{i}(): pass" for i in range(20)) + "\n"
        )
        monkeypatch.delenv("BOB3_TEST_RUN_TIMEOUT", raising=False)
        monkeypatch.setenv("BOB3_TEST_RUN_PER_TEST_S", "60")
        monkeypatch.setenv("BOB3_TEST_RUN_CAP", "3600")
        # 20 * 60 = 1200s -- between 300 floor and 3600 cap.
        assert _test_run_timeout(td) == 1200

    def test_huge_project_clamped_to_cap(self, tmp_path, monkeypatch):
        from bob3.superpowers import _test_run_timeout

        td = tmp_path / "tests"
        td.mkdir()
        (td / "test_x.py").write_text(
            "\n".join(f"def test_{i}(): pass" for i in range(500)) + "\n"
        )
        monkeypatch.delenv("BOB3_TEST_RUN_TIMEOUT", raising=False)
        monkeypatch.setenv("BOB3_TEST_RUN_PER_TEST_S", "60")
        monkeypatch.setenv("BOB3_TEST_RUN_CAP", "1800")
        # 500 * 60 = 30000s -- must be clamped to 1800s cap.
        assert _test_run_timeout(td) == 1800

    def test_invalid_env_override_falls_back_to_scaling(self, tmp_path, monkeypatch):
        from bob3.superpowers import _test_run_timeout

        td = tmp_path / "tests"
        td.mkdir()
        (td / "test_x.py").write_text(
            "\n".join(f"def test_{i}(): pass" for i in range(20)) + "\n"
        )
        # Garbage values must not crash and must fall through to scaling.
        monkeypatch.setenv("BOB3_TEST_RUN_TIMEOUT", "not-a-number")
        monkeypatch.setenv("BOB3_TEST_RUN_PER_TEST_S", "negative-please")
        monkeypatch.delenv("BOB3_TEST_RUN_CAP", raising=False)
        # Falls back to default per-test (60) * 20 = 1200s.
        assert _test_run_timeout(td) == 1200
