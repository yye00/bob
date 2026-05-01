"""Tests for F124: End-to-end verification-gates-completion through the resume flow.

This file is the real-path counterpart to F118, which patches
``run_verification_checklist`` to always pass via ``_passing_verification``
because its lightweight ``/tmp`` workspaces lack the implementation files
required by the spec's acceptance criteria.

F124 instead exercises the new verification-first ordering against a real
workspace with a proper Python project layout. It demonstrates that:

1. When the sub-agent succeeds but the workspace does NOT contain the
   files required by the acceptance criteria, ``run_verification_checklist``
   fails, the feature is marked ``needs_human`` (NOT ``completed``), and
   no dependent features are cascaded to ``ready``.
2. When the same feature is later re-run with a sub-agent that DOES
   produce the required files, verification passes, the feature becomes
   ``completed``, and dependents cascade to ``ready``.
3. The dead-code branch in ``execute_feature`` that previously raised
   ``NameError`` (referencing ``SubAgentResult``, ``time``, and
   ``start_time``) is gone — verified with ``inspect.getsource`` + ``ast``.

These tests must NOT patch ``run_verification_checklist``; they exercise
the real verification path.
"""

import ast
import inspect
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from bob3.db import (
    add_feature_dependency,
    compute_spec_hash,
    create_checkpoint,
    create_feature,
    create_project,
    detect_spec_changes,
    get_checkpoint,
    get_feature,
    get_ready_features,
    init_database,
    list_checkpoints,
    list_features,
    query_evidence,
    update_feature,
    update_project,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import LoopTermination, OrchestrationLoop


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def real_workspace(tmp_path):
    """Create a real Python project workspace with src/ and tests/ scaffolding.

    Verification's project-type detection keys off ``src/`` existing, and
    the workspace must contain at least one non-empty source file plus
    one test file so the static-analysis checks (source_files_exist,
    test_files_exist, code_changes_made) pass on their own. The
    acceptance-criteria check then becomes the deciding gate.

    NOTE on stub heuristics: the verifier's ``no_stubs_in_source`` check
    flags any function whose body is a single ``return <literal>`` (even
    at warning severity it still flips ``passed=False`` for that check).
    The baseline source therefore must do something non-trivial in its
    body so the heuristic does NOT fire — otherwise ``no_stubs_in_source``
    becomes the de-facto failing gate and masks every other verification
    result.
    """
    ws = tmp_path / "f124-workspace"
    ws.mkdir()

    # Make it a Python project
    src_dir = ws / "src"
    src_dir.mkdir()
    # A real, non-stub source file so source_files_exist + no_stubs pass.
    # Body is non-trivial (list comprehension + join) so the AST stub
    # heuristic does not fire.
    (src_dir / "baseline.py").write_text(
        "def baseline(name='baseline', count=1):\n"
        "    parts = [f'{name}-{i}' for i in range(count)]\n"
        "    return '|'.join(parts)\n"
    )

    tests_dir = ws / "tests"
    tests_dir.mkdir()
    # Self-contained test (does not rely on sys.path being set to ws/src).
    # Bob3's verifier auto-runs pytest in the workspace, so the test file
    # must actually pass when collected from this directory.
    (tests_dir / "test_baseline.py").write_text(
        "def baseline(name='baseline', count=1):\n"
        "    parts = [f'{name}-{i}' for i in range(count)]\n"
        "    return '|'.join(parts)\n"
        "\n"
        "def test_baseline_default():\n"
        "    assert baseline() == 'baseline-0'\n"
        "\n"
        "def test_baseline_multi():\n"
        "    assert baseline('x', 3) == 'x-0|x-1|x-2'\n"
    )

    return ws


def _make_spawn_result(text="Feature done", is_error=False, cost=0.50):
    """Helper to create a successful SpawnResult."""
    mock_result = ExecutionResult(
        text=text,
        is_error=is_error,
        error_message="" if not is_error else "error",
        duration_ms=3000,
        num_turns=8,
        total_cost_usd=cost,
    )
    mock_agent_run = MagicMock()
    mock_agent_run.id = str(uuid.uuid4())
    return SpawnResult(execution_result=mock_result, agent_run=mock_agent_run)


def _make_high_readiness_feature(
    *, project_id, name, criteria_path, status="ready", priority=10
):
    """Create a feature with a 'File exists: <path>' acceptance criterion
    and readiness above the 'low' risk threshold (0.70)."""
    feature = create_feature(
        project_id=project_id,
        name=name,
        description=f"{name} description",
        acceptance_criteria=json.dumps([f"File exists: {criteria_path}"]),
        status=status,
        priority=priority,
        risk_category="low",
    )
    update_feature(
        feature.id,
        conf_spec_understanding=0.9,
        conf_impl_correctness=0.9,
        conf_test_adequacy=0.9,
        readiness_score=0.9,
    )
    return get_feature(feature.id)


# ============================================================
# Step 1: First run — verification fails, feature lands in needs_human
# ============================================================


class TestVerificationFailureGatesCompletion:
    """When the sub-agent succeeds but the required artifact is missing,
    verification must gate completion. The feature is marked needs_human
    (NOT completed), and dependents are NOT cascaded to ready.
    """

    @pytest.mark.asyncio
    async def test_missing_artifact_lands_in_needs_human_and_blocks_cascade(
        self, tmp_db, real_workspace
    ):
        """Sub-agent succeeds but does not create src/foo.py.

        Real ``run_verification_checklist`` runs (no patching) and fails
        the acceptance-criterion check; feature must end in needs_human.
        Dependent feature must remain ``pending`` because cascade was
        skipped.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="VerificationGatesProject",
                workspace_path=str(real_workspace),
            )

            # Feature A: foundation feature whose acceptance criterion
            # requires src/foo.py to exist
            feature_a = _make_high_readiness_feature(
                project_id=project.id,
                name="Feature A",
                criteria_path="src/foo.py",
                status="ready",
                priority=10,
            )

            # Feature B: depends on Feature A — must NOT be cascaded if A
            # never truly completes
            feature_b = _make_high_readiness_feature(
                project_id=project.id,
                name="Feature B",
                criteria_path="src/bar.py",
                status="pending",
                priority=20,
            )
            add_feature_dependency(
                feature_id=feature_b.id,
                depends_on_feature_id=feature_a.id,
            )

            # Sanity: only Feature A is ready before the loop runs
            ready_before = get_ready_features(project.id)
            assert len(ready_before) == 1
            assert ready_before[0].id == feature_a.id

            spawn_count = 0

            async def mock_spawn_no_file(*args, **kwargs):
                """Sub-agent reports success but does NOT create src/foo.py."""
                nonlocal spawn_count
                spawn_count += 1
                return _make_spawn_result(
                    text=(
                        "Implemented feature (allegedly), but did NOT create "
                        "src/foo.py"
                    ),
                    is_error=False,
                    cost=0.50,
                )

            loop = OrchestrationLoop(
                project_id=project.id,
                workspace=str(real_workspace),
            )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_no_file,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                # NOTE: run_verification_checklist is NOT patched — it runs
                # against the real workspace which lacks src/foo.py.
                termination = await loop.run()

            # Sub-agent was actually invoked at least once for Feature A
            assert spawn_count >= 1

            # Feature A must NOT be completed — verification gates it
            f_a_after = get_feature(feature_a.id)
            assert f_a_after.status == "needs_human", (
                f"Expected Feature A to be needs_human (verification gate), "
                f"got {f_a_after.status!r}"
            )

            # Feature B must remain pending — cascade is suppressed when
            # verification fails
            f_b_after = get_feature(feature_b.id)
            assert f_b_after.status == "pending", (
                f"Dependent Feature B must NOT be cascaded to ready when its "
                f"dependency failed verification; got {f_b_after.status!r}"
            )

            # No ready features remain — Feature A is needs_human, B is
            # blocked on A. Loop must terminate as ALL_BLOCKED, NOT
            # ALL_COMPLETED. This is the project-level "work is unfinished"
            # signal.
            assert termination == LoopTermination.ALL_BLOCKED, (
                f"Loop must report ALL_BLOCKED when verification fails on "
                f"the only ready feature; got {termination!r}"
            )

            # Project state reflects unfinished work: not every feature is
            # completed, and at least one needs human attention.
            all_features = list_features(project_id=project.id)
            statuses = {f.id: f.status for f in all_features}
            assert "needs_human" in statuses.values()
            assert not all(s == "completed" for s in statuses.values()), (
                "Project still has unfinished features"
            )

            # Evidence trail: an execution_error evidence (status=needs_human)
            # was recorded, plus a verification_checklist evidence with
            # passed=False.
            evidence_a = query_evidence(feature_id=feature_a.id)
            error_evidence = [
                e for e in evidence_a if e.type == "execution_error"
            ]
            assert len(error_evidence) >= 1
            err_payload = json.loads(error_evidence[-1].content)
            assert err_payload["status"] == "needs_human"
            assert "Verification failed" in (err_payload.get("error_message") or "")

            verif_evidence = [
                e for e in evidence_a if e.type == "verification_checklist"
            ]
            assert len(verif_evidence) >= 1, (
                "verification_checklist evidence must be recorded even when "
                "verification fails"
            )
            verif_payload = json.loads(verif_evidence[-1].content)
            assert verif_payload["passed"] is False

    # ============================================================
    # Step 2: Second run — sub-agent creates the file, verification passes,
    #         feature completes and dependents cascade.
    # ============================================================

    @pytest.mark.asyncio
    async def test_second_run_creates_file_completes_and_cascades(
        self, tmp_db, real_workspace
    ):
        """After verification fails on the first run, a second run with a
        sub-agent that DOES create the required file must succeed:
        - feature transitions to completed
        - dependent feature cascades to ready
        - subsequent dependent feature also completes if a single loop
          processes both.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            project = create_project(
                name="VerificationGatesProjectResume",
                workspace_path=str(real_workspace),
            )

            feature_a = _make_high_readiness_feature(
                project_id=project.id,
                name="Feature A",
                criteria_path="src/foo.py",
                status="ready",
                priority=10,
            )
            feature_b = _make_high_readiness_feature(
                project_id=project.id,
                name="Feature B",
                criteria_path="src/bar.py",
                status="pending",
                priority=20,
            )
            add_feature_dependency(
                feature_id=feature_b.id,
                depends_on_feature_id=feature_a.id,
            )

            # ---- Run 1: sub-agent does NOT create src/foo.py ----
            async def mock_spawn_no_file(*args, **kwargs):
                return _make_spawn_result(
                    text="Pretended to do the work; no file written",
                    is_error=False,
                    cost=0.50,
                )

            loop1 = OrchestrationLoop(
                project_id=project.id,
                workspace=str(real_workspace),
            )
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_no_file,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ):
                termination1 = await loop1.run()

            assert termination1 == LoopTermination.ALL_BLOCKED
            assert get_feature(feature_a.id).status == "needs_human"
            assert get_feature(feature_b.id).status == "pending"

            # ---- Operator intervention: re-ready Feature A so the loop
            # picks it up again on the next run ----
            update_feature(
                feature_a.id,
                status="ready",
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )

            # ---- Run 2: sub-agent DOES create the required file(s) ----
            async def mock_spawn_creates_files(*args, **kwargs):
                target_id = kwargs.get("target_id")
                feature = get_feature(target_id)
                # Map Feature A -> src/foo.py, Feature B -> src/bar.py
                criterion = json.loads(feature.acceptance_criteria)[0]
                # criterion looks like "File exists: src/foo.py"
                _, _, rel = criterion.partition("File exists:")
                rel_path = rel.strip()
                target = real_workspace / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    f"def {feature.name.lower().replace(' ', '_')}():\n"
                    f"    return {feature.name!r}\n"
                )
                return _make_spawn_result(
                    text=f"Implemented {feature.name}",
                    is_error=False,
                    cost=0.50,
                )

            loop2 = OrchestrationLoop(
                project_id=project.id,
                workspace=str(real_workspace),
            )
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_creates_files,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="ghi789",
            ):
                termination2 = await loop2.run()

            # All features completed, including the dependent that was
            # cascaded to ready inside the same loop run after Feature A
            # passed verification
            assert termination2 == LoopTermination.ALL_COMPLETED, (
                f"Expected ALL_COMPLETED on the second run, got {termination2!r}"
            )

            f_a_final = get_feature(feature_a.id)
            f_b_final = get_feature(feature_b.id)
            assert f_a_final.status == "completed"
            assert f_b_final.status == "completed"

            # The required files were actually written
            assert (real_workspace / "src" / "foo.py").exists()
            assert (real_workspace / "src" / "bar.py").exists()


# ============================================================
# Regression: dead-code branch in execute_feature is gone
# ============================================================


class TestExecuteFeatureNoDeadCodeReferences:
    """Regression test for a NameError dead-code branch that was removed
    from ``OrchestrationLoop.execute_feature``.

    A previous version of the verification-fail branch referenced names
    that did not exist in the function's local scope (``SubAgentResult``,
    ``time``, ``start_time``), which would raise ``NameError`` if ever
    hit. We removed that branch; this test guards against re-introduction.

    We use ``inspect.getsource`` + ``ast`` rather than substring search so
    the test stays robust against comments/docstrings that may legitimately
    mention these names in the future.
    """

    FORBIDDEN_NAMES = frozenset({"SubAgentResult", "start_time"})
    # 'time' is checked separately because importing it as a *module*
    # at the top of the file is fine; we only forbid bare references
    # from inside execute_feature.
    FORBIDDEN_MODULE_NAMES = frozenset({"time"})

    def _execute_feature_ast(self) -> ast.AST:
        src = inspect.getsource(OrchestrationLoop.execute_feature)
        # inspect.getsource returns the function with its leading indentation
        # preserved as-is. Dedent so ast.parse sees a top-level def.
        import textwrap

        src = textwrap.dedent(src)
        return ast.parse(src)

    def test_execute_feature_does_not_reference_removed_names(self):
        tree = self._execute_feature_ast()

        # Walk every Name and Attribute node and confirm none of the
        # forbidden bare names appear.
        offending: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id in self.FORBIDDEN_NAMES:
                    offending.append(
                        f"Name {node.id!r} at line {node.lineno}"
                    )
                if node.id in self.FORBIDDEN_MODULE_NAMES:
                    offending.append(
                        f"Module name {node.id!r} at line {node.lineno}"
                    )
            elif isinstance(node, ast.Attribute):
                # e.g. `time.time()` would parse as Attribute(value=Name('time')...)
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id in self.FORBIDDEN_MODULE_NAMES
                ):
                    offending.append(
                        f"Attribute access {node.value.id}.{node.attr} "
                        f"at line {node.lineno}"
                    )

        assert not offending, (
            "execute_feature still references removed dead-code names "
            "(would raise NameError on the verification-fail path):\n  "
            + "\n  ".join(offending)
        )

    def test_execute_feature_source_is_well_formed(self):
        """Sanity check: the function must still parse and contain the
        verification path so this regression test is actually exercising
        the right code."""
        src = inspect.getsource(OrchestrationLoop.execute_feature)
        # The function must mention run_verification_checklist somewhere —
        # otherwise we'd be guarding against an empty target.
        assert "run_verification_checklist" in src, (
            "execute_feature no longer references run_verification_checklist; "
            "this regression test needs to be updated to reflect the new "
            "verification entry point."
        )
        # And the verification-fail branch must still exist
        assert "verification_passed" in src


# ============================================================
# Issue 1 fix: full interrupt-resume-spec-change flow with REAL
# verification (no _passing_verification stub).
#
# The F118 e2e suite stubs out ``run_verification_checklist`` to always
# pass because its workspaces are lightweight /tmp paths that don't
# contain implementation files. That means the resume + spec-change flow
# is never tested end-to-end with real verification.
#
# This test runs the full lifecycle against a real workspace and lets
# the real verifier decide pass/fail per-feature based on whether the
# mock_spawn actually produced the file required by acceptance criteria.
# ============================================================


@pytest.fixture
def real_workspace_nonstub(tmp_path):
    """Real Python workspace whose baseline source is non-trivial.

    The shared ``real_workspace`` fixture writes ``baseline.py`` with a
    single ``return '<literal>'`` body, which the stub-AST analyzer flags
    at warning severity — that warning still flips
    ``no_stubs_in_source`` to ``passed=False`` in the verifier, so it
    masks any other verification result. We use a non-trivial body here
    so verification can cleanly pass for features whose mock_spawn
    actually produces the required files.
    """
    ws = tmp_path / "f124-nonstub-workspace"
    ws.mkdir()

    src_dir = ws / "src"
    src_dir.mkdir()
    (src_dir / "baseline.py").write_text(
        "def baseline(name, count):\n"
        "    parts = [f'{name}-{i}' for i in range(count)]\n"
        "    return '|'.join(parts)\n"
    )

    tests_dir = ws / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_baseline.py").write_text(
        "def baseline(name, count):\n"
        "    parts = [f'{name}-{i}' for i in range(count)]\n"
        "    return '|'.join(parts)\n"
        "\n"
        "def test_baseline_joins():\n"
        "    assert baseline('x', 3) == 'x-0|x-1|x-2'\n"
        "\n"
        "def test_baseline_zero():\n"
        "    assert baseline('x', 0) == ''\n"
    )
    return ws


def _write_real_feature_source(workspace, rel_path: str, name: str) -> None:
    """Write a non-stub Python source file at ``workspace/rel_path``.

    The body must be substantial enough that the stub-AST heuristic
    does not flag it (no single-literal return). We write a small
    string-building function so verification's no_stubs_in_source check
    passes cleanly.
    """
    target = workspace / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    safe = name.lower().replace(" ", "_")
    target.write_text(
        f"def {safe}(prefix=''):\n"
        f"    pieces = [prefix + str(i) for i in range({len(name)})]\n"
        f"    return ' '.join(pieces) or {name!r}\n"
    )


class TestInterruptResumeSpecChangeWithRealVerification:
    """Full interrupt-resume-spec-change flow without patching verification.

    Coverage:
      1. Features that pass verification get resumed correctly (file is
         created on retry, feature transitions to completed).
      2. Features that fail verification stay needs_human after resume
         (file deliberately not created on retry; verification gates).
      3. Spec changes detected in resume mode preserve the verification
         state (already-needs_human features are NOT reset by spec changes,
         and a modified feature is reset to pending while completed
         features stay completed).
    """

    @pytest.mark.asyncio
    async def test_full_flow_real_verification(
        self, tmp_db, real_workspace_nonstub, tmp_path
    ):
        real_workspace = real_workspace_nonstub
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            # ---- Build a 4-feature spec on disk so we can mutate it ----
            # IMPORTANT: keep DB description/priority/acceptance_criteria
            # in EXACT sync with the spec file content. ``detect_spec_changes``
            # diffs the DB representation against the spec file, so any
            # mismatch (e.g. DB description != spec description) shows up
            # as every feature being "modified" on the first detect call.
            spec = {
                "name": "RealVerifResumeProject",
                "version": "1.0",
                "features": [
                    {
                        "name": f"Feature {i}",
                        "description": f"Feature {i} description",
                        "priority": i * 10,
                        "acceptance_criteria": [f"File exists: src/feat{i}.py"],
                    }
                    for i in range(1, 5)
                ],
            }
            spec_path = tmp_path / "real_verif_spec.yaml"
            spec_path.write_text(yaml.dump(spec, default_flow_style=False))

            project = create_project(
                name="RealVerifResumeProject",
                workspace_path=str(real_workspace),
                spec_path=str(spec_path),
            )
            update_project(project.id, spec_hash=compute_spec_hash(spec_path))

            features: list = []
            for feat in spec["features"]:
                # Use the exact same description/priority as the spec.
                f = create_feature(
                    project_id=project.id,
                    name=feat["name"],
                    description=feat["description"],
                    acceptance_criteria=json.dumps(feat["acceptance_criteria"]),
                    status="ready",
                    priority=feat["priority"],
                    risk_category="low",
                )
                update_feature(
                    f.id,
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )
                features.append(get_feature(f.id))

            assert len(get_ready_features(project.id)) == 4

            # =======================================================
            # PHASE 1: First loop run.
            # - Feature 1: sub-agent CREATES src/feat1.py -> verification
            #   passes -> completed.
            # - Feature 2: sub-agent does NOT create src/feat2.py ->
            #   verification fails -> needs_human (no cascade since none
            #   depend on it).
            # - Feature 3: sub-agent CREATES src/feat3.py, then we request
            #   shutdown to interrupt before Feature 4. Feature 3 should
            #   complete (verification passes) before the shutdown is
            #   honored, leaving Feature 4 untouched (still 'ready').
            # =======================================================

            loop1 = OrchestrationLoop(
                project_id=project.id,
                workspace=str(real_workspace),
            )

            spawn_count = 0

            async def mock_spawn_phase1(*args, **kwargs):
                """Real-file-creating sub-agent for some features only."""
                nonlocal spawn_count
                spawn_count += 1
                target_id = kwargs.get("target_id")
                feature = get_feature(target_id)
                criterion = json.loads(feature.acceptance_criteria)[0]
                _, _, rel = criterion.partition("File exists:")
                rel_path = rel.strip()

                if feature.name == "Feature 1":
                    _write_real_feature_source(
                        real_workspace, rel_path, feature.name
                    )
                    return _make_spawn_result(
                        text="Feature 1 implemented", cost=0.50,
                    )
                if feature.name == "Feature 2":
                    # Deliberately do NOT create the file -> verification
                    # will fail and the feature lands in needs_human.
                    return _make_spawn_result(
                        text="Pretended to do Feature 2 — no file written",
                        cost=0.50,
                    )
                if feature.name == "Feature 3":
                    _write_real_feature_source(
                        real_workspace, rel_path, feature.name
                    )
                    # Request shutdown so Feature 4 doesn't run.
                    loop1.request_shutdown()
                    return _make_spawn_result(
                        text="Feature 3 implemented; shutting down", cost=0.50,
                    )
                # Feature 4 should never run in phase 1
                raise AssertionError(
                    f"phase1 unexpectedly executed {feature.name!r}"
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_phase1,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "abc123"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="def456",
            ), patch(
                "bob3.orchestrator.run_loop.stop_mcp_server",
            ):
                term1 = await loop1.run()

            # We expect SHUTDOWN_REQUESTED because Feature 3 triggered
            # request_shutdown after completing.
            assert term1 == LoopTermination.SHUTDOWN_REQUESTED, (
                f"Expected SHUTDOWN_REQUESTED, got {term1!r}"
            )
            # All three features in phase 1 ran exactly once each.
            assert spawn_count == 3

            # Real verification gated each feature correctly:
            # - Feature 1: file created -> completed
            # - Feature 2: file missing -> needs_human
            # - Feature 3: file created -> completed
            # - Feature 4: never ran -> still ready
            assert get_feature(features[0].id).status == "completed"
            assert get_feature(features[1].id).status == "needs_human", (
                "Feature 2 had no file created; verification must gate it "
                "to needs_human"
            )
            assert get_feature(features[2].id).status == "completed"
            assert get_feature(features[3].id).status == "ready"

            # Real-verification evidence was recorded for the verified
            # features (passed=True for 1+3, passed=False for 2).
            for fid, expect_pass in (
                (features[0].id, True),
                (features[1].id, False),
                (features[2].id, True),
            ):
                ve = [
                    e for e in query_evidence(feature_id=fid)
                    if e.type == "verification_checklist"
                ]
                assert len(ve) >= 1, (
                    f"verification evidence missing for feature {fid}"
                )
                payload = json.loads(ve[-1].content)
                assert payload["passed"] is expect_pass, (
                    f"feature {fid}: expected passed={expect_pass}, "
                    f"got {payload['passed']}"
                )

            # =======================================================
            # PHASE 2: Mutate the spec mid-flight, then resume.
            # - Modify Feature 4 (ready, untouched) -> resets to pending
            #   on detect_spec_changes.
            # - Modify Feature 1 (completed) -> resets to pending; this
            #   is by design — the spec change invalidates prior work.
            # - Feature 2 stays needs_human (NOT touched by spec change
            #   since we don't modify it). This is the "preserve
            #   verification state" invariant.
            # - Feature 3 stays completed (NOT modified in spec).
            # =======================================================

            spec["features"][0]["description"] = "Feature 1 — REVISED scope"
            spec["features"][3]["description"] = "Feature 4 — REVISED scope"
            spec_path.write_text(yaml.dump(spec, default_flow_style=False))

            changes = detect_spec_changes(project.id)
            assert changes is not None
            modified_names = [c["name"] for c in changes["modified"]]
            assert "Feature 1" in modified_names
            assert "Feature 4" in modified_names
            # Feature 2 (needs_human) and Feature 3 (completed) were NOT
            # mutated in the spec, so they must NOT show up as modified.
            assert "Feature 2" not in modified_names
            assert "Feature 3" not in modified_names

            # Verify the verification-state-preservation invariant:
            # Feature 2 is still needs_human after spec-change detection
            # (its row was untouched), and Feature 3 is still completed.
            assert get_feature(features[1].id).status == "needs_human", (
                "Spec change must preserve needs_human verification state "
                "on features it didn't modify"
            )
            assert get_feature(features[2].id).status == "completed"

            # The two features we *did* modify in the spec should now be
            # back to pending (work invalidated).
            assert get_feature(features[0].id).status == "pending"
            assert get_feature(features[3].id).status == "pending"

            # =======================================================
            # PHASE 3: Operator re-readies the affected features (Feature
            # 1 reset by spec change, Feature 2 needs human + reset to
            # ready by an operator, Feature 4 reset by spec change).
            # Then the loop runs again with REAL verification.
            #   - Feature 1: sub-agent CREATES file -> passes -> completed
            #   - Feature 2: sub-agent CREATES file this time -> passes
            #     -> completed (proves "feature that was needs_human can
            #     resume to completed once verification passes")
            #   - Feature 4: sub-agent does NOT create file -> stays
            #     needs_human after resume (proves the negative case
            #     in resume mode too).
            # =======================================================

            # Operator re-readies the previously-failed and reset features.
            for fid in (features[0].id, features[1].id, features[3].id):
                update_feature(
                    fid,
                    status="ready",
                    conf_spec_understanding=0.9,
                    conf_impl_correctness=0.9,
                    conf_test_adequacy=0.9,
                    readiness_score=0.9,
                )

            # Sanity: ready set is exactly {1, 2, 4}; Feature 3 is done.
            ready_ids = {f.id for f in get_ready_features(project.id)}
            assert ready_ids == {features[0].id, features[1].id, features[3].id}

            loop2 = OrchestrationLoop(
                project_id=project.id,
                workspace=str(real_workspace),
            )

            phase2_seen: list[str] = []

            async def mock_spawn_phase2(*args, **kwargs):
                target_id = kwargs.get("target_id")
                feature = get_feature(target_id)
                phase2_seen.append(feature.name)
                criterion = json.loads(feature.acceptance_criteria)[0]
                _, _, rel = criterion.partition("File exists:")
                rel_path = rel.strip()

                if feature.name in ("Feature 1", "Feature 2"):
                    _write_real_feature_source(
                        real_workspace, rel_path, feature.name
                    )
                    return _make_spawn_result(
                        text=f"{feature.name} implemented", cost=0.50,
                    )
                if feature.name == "Feature 4":
                    # Still don't create the file -> still fails verification
                    return _make_spawn_result(
                        text="Feature 4 — pretended again", cost=0.50,
                    )
                raise AssertionError(
                    f"phase2 unexpectedly executed {feature.name!r}"
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_phase2,
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": "fed987"},
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value="cba321",
            ):
                term2 = await loop2.run()

            # Feature 4 stays needs_human, so the loop must terminate
            # ALL_BLOCKED (not ALL_COMPLETED).
            assert term2 == LoopTermination.ALL_BLOCKED, (
                f"Expected ALL_BLOCKED (Feature 4 stuck in needs_human), "
                f"got {term2!r}"
            )
            assert set(phase2_seen) == {"Feature 1", "Feature 2", "Feature 4"}

            # Final state per the three required invariants in Issue 1:
            # 1. Features that pass verification get resumed correctly:
            assert get_feature(features[0].id).status == "completed", (
                "Feature 1 (reset by spec change) must complete after "
                "successful resume + verification"
            )
            assert get_feature(features[1].id).status == "completed", (
                "Feature 2 (was needs_human) must complete after operator "
                "intervention + successful resume + verification"
            )
            # 2. Features that fail verification stay needs_human after resume:
            assert get_feature(features[3].id).status == "needs_human", (
                "Feature 4 must stay needs_human when verification keeps "
                "failing after resume"
            )
            # 3. Spec changes detected in resume mode preserve the
            #    verification state of features they didn't touch:
            assert get_feature(features[2].id).status == "completed", (
                "Feature 3 (untouched by spec change) must still be "
                "completed after the spec-change resume cycle"
            )

            # The required files for the passing features actually exist
            assert (real_workspace / "src" / "feat1.py").exists()
            assert (real_workspace / "src" / "feat2.py").exists()
            assert (real_workspace / "src" / "feat3.py").exists()
            # And the failing one really does not.
            assert not (real_workspace / "src" / "feat4.py").exists()
