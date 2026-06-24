"""Round 0 Task 1 (Gap #1) — Independent Evaluator agent tests.

Covers Acceptance Criteria from
``docs/recursion/round0/PLAN.md`` Task 1:

- AC1: ``spawn_evaluator_agent`` is importable from
  ``bob.orchestrator.claude_executor``.
- AC2: ``EvaluatorVerdict`` is importable from ``bob.models`` and has the
  required fields with the right types/literals.
- AC3: ``spawn_evaluator_agent`` does NOT receive (and cannot use) the
  implementation agent's transcript or session id. Verified by inspecting
  the function signature/body and by exercising the prompt the spawn
  function builds.
- AC4: When the evaluator returns ``FAIL`` the orchestration loop files
  a finding to ``reviews/findings.yaml`` with ``tag="evaluator-rejection"``.
- AC5: ``adversarial-self-review`` is no longer installed by
  ``install_skills_to_workspace`` for an implementation workspace; it
  is only installed when the evaluator opts in via
  ``include_evaluator_skills=True``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bob import db
from bob.models import EvaluatorVerdict
from bob.orchestrator.claude_executor import (
    EVALUATOR_ALLOWED_TOOLS,
    EVALUATOR_DISALLOWED_TOOLS,
    EVALUATOR_SYSTEM_PROMPT,
    parse_evaluator_verdict,
    spawn_evaluator_agent,
)
from bob.skills_installer import (
    EVALUATOR_ONLY_SKILLS,
    install_skills_to_workspace,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _test_db(tmp_path, monkeypatch):
    """Isolated test database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project(tmp_path):
    """A test project with a workspace dir."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return db.create_project(
        name="Evaluator Project",
        workspace_path=str(workspace),
    )


@pytest.fixture()
def workspace(tmp_path):
    """A bare workspace directory (no git repo)."""
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


# ---------------------------------------------------------------------------
# AC1 + AC2: imports
# ---------------------------------------------------------------------------


class TestImportsAndVerdictSchema:
    """AC1 + AC2: spawn_evaluator_agent + EvaluatorVerdict are importable."""

    def test_spawn_evaluator_agent_importable(self):
        # Import again at function scope to assert AC1 directly even
        # when the module-level import has been monkeypatched.
        from bob.orchestrator.claude_executor import (  # noqa: F401
            spawn_evaluator_agent as _imported,
        )

        assert callable(_imported)

    def test_evaluator_verdict_importable_with_required_fields(self):
        from bob.models import EvaluatorVerdict as _Verdict

        # AC2: required fields with the right types
        fields = _Verdict.model_fields
        assert "verdict" in fields
        assert "findings" in fields
        assert "confidence" in fields
        assert "evidence" in fields

        # The verdict literal must accept exactly the three documented values.
        for value in ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE"):
            v = _Verdict(
                verdict=value,
                findings=["x"],
                confidence=0.5,
                evidence={"k": "v"},
            )
            assert v.verdict == value

    def test_evaluator_verdict_rejects_invalid_verdict(self):
        with pytest.raises(Exception):
            EvaluatorVerdict(verdict="MAYBE", findings=[], confidence=0.0, evidence={})

    def test_evaluator_verdict_confidence_bounded(self):
        # ge=0.0, le=1.0
        with pytest.raises(Exception):
            EvaluatorVerdict(
                verdict="PASS", findings=[], confidence=1.1, evidence={}
            )
        with pytest.raises(Exception):
            EvaluatorVerdict(
                verdict="PASS", findings=[], confidence=-0.1, evidence={}
            )


# ---------------------------------------------------------------------------
# AC3: prompt-boundary isolation
# ---------------------------------------------------------------------------


class TestPromptBoundaryIsolation:
    """AC3: evaluator must not see the implementation agent's transcript or session id.

    Enforced both structurally (function signature) and behaviourally
    (the body never reads ``parent_run_id`` or any implementation
    transcript field; the prompt it builds never embeds them).
    """

    def test_signature_does_not_accept_implementation_transcript(self):
        sig = inspect.signature(spawn_evaluator_agent)
        param_names = set(sig.parameters)
        # AC3: forbidden inputs
        forbidden = {
            "transcript",
            "implementation_transcript",
            "session_id",
            "implementation_session_id",
            "parent_run_id",
            "execution_result",
            "spawn_result",
            "implementation_prompt",
        }
        leaked = forbidden & param_names
        assert not leaked, (
            f"spawn_evaluator_agent must not receive implementation "
            f"context — found forbidden parameters: {leaked}"
        )

    def test_signature_only_takes_documented_inputs(self):
        sig = inspect.signature(spawn_evaluator_agent)
        # Allowed inputs per PLAN.md AC3: feature spec, diff,
        # acceptance criteria, workspace path, and (optionally) a
        # session-isolation hint. Plus the standard tracking params
        # (project_id, target_*, max_turns, on_message).
        allowed = {
            "project_id",
            "feature_spec",
            "acceptance_criteria",
            "diff",
            "workspace",
            "target_type",
            "target_id",
            "max_turns",
            "session_isolation_hint",
            "on_message",
        }
        unexpected = set(sig.parameters) - allowed
        assert not unexpected, (
            f"spawn_evaluator_agent has unexpected parameters: {unexpected}"
        )

    def test_body_never_references_implementation_session_id(self):
        """The implementation must never read parent_run_id or session_id from inputs."""
        src = inspect.getsource(spawn_evaluator_agent)
        # Strip the docstring so docstring text doesn't trigger the
        # substring checks below.
        import ast as _ast
        tree = _ast.parse(src)
        func = tree.body[0]
        assert isinstance(func, _ast.AsyncFunctionDef)
        # Drop the docstring node if present
        if (
            func.body
            and isinstance(func.body[0], _ast.Expr)
            and isinstance(func.body[0].value, _ast.Constant)
            and isinstance(func.body[0].value.value, str)
        ):
            func.body = func.body[1:]
        body_src = _ast.unparse(func)

        # parent_run_id should appear ONCE — when explicitly passed as
        # None to spawn_sub_agent. It must not be read from a parameter.
        assert "parent_run_id=None" in body_src, (
            "spawn_evaluator_agent must explicitly pass parent_run_id=None "
            "to keep the evaluator unlinked from the implementation run."
        )
        # The body (excluding docstring) must not reference any
        # implementation-context attribute.
        for forbidden in (
            "implementation_transcript",
            "spawn_result.execution_result.text",
            "result.text",
            "execution_result.text",
        ):
            assert forbidden not in body_src, (
                f"spawn_evaluator_agent body contains forbidden reference: {forbidden}"
            )

    def test_system_prompt_describes_independent_qa_role(self):
        # The system prompt must establish the independent-QA framing.
        prompt = EVALUATOR_SYSTEM_PROMPT
        assert "QA engineer" in prompt or "QA" in prompt
        assert "never seen" in prompt or "have not seen" in prompt or "not seen" in prompt
        # And explicitly call out the lack of implementation transcript.
        assert "transcript" in prompt.lower()

    def test_evaluator_disallows_edit_write_tools(self):
        # AC3: the evaluator must not be able to "fix" the diff and
        # then self-grade as PASS.
        for tool in ("Edit", "Write", "NotebookEdit"):
            assert tool in EVALUATOR_DISALLOWED_TOOLS, (
                f"Evaluator must disallow {tool}; got {EVALUATOR_DISALLOWED_TOOLS}"
            )
        # Read/Bash are fine — needed to inspect files and run pytest.
        assert "Read" in EVALUATOR_ALLOWED_TOOLS
        assert "Edit" not in EVALUATOR_ALLOWED_TOOLS
        assert "Write" not in EVALUATOR_ALLOWED_TOOLS

    @pytest.mark.asyncio
    async def test_spawn_does_not_pass_parent_run_id(self, project, workspace):
        """End-to-end: the spawn_sub_agent call passes parent_run_id=None.

        We patch the underlying ``spawn_sub_agent`` and assert that
        ``parent_run_id`` is not set, regardless of what context the
        evaluator was invoked from.
        """
        captured = {}

        async def fake_spawn_sub_agent(**kwargs):
            captured.update(kwargs)
            from bob.orchestrator.claude_executor import (
                ExecutionResult,
                SpawnResult,
            )

            return SpawnResult(
                execution_result=ExecutionResult(
                    text='```json\n{"verdict": "PASS", "findings": [], '
                    '"confidence": 0.9, "evidence": {}}\n```',
                    is_error=False,
                ),
                agent_run=MagicMock(id="ev-run-1"),
            )

        with patch(
            "bob.orchestrator.claude_executor.spawn_sub_agent",
            new=fake_spawn_sub_agent,
        ):
            await spawn_evaluator_agent(
                project_id=project.id,
                feature_spec="Add a thing",
                acceptance_criteria="The thing must be added",
                diff="diff --git a/foo b/foo\n+thing",
                workspace=workspace,
            )

        # parent_run_id must be None (sibling, not child, of impl agent)
        assert captured.get("parent_run_id") is None
        assert captured.get("purpose") == "evaluator"
        # Prompt must contain the spec + criteria + diff but NOT any
        # implementation transcript markers.
        prompt = captured["prompt"]
        assert "Add a thing" in prompt
        assert "The thing must be added" in prompt
        assert "diff --git" in prompt


# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------


class TestParseEvaluatorVerdict:

    def test_parses_fenced_json(self):
        text = (
            "Some preamble\n"
            "```json\n"
            '{"verdict": "FAIL", "findings": ["bug"], '
            '"confidence": 0.7, "evidence": {"AC1": "test_x.py:42"}}\n'
            "```\n"
        )
        v = parse_evaluator_verdict(text)
        assert v["verdict"] == "FAIL"
        assert v["findings"] == ["bug"]
        assert v["confidence"] == 0.7
        assert v["evidence"] == {"AC1": "test_x.py:42"}

    def test_unparseable_returns_insufficient_evidence(self):
        v = parse_evaluator_verdict("not json at all")
        assert v["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert v["confidence"] == 0.0

    def test_invalid_verdict_returns_insufficient_evidence(self):
        text = '```json\n{"verdict": "MAYBE", "findings": [], "confidence": 1.0}\n```'
        v = parse_evaluator_verdict(text)
        assert v["verdict"] == "INSUFFICIENT_EVIDENCE"

    def test_confidence_clamped_to_unit_interval(self):
        text = '```json\n{"verdict": "PASS", "findings": [], "confidence": 5.0, "evidence": {}}\n```'
        v = parse_evaluator_verdict(text)
        assert v["verdict"] == "PASS"
        assert v["confidence"] == 1.0


# ---------------------------------------------------------------------------
# AC4: FAIL routes to reviews/findings.yaml with the right tag
# ---------------------------------------------------------------------------


class TestEvaluatorFailRoutesToFindingsRegistry:
    """AC4: orchestrator's evaluator-rejection handler files a finding
    to ``reviews/findings.yaml`` with ``tag="evaluator-rejection"``.

    The handler is ``OrchestrationLoop._file_evaluator_rejection_finding``.
    """

    def test_file_evaluator_rejection_finding_tags_correctly(self, tmp_path, project):
        from bob import reviews
        from bob.models import Feature
        from bob.orchestrator.run_loop import OrchestrationLoop

        # Set up an isolated registry file
        registry_path = tmp_path / "findings.yaml"
        registry_path.write_text(
            "schema_version: 1\nfindings: []\nrecurring_patterns: []\n"
        )

        loop = OrchestrationLoop(
            project_id=project.id,
            workspace=str(tmp_path),
        )

        feature = Feature(
            id="feat-x",
            project_id=project.id,
            name="A feature",
            description="desc",
            acceptance_criteria="ac",
        )

        verdict = {
            "verdict": "FAIL",
            "findings": ["The slope diagram does not respond to the slider"],
            "confidence": 0.85,
            "evidence": {"AC2": "screenshot:def456"},
        }

        with patch("bob.reviews._registry_path", return_value=registry_path):
            loop._file_evaluator_rejection_finding(
                feature=feature, verdict=verdict
            )

        # The finding must be in the registry with the correct tag.
        loaded = reviews.load_registry(registry_path)
        assert loaded.findings, "No finding was filed"
        latest = loaded.findings[-1]
        assert "evaluator-rejection" in latest.tags
        assert latest.severity == "high"
        # Notes should reference the verdict
        assert "FAIL" in latest.notes
        assert "slope diagram" in latest.notes


# ---------------------------------------------------------------------------
# AC5: adversarial-self-review is evaluator-only
# ---------------------------------------------------------------------------


class TestAdversarialSelfReviewIsEvaluatorOnly:
    """AC5: install_skills_to_workspace must NOT install adversarial-self-review
    in the default (implementation) path; only when include_evaluator_skills=True.
    """

    def test_evaluator_only_skills_constant_lists_adversarial_review(self):
        assert "adversarial-self-review" in EVALUATOR_ONLY_SKILLS

    def test_default_install_excludes_adversarial_review(self, workspace):
        installed = install_skills_to_workspace(workspace)
        assert "adversarial-self-review" not in installed
        # Should not exist in workspace
        target = workspace / ".claude" / "skills" / "adversarial-self-review"
        assert not target.exists() and not target.is_symlink()

    def test_evaluator_install_includes_adversarial_review(self, workspace):
        installed = install_skills_to_workspace(
            workspace, include_evaluator_skills=True
        )
        assert "adversarial-self-review" in installed
        target = workspace / ".claude" / "skills" / "adversarial-self-review"
        assert target.exists() or target.is_symlink()

    def test_install_removes_pre_existing_adversarial_review(self, workspace):
        """If a previous bob version installed the skill, it gets removed."""
        # Pre-install the skill via the evaluator path...
        install_skills_to_workspace(
            workspace, include_evaluator_skills=True
        )
        target = workspace / ".claude" / "skills" / "adversarial-self-review"
        assert target.exists() or target.is_symlink()
        # ...then run the default (impl) path; the skill should be removed.
        install_skills_to_workspace(workspace)
        assert not target.exists() and not target.is_symlink()
