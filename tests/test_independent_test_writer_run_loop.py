"""Focused integration tests for Bob's required independent-test boundary."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_code_sdk import ClaudeCodeOptions

from bob.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob.orchestrator.independent_test_writer import (
    CriterionCoverage,
    TestFileEvidence as _TestFileEvidence,
    TestWriterEvidence as _TestWriterEvidence,
    TestWriterRoleResult as _TestWriterRoleResult,
    WriterGreenExecution,
    WriterTestExecution,
    snapshot_test_roots,
    test_manifest_sha256 as _test_manifest_sha256,
    test_writer_assignment_sha256 as _test_writer_assignment_sha256,
    writer_test_execution_sha256,
)
from bob.candidate_change_manifest import manifest_sha256, snapshot_candidate_tree


class _StopAfterImplementer(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _disable_slow_regression_snapshot(monkeypatch):
    monkeypatch.setenv("BOB_REGRESSION_DETECTION_ENABLED", "0")
    # These tests exercise the writer/run-loop transaction in isolation. The
    # complete hardened startup profile is covered in test_candidate_hardening.
    monkeypatch.setattr(
        "bob.orchestrator.run_loop.validate_candidate_execution_policy",
        lambda **kwargs: None,
    )


def _feature():
    return SimpleNamespace(
        id="feature-1",
        name="Feature one",
        description="Implement observable feature-one behavior",
        acceptance_criteria='["returns the projected value", "rejects bad input"]',
        exceeds_size_limits=False,
        tdd_mode=None,
        sub_agent_mode=None,
        estimated_files_touched=1,
        estimated_complexity=1,
        model_tier=0,
        refinement_attempts=0,
        max_refinement_attempts=5,
        conf_impl_correctness=0.9,
        status="ready",
    )


def _loop(workspace):
    from bob.orchestrator.run_loop import OrchestrationLoop

    loop = object.__new__(OrchestrationLoop)
    loop.project_id = "project-1"
    loop.workspace = str(workspace)
    loop.features_completed = 0
    loop.features_failed = 0
    loop.shutdown_requested = False
    loop._current_feature = None
    loop._cost_proxy_active = False
    loop._spawn_failure_counts = {}
    loop._cost_projection_gate = MagicMock(return_value=None)
    loop._run_research = AsyncMock(return_value=None)
    loop._increment_cost = MagicMock()
    loop._run_evaluator = AsyncMock(return_value=None)
    return loop


def _writer_result(
    test_bytes: bytes,
    workspace,
    *,
    outcome: str = "completed",
    error: str = "",
):
    feature = _feature()
    acceptance_criteria = (
        "returns the projected value",
        "rejects bad input",
    )
    changed = (
        _TestFileEvidence(
            path="tests/test_feature.py",
            operation="created",
            sha256=hashlib.sha256(test_bytes).hexdigest(),
            size_bytes=len(test_bytes),
        ),
    )
    evidence = _TestWriterEvidence(
        role="independent_test_writer",
        principal_nonce="nonce",
        session_id="writer-session",
        cwd=str(workspace),
        model="claude-opus-4-8",
        max_turns=None,
        prompt_sha256="1" * 64,
        response_sha256="2" * 64,
        duration_ms=10,
        num_turns=2,
        total_cost_usd=0.1,
        tool_uses=("Read", "Write"),
        changed_files=changed if outcome == "completed" else (),
        unauthorized_changes=(),
        agent_run_id="writer-run",
        test_namespace="tests/bob_generated/feature-1-a0-deadbeef",
        post_test_manifest=(
            snapshot_test_roots(cwd=workspace, allowed_test_roots=("tests",))
            if outcome == "completed"
            else ()
        ),
        test_execution=(
            WriterTestExecution(
                collected_node_ids=(
                    "tests/test_feature.py::test_projection",
                    "tests/test_feature.py::test_bad_input",
                ),
                test_argv=(
                    sys.executable,
                    "-B",
                    "-m",
                    "pytest",
                    "-c",
                    os.devnull,
                    "--rootdir=.",
                    "--noconftest",
                    "-p",
                    "no:cacheprovider",
                    "--color=no",
                    "-vv",
                    "tests/test_feature.py::test_projection",
                    "tests/test_feature.py::test_bad_input",
                ),
                red_exit_code=1,
                red_output_sha256="3" * 64,
                red_failed_node_ids=(
                    "tests/test_feature.py::test_projection",
                    "tests/test_feature.py::test_bad_input",
                ),
            )
            if outcome == "completed"
            else None
        ),
        production_baseline_manifest=snapshot_candidate_tree(
            cwd=workspace, excluded_roots=("tests",)
        ),
        production_baseline_manifest_sha256=manifest_sha256(
            snapshot_candidate_tree(cwd=workspace, excluded_roots=("tests",))
        ),
        assignment_sha256=_test_writer_assignment_sha256(
            feature_id=feature.id,
            feature_title=feature.name,
            feature_description=feature.description,
            acceptance_criteria=acceptance_criteria,
            allowed_test_roots=("tests",),
        ),
    )
    return _TestWriterRoleResult(
        outcome=outcome,
        reported_status="completed" if outcome == "completed" else None,
        feature_id="feature-1",
        test_files=("tests/test_feature.py",) if outcome == "completed" else (),
        test_command=("pytest", "-q", "tests/test_feature.py") if outcome == "completed" else (),
        criterion_coverage=(
            CriterionCoverage(0, ("tests/test_feature.py::test_projection",)),
            CriterionCoverage(1, ("tests/test_feature.py::test_bad_input",)),
        ) if outcome == "completed" else (),
        notes=(),
        evidence=evidence,
        error=error,
    )


def _common_patches(options, writer_mock, implementer_mock):
    current = []

    def create_evidence(**kwargs):
        created = SimpleNamespace(
            id=f"evidence-{len(current)}",
            output_hash=kwargs.get("output_hash"),
            type=kwargs["type"],
            content=kwargs["content"],
            is_current=kwargs.get("is_current", True),
        )
        if kwargs.get("is_current", True):
            if kwargs.get("supersede_current") or kwargs["type"] == (
                "independent_test_writer"
            ):
                current[:] = [
                    item for item in current if item.type != kwargs["type"]
                ]
            current.append(created)
        return created

    return (
        patch("bob.orchestrator.run_loop.db.update_feature"),
        patch("bob.orchestrator.run_loop.db.create_evidence", side_effect=create_evidence),
        patch("bob.orchestrator.run_loop.db.query_evidence", side_effect=lambda **_: list(current)),
        patch("bob.orchestrator.run_loop.git_get_status", return_value={"sha": "base"}),
        patch("bob.orchestrator.run_loop.build_sub_agent_options", return_value=options),
        patch("bob.orchestrator.run_loop._run_independent_test_writer_role", writer_mock),
        patch("bob.orchestrator.run_loop.spawn_sub_agent", implementer_mock),
        patch("bob.orchestrator.run_loop.wrap_prompt_with_orientation", side_effect=lambda **kw: kw["prompt"]),
    )


@pytest.mark.asyncio
async def test_required_writer_runs_before_implementer_with_identical_options(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "unlimited")
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "none")
    test_bytes = b"def test_projection():\n    assert project() == 7\n"
    test_path = tmp_path / "tests" / "test_feature.py"
    test_path.parent.mkdir()
    test_path.write_bytes(test_bytes)
    calls: list[str] = []
    options = ClaudeCodeOptions(
        cwd=str(tmp_path), model="claude-opus-4-8", max_turns=None
    )

    async def writer_side_effect(**kwargs):
        calls.append("writer")
        return _writer_result(test_bytes, tmp_path)

    async def implementer_side_effect(**kwargs):
        calls.append("implementer")
        assert "MANDATORY INDEPENDENT-TEST FREEZE" in kwargs["prompt"]
        assert "Do not create, edit, rename, move, or delete tests" in kwargs["prompt"]
        raise _StopAfterImplementer

    writer = AsyncMock(side_effect=writer_side_effect)
    implementer = AsyncMock(side_effect=implementer_side_effect)
    wait_for = AsyncMock(side_effect=AssertionError("unlimited mode used wait_for"))
    patches = _common_patches(options, writer, implementer)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patch(
        "bob.orchestrator.run_loop.asyncio.wait_for", wait_for
    ):
        with pytest.raises(_StopAfterImplementer):
            await _loop(tmp_path).execute_feature(_feature())

    assert calls == ["writer", "implementer"]
    assert writer.await_args.kwargs["options"].model == options.model
    assert writer.await_args.kwargs["options"].env["BOB_AGENT_ROLE"] == (
        "independent_test_writer"
    )
    assert implementer.await_args.kwargs["options"] is options
    wait_for.assert_not_awaited()


@pytest.mark.asyncio
async def test_required_writer_failure_prevents_implementer(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "none")
    options = ClaudeCodeOptions(cwd=str(tmp_path), model="claude-opus-4-8")
    writer = AsyncMock(
        return_value=_writer_result(
            b"", tmp_path,
            outcome="protocol_error",
            error="completed writer produced no changed test",
        )
    )
    implementer = AsyncMock()
    patches = _common_patches(options, writer, implementer)
    with patches[0] as update_feature, patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        result = await _loop(tmp_path).execute_feature(_feature())

    assert result.execution_result.is_error
    assert "independent test writer failed" in result.execution_result.error_message.lower()
    implementer.assert_not_awaited()
    assert any(
        call.kwargs.get("status") == "needs_human"
        for call in update_feature.call_args_list
    )


@pytest.mark.asyncio
async def test_implementer_test_mutation_blocks_commit(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "none")
    monkeypatch.setenv("BOB_REGRESSION_DETECTION_ENABLED", "0")
    original = b"def test_projection():\n    assert project() == 7\n"
    test_path = tmp_path / "tests" / "test_feature.py"
    test_path.parent.mkdir()
    test_path.write_bytes(original)
    options = ClaudeCodeOptions(cwd=str(tmp_path), model="claude-opus-4-8")
    writer = AsyncMock(return_value=_writer_result(original, tmp_path))

    async def mutate_test(**kwargs):
        test_path.write_text("def test_projection():\n    assert True\n")
        return SpawnResult(
            execution_result=ExecutionResult(
                text="implemented",
                is_error=False,
                duration_ms=10,
                num_turns=1,
                total_cost_usd=0.2,
            ),
            agent_run=SimpleNamespace(id="implementation-run"),
        )

    implementer = AsyncMock(side_effect=mutate_test)
    patches = _common_patches(options, writer, implementer)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patch(
        "bob.orchestrator.run_loop._run_writer_tests_green",
        return_value=WriterGreenExecution(0, "4" * 64, True),
    ), patch(
        "bob.orchestrator.run_loop.run_verification_checklist",
        return_value={"passed": True, "summary": "tests pass", "checks": []},
    ), patch(
        "bob.orchestrator.run_loop.handle_execution_result",
        return_value={"cost_usd": 0.2, "cost_source": "sdk", "evidence_id": "execution"},
    ) as handle_result, patch(
        "bob.orchestrator.run_loop.git_commit_feature"
    ) as commit, patch(
        "bob.orchestrator.run_loop.update_progress_notes"
    ), patch(
        "bob.orchestrator.run_loop._record_feature_calibration"
    ), patch(
        "bob.orchestrator.run_loop.db.get_feature",
        return_value=_feature(),
    ), patch(
        "bob.orchestrator.run_loop.db.rollback_feature_cascade"
    ) as rollback:
        loop = _loop(tmp_path)
        await loop.execute_feature(_feature())

    assert handle_result.call_args.kwargs["verification_passed"] is False
    commit.assert_not_called()
    rollback.assert_called_once_with("feature-1", target_status="needs_human")
    assert loop.features_failed == 1


@pytest.mark.asyncio
async def test_intact_independent_tests_reach_commit_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "none")
    original = b"def test_projection():\n    assert project() == 7\n"
    test_path = tmp_path / "tests" / "test_feature.py"
    test_path.parent.mkdir()
    test_path.write_bytes(original)
    options = ClaudeCodeOptions(cwd=str(tmp_path), model="claude-opus-4-8")
    writer = AsyncMock(return_value=_writer_result(original, tmp_path))
    implementer = AsyncMock(
        return_value=SpawnResult(
            execution_result=ExecutionResult(
                text="implemented",
                is_error=False,
                session_id="implementation-session",
                duration_ms=10,
                num_turns=1,
                total_cost_usd=0.2,
            ),
            agent_run=SimpleNamespace(id="implementation-run"),
        )
    )
    commit_sha = "a" * 40

    def exact_commit(**kwargs):
        kwargs["on_exact_commit_planned"](
            {
                "commit_sha": commit_sha,
                "parent_sha": "b" * 40,
                "tree_sha": "c" * 40,
                "paths": list(kwargs["stage_paths"]),
            }
        )
        return commit_sha

    patches = _common_patches(options, writer, implementer)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patch(
        "bob.orchestrator.run_loop._run_writer_tests_green",
        return_value=WriterGreenExecution(0, "4" * 64, True),
    ), patch(
        "bob.orchestrator.run_loop.run_verification_checklist",
        return_value={"passed": True, "summary": "tests pass", "checks": []},
    ), patch(
        "bob.orchestrator.run_loop.handle_execution_result",
        return_value={"cost_usd": 0.2, "cost_source": "sdk", "evidence_id": "execution"},
    ), patch(
        "bob.orchestrator.run_loop.git_commit_feature",
        side_effect=exact_commit,
    ) as commit, patch(
        "bob.orchestrator.run_loop.git_get_commit_proof",
        return_value={
            "commit_sha": commit_sha,
            "parent_sha": "b" * 40,
            "tree_sha": "c" * 40,
            "paths": ["tests/test_feature.py"],
            "entries": [
                {
                    "path": "tests/test_feature.py",
                    "operation": "present",
                    "mode": "100644",
                    "object_type": "blob",
                    "blob_sha": "d" * 40,
                    "content_sha256": hashlib.sha256(original).hexdigest(),
                }
            ],
        },
    ), patch(
        "bob.orchestrator.run_loop.db.complete_feature_hierarchy_and_cascade",
        return_value=[],
    ), patch(
        "bob.orchestrator.run_loop.update_progress_notes"
    ), patch(
        "bob.orchestrator.run_loop._record_feature_calibration"
    ), patch(
        "bob.orchestrator.run_loop.db.get_feature",
        return_value=_feature(),
    ):
        loop = _loop(tmp_path)
        loop._run_evaluator.return_value = {
            "verdict": "PASS",
            "findings": [],
            "confidence": 0.9,
            "evidence": {},
            "_provider_session_id": "evaluator-session",
            "_agent_run_id": "evaluator-run",
            "_prompt_sha256": "5" * 64,
            "_result_sha256": "6" * 64,
        }
        await loop.execute_feature(_feature())

    commit.assert_called_once()
    assert loop.features_completed == 1
    assert loop.features_failed == 0


@pytest.mark.parametrize("value", ["unlimited", "none", " UNLIMITED "])
def test_feature_timeout_can_be_unlimited(monkeypatch, value):
    from bob.orchestrator.run_loop import _resolve_feature_timeout_seconds

    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", value)
    assert _resolve_feature_timeout_seconds() is None


def test_feature_timeout_preserves_finite_positive_policy(monkeypatch):
    from bob.orchestrator.run_loop import _resolve_feature_timeout_seconds

    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "123.5")
    assert _resolve_feature_timeout_seconds() == 123.5


@pytest.mark.parametrize("value", ["garbage", "0", "-1", "nan", "inf"])
def test_feature_timeout_malformed_policy_fails_closed(monkeypatch, value):
    from bob.orchestrator.run_loop import _resolve_feature_timeout_seconds

    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="BOB_FEATURE_TIMEOUT_SECONDS"):
        _resolve_feature_timeout_seconds()


@pytest.mark.asyncio
async def test_legacy_workspace_completes_only_after_nonempty_commit(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "disabled")
    monkeypatch.setenv("BOB_FEATURE_TIMEOUT_SECONDS", "none")
    options = ClaudeCodeOptions(cwd=str(tmp_path), model="claude-opus-4-8")
    implementer = AsyncMock(
        return_value=SpawnResult(
            execution_result=ExecutionResult(
                text="implemented",
                is_error=False,
                session_id="implementer-session",
                duration_ms=1,
                num_turns=1,
                total_cost_usd=0.1,
            ),
            agent_run=SimpleNamespace(id="implementer-run"),
        )
    )
    writer = AsyncMock()
    patches = _common_patches(options, writer, implementer)
    order: list[str] = []

    def handled(**kwargs):
        order.append("handled")
        assert kwargs["defer_success_completion"] is True
        return {"cost_usd": 0.1, "cost_source": "sdk", "evidence_id": "execution"}

    def committed(**kwargs):
        order.append("committed")
        return "a" * 40

    def completed(feature):
        order.append("completed")

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patch(
        "bob.orchestrator.run_loop.run_verification_checklist",
        return_value={"passed": True, "summary": "pass", "checks": []},
    ), patch(
        "bob.orchestrator.run_loop.handle_execution_result", side_effect=handled
    ), patch(
        "bob.orchestrator.run_loop.git_commit_feature", side_effect=committed
    ), patch(
        "bob.orchestrator.run_loop._complete_feature_and_ancestors",
        side_effect=completed,
    ), patch(
        "bob.orchestrator.run_loop.update_progress_notes"
    ), patch(
        "bob.orchestrator.run_loop._record_feature_calibration"
    ), patch(
        "bob.orchestrator.run_loop.db.get_feature", return_value=_feature()
    ):
        loop = _loop(tmp_path)
        await loop.execute_feature(_feature())

    assert order == ["handled", "committed", "completed"]
    assert loop.features_completed == 1


def test_commit_intent_recovery_finalizes_even_from_needs_human_status(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    test_bytes = b"def test_projection():\n    assert project() == 7\n"
    test_path = tmp_path / "tests" / "test_feature.py"
    test_path.parent.mkdir()
    test_path.write_bytes(test_bytes)
    feature = _feature()
    feature.status = "needs_human"
    writer = _writer_result(test_bytes, tmp_path)

    def artifact(evidence_type, payload, identifier):
        content = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
        return SimpleNamespace(
            id=identifier,
            type=evidence_type,
            content=content,
            output_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )

    writer_artifact = artifact(
        "independent_test_writer",
        json.dumps(asdict(writer), sort_keys=True),
        "writer-evidence",
    )
    bundle_sha = "4" * 64
    bundle_artifact = artifact(
        "candidate_change_bundle",
        {
            "change_bundle_sha256": bundle_sha,
            "implementer_agent_run_id": "implementer-run",
            "implementer_provider_session_id": "implementer-session",
            "implementer_prompt_sha256": "3" * 64,
            "implementer_result_sha256": "4" * 64,
        },
        "bundle-evidence",
    )
    evaluator_artifact = artifact(
        "evaluator_verdict",
        {
            "change_bundle_sha256": bundle_sha,
            "agent_run_id": "evaluator-run",
            "provider_session_id": "evaluator-session",
            "evaluator_prompt_sha256": "5" * 64,
            "evaluator_result_sha256": "6" * 64,
        },
        "evaluator-evidence",
    )
    manifest_digest = _test_manifest_sha256(writer.evidence.post_test_manifest)
    execution_digest = writer_test_execution_sha256(
        writer.evidence.test_execution
    )
    commit_sha = "a" * 40
    intent_payload = {
        "feature_id": feature.id,
        "attempt_number": 0,
        "commit_sha": commit_sha,
        "parent_sha": "b" * 40,
        "tree_sha": "c" * 40,
        "paths": ["tests/test_feature.py"],
        "expected_file_sha256": {
            "tests/test_feature.py": hashlib.sha256(test_bytes).hexdigest()
        },
        "expected_file_modes": {"tests/test_feature.py": "100644"},
        "change_bundle_sha256": bundle_sha,
        "test_manifest_sha256": manifest_digest,
        "test_execution_sha256": execution_digest,
        "writer_assignment_sha256": writer.evidence.assignment_sha256,
        "writer_agent_run_id": "writer-run",
        "writer_provider_session_id": "writer-session",
        "writer_prompt_sha256": "1" * 64,
        "writer_response_sha256": "2" * 64,
        "implementer_agent_run_id": "implementer-run",
        "implementer_provider_session_id": "implementer-session",
        "implementer_prompt_sha256": "3" * 64,
        "implementer_result_sha256": "4" * 64,
        "evaluator_agent_run_id": "evaluator-run",
        "evaluator_provider_session_id": "evaluator-session",
        "evaluator_prompt_sha256": "5" * 64,
        "evaluator_result_sha256": "6" * 64,
        "feature_description_sha256": hashlib.sha256(
            feature.description.encode("utf-8")
        ).hexdigest(),
    }
    intent_artifact = artifact(
        "feature_commit_intent", intent_payload, "intent-evidence"
    )
    runs = {
        "writer-run": SimpleNamespace(
            status="completed",
            agent_role="independent_test_writer",
            provider_session_id="writer-session",
            model="claude-opus-4-8",
            cwd=str(tmp_path),
            prompt_sha256="1" * 64,
            result_sha256="2" * 64,
        ),
        "implementer-run": SimpleNamespace(
            status="completed",
            agent_role="implementer",
            provider_session_id="implementer-session",
            model="claude-opus-4-8",
            cwd=str(tmp_path),
            prompt_sha256="3" * 64,
            result_sha256="4" * 64,
        ),
        "evaluator-run": SimpleNamespace(
            status="completed",
            agent_role="evaluator",
            provider_session_id="evaluator-session",
            model="claude-opus-4-8",
            cwd=str(tmp_path),
            prompt_sha256="5" * 64,
            result_sha256="6" * 64,
        ),
    }
    proof = {
        "commit_sha": commit_sha,
        "parent_sha": "b" * 40,
        "tree_sha": "c" * 40,
        "paths": ["tests/test_feature.py"],
        "entries": [
            {
                "path": "tests/test_feature.py",
                "operation": "present",
                "mode": "100644",
                "object_type": "blob",
                "content_sha256": hashlib.sha256(test_bytes).hexdigest(),
            }
        ],
    }
    loop = _loop(tmp_path)
    persisted = MagicMock(
        side_effect=lambda **kwargs: SimpleNamespace(
            id=f"persisted-{kwargs['evidence_type']}",
            output_hash="7" * 64,
        )
    )
    with patch(
        "bob.orchestrator.run_loop.db.query_evidence",
        return_value=[
            intent_artifact,
            writer_artifact,
            bundle_artifact,
            evaluator_artifact,
        ],
    ), patch(
        "bob.orchestrator.run_loop.db.get_agent_run",
        side_effect=lambda run_id: runs.get(run_id),
    ), patch(
        "bob.orchestrator.run_loop.git_finalize_exact_commit_intent",
        return_value=proof,
    ) as finalize, patch(
        "bob.orchestrator.run_loop._persist_required_current_evidence",
        persisted,
    ), patch(
        "bob.orchestrator.run_loop._complete_feature_and_ancestors"
    ) as complete, patch(
        "bob.orchestrator.run_loop.db.update_evidence"
    ), patch(
        "bob.orchestrator.run_loop.update_progress_notes"
    ), patch(
        "bob.orchestrator.run_loop._record_feature_calibration"
    ):
        result = loop._recover_hardened_commit_intent(feature)

    assert result is not None and not result.execution_result.is_error
    finalize.assert_called_once()
    complete.assert_called_once_with(feature)
    assert [call.kwargs["evidence_type"] for call in persisted.call_args_list] == [
        "feature_commit",
        "completion_finalized",
    ]

    substituted_evaluator = artifact(
        "evaluator_verdict",
        {
            "change_bundle_sha256": bundle_sha,
            "agent_run_id": "evaluator-run",
            "provider_session_id": "evaluator-session",
            "evaluator_prompt_sha256": "5" * 64,
            "evaluator_result_sha256": "9" * 64,
        },
        "substituted-evaluator",
    )
    with patch(
        "bob.orchestrator.run_loop.db.query_evidence",
        return_value=[
            intent_artifact,
            writer_artifact,
            bundle_artifact,
            substituted_evaluator,
        ],
    ), patch(
        "bob.orchestrator.run_loop.db.get_agent_run",
        side_effect=lambda run_id: runs.get(run_id),
    ), patch(
        "bob.orchestrator.run_loop.git_finalize_exact_commit_intent"
    ) as forbidden_finalize, patch(
        "bob.orchestrator.run_loop.db.update_feature"
    ):
        rejected = _loop(tmp_path)._recover_hardened_commit_intent(feature)

    assert rejected is not None and rejected.execution_result.is_error
    assert "evaluator artifact binding mismatch" in (
        rejected.execution_result.error_message or ""
    )
    forbidden_finalize.assert_not_called()


def test_startup_commit_intent_scan_ignores_feature_status(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    feature = _feature()
    feature.status = "needs_human"
    intent = SimpleNamespace(
        type="feature_commit_intent", feature_id=feature.id
    )
    recovered = SpawnResult(
        execution_result=ExecutionResult(text="recovered", is_error=False),
        agent_run=SimpleNamespace(id="implementer-run"),
    )
    loop = _loop(tmp_path)
    loop._recover_hardened_commit_intent = MagicMock(return_value=recovered)

    with patch(
        "bob.orchestrator.run_loop.db.query_evidence", return_value=[intent]
    ) as query, patch(
        "bob.orchestrator.run_loop.db.get_feature", return_value=feature
    ):
        assert loop._recover_all_hardened_commit_intents() is True

    query.assert_called_once_with(project_id=loop.project_id, is_current=True)
    loop._recover_hardened_commit_intent.assert_called_once_with(feature)


def test_startup_commit_intent_scan_fails_closed_on_recovery_error(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    feature = _feature()
    intent = SimpleNamespace(
        type="feature_commit_intent", feature_id=feature.id
    )
    rejected = SpawnResult(
        execution_result=ExecutionResult(
            text="", is_error=True, error_message="proof mismatch"
        ),
        agent_run=SimpleNamespace(id=None),
    )
    loop = _loop(tmp_path)
    loop._recover_hardened_commit_intent = MagicMock(return_value=rejected)

    with patch(
        "bob.orchestrator.run_loop.db.query_evidence", return_value=[intent]
    ), patch("bob.orchestrator.run_loop.db.get_feature", return_value=feature):
        assert loop._recover_all_hardened_commit_intents() is False


def test_required_execution_evidence_binds_full_implementer_output():
    from bob.orchestrator.run_loop import handle_execution_result

    feature = _feature()
    output = "implementation-result\n" + ("x" * 9000)
    spawn = SpawnResult(
        execution_result=ExecutionResult(
            text=output,
            is_error=False,
            session_id="implementer-session",
        ),
        agent_run=SimpleNamespace(id="implementer-run"),
    )
    captured: dict[str, object] = {}

    def create_evidence(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="execution-evidence")

    with patch("bob.orchestrator.run_loop.db.update_feature"), patch(
        "bob.orchestrator.run_loop.db.create_evidence",
        side_effect=create_evidence,
    ), patch(
        "bob.orchestrator.run_loop.db.get_feature",
        return_value=SimpleNamespace(status="executing"),
    ):
        outcome = handle_execution_result(
            project_id="project-1",
            feature=feature,
            spawn_result=spawn,
            verification_passed=True,
            required_evidence=True,
            defer_success_completion=True,
            change_bundle_sha256="a" * 64,
            implementer_provider_session_id="implementer-session",
            implementer_prompt_sha256="b" * 64,
            implementer_result_sha256=hashlib.sha256(
                output.encode("utf-8")
            ).hexdigest(),
        )

    assert outcome["evidence_id"] == "execution-evidence"
    evidence = json.loads(captured["content"])
    assert evidence["output_text"] == output
    assert evidence["output_text_sha256"] == hashlib.sha256(
        output.encode("utf-8")
    ).hexdigest()
    assert evidence["implementer_prompt_sha256"] == "b" * 64
    assert evidence["implementer_result_sha256"] == hashlib.sha256(
        output.encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["one", "two"]', ("one", "two")),
        ("- one\n- two", ("one", "two")),
        ({"criteria": [{"text": "one"}, {"criterion": "two"}]}, ("one", "two")),
        ("one wrapped prose criterion", ("one wrapped prose criterion",)),
    ],
)
def test_acceptance_criteria_normalization(raw, expected):
    from bob.orchestrator.run_loop import _parse_independent_acceptance_criteria

    assert _parse_independent_acceptance_criteria(raw) == expected
