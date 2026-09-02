"""Focused regression tests for Bob's hardened candidate boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob.candidate_change_manifest import (
    build_candidate_change_bundle,
    snapshot_candidate_tree,
)
from bob.candidate_exec import candidate_argv, validate_candidate_execution_policy
from bob.git_ops import (
    GitCommitError,
    GitRepoError,
    commit_feature,
    finalize_exact_commit_intent,
)
from bob.orchestrator.independent_test_writer import (
    CriterionCoverage,
    TestWriterProtocolError as _TestWriterProtocolError,
    restore_failed_writer_namespace,
    run_writer_tests_green,
    run_independent_test_writer,
    validate_writer_tests_red,
    WriterTestExecution,
)
from bob.orchestrator.claude_executor import ExecutionResult


def _executable(path: Path, text: str = "#!/bin/sh\nexec \"$@\"\n") -> Path:
    path.write_text(text)
    path.chmod(0o700)
    return path


def test_hardened_pytest_is_pinned_isolated_and_wrapped(monkeypatch, tmp_path):
    wrapper = _executable(tmp_path / "candidate-wrapper")
    monkeypatch.setenv("BOB_EXTERNAL_VERIFIER_REQUIRED", "1")
    monkeypatch.setenv("BOB_CANDIDATE_EXEC_WRAPPER", str(wrapper))
    monkeypatch.setenv("BOB_CANDIDATE_TEST_PYTHON", sys.executable)

    argv = candidate_argv([sys.executable, "-B", "-m", "pytest", "-q"])

    assert argv[0] == str(wrapper)
    assert argv[1] == str(Path(sys.executable))
    assert argv[2:5] == ["-I", "-B", "-c"]
    assert 'sys.path.insert(0, "/workspace/app/src")' in argv[5]
    assert argv[6:] == ["-q"]


def test_hardened_unknown_python_and_missing_wrapper_fail_before_spawn(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BOB_EXTERNAL_VERIFIER_REQUIRED", "1")
    monkeypatch.setenv("BOB_CANDIDATE_TEST_PYTHON", sys.executable)
    monkeypatch.delenv("BOB_CANDIDATE_EXEC_WRAPPER", raising=False)

    with pytest.raises(RuntimeError, match="CANDIDATE_EXEC_WRAPPER"):
        candidate_argv([sys.executable, "-m", "pytest"])

    wrapper = _executable(tmp_path / "candidate-wrapper")
    monkeypatch.setenv("BOB_CANDIDATE_EXEC_WRAPPER", str(wrapper))
    with pytest.raises(ValueError, match="unrecognized dynamic Python"):
        candidate_argv([sys.executable, "-c", "print('candidate')"])

    with patch("bob.enhanced_verification.subprocess.Popen") as popen:
        monkeypatch.delenv("BOB_CANDIDATE_EXEC_WRAPPER")
        from bob.enhanced_verification import _run_with_pgroup_timeout

        with pytest.raises(RuntimeError, match="CANDIDATE_EXEC_WRAPPER"):
            _run_with_pgroup_timeout(
                [sys.executable, "-m", "pytest", "-q"], tmp_path, 1
            )
        popen.assert_not_called()


def test_hardened_policy_rejects_partial_or_candidate_owned_controller_state(
    monkeypatch, tmp_path
):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    wrapper = _executable(tmp_path / "candidate-wrapper")
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    database = tmp_path / "bob.db"
    database.touch()
    monkeypatch.setenv("BOB_EXTERNAL_VERIFIER_REQUIRED", "1")
    monkeypatch.setenv("BOB_CANDIDATE_EXEC_WRAPPER", str(wrapper))
    monkeypatch.setenv("BOB_CANDIDATE_TEST_PYTHON", sys.executable)
    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    monkeypatch.setenv("BOB_CLAUDE_HERMETIC", "1")
    monkeypatch.setenv("BOB_DYNAMIC_DECOMPOSITION", "disabled")
    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("BOB_DATABASE_PATH", str(database))
    monkeypatch.setenv("BOB_SESSIONS_ROOT", str(sessions))

    with pytest.raises(RuntimeError, match="BOB_EVALUATOR_REQUIRED"):
        validate_candidate_execution_policy(workspace=candidate)

    monkeypatch.setenv("BOB_EVALUATOR_REQUIRED", "1")
    validate_candidate_execution_policy(workspace=candidate)

    candidate_database = candidate / "bob.db"
    candidate_database.touch()
    monkeypatch.setenv("BOB_DATABASE_PATH", str(candidate_database))
    with pytest.raises(RuntimeError, match="controller-owned outside"):
        validate_candidate_execution_policy(workspace=candidate)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("BOB_INDEPENDENT_TEST_WRITER", "required"),
        ("BOB_EVALUATOR_REQUIRED", "1"),
        ("BOB_CLAUDE_HERMETIC", "1"),
        ("BOB_DYNAMIC_DECOMPOSITION", "disabled"),
        ("BOB_REQUIRED_MODEL", "claude-opus-4-8"),
        ("BOB_CANDIDATE_EXEC_WRAPPER", "/controller/wrapper"),
        ("BOB_CANDIDATE_TEST_PYTHON", "/controller/python"),
    ],
)
def test_any_partial_hardened_member_requires_master_boundary(
    monkeypatch, name, value
):
    for member in (
        "BOB_EXTERNAL_VERIFIER_REQUIRED",
        "BOB_INDEPENDENT_TEST_WRITER",
        "BOB_EVALUATOR_REQUIRED",
        "BOB_CLAUDE_HERMETIC",
        "BOB_DYNAMIC_DECOMPOSITION",
        "BOB_REQUIRED_MODEL",
        "BOB_CANDIDATE_EXEC_WRAPPER",
        "BOB_CANDIDATE_TEST_PYTHON",
    ):
        monkeypatch.delenv(member, raising=False)
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="partial hardened candidate policy"):
        validate_candidate_execution_policy()


@pytest.mark.parametrize("sweep_name", ["_final_exit_sweep", "flip_orphans_to_failed"])
def test_hardened_exit_sweeps_cannot_disk_promote(
    monkeypatch, sweep_name
):
    from bob.orchestrator import run_loop

    monkeypatch.setenv("BOB_INDEPENDENT_TEST_WRITER", "required")
    feature = SimpleNamespace(
        id="feature-1",
        name="feature",
        acceptance_criteria='["criterion"]',
    )
    monkeypatch.setattr(
        run_loop.db, "list_features", lambda **kwargs: [feature]
    )
    monkeypatch.setattr(
        run_loop, "find_subagent_pid_for_feature", lambda feature_id: []
    )
    monkeypatch.setattr(run_loop, "_sweep_orphan_subagents", lambda: [])
    disk_promote = MagicMock(return_value=True)
    monkeypatch.setattr(run_loop, "_check_executing_feature_acs", disk_promote)
    update = MagicMock()
    monkeypatch.setattr(run_loop.db, "update_feature", update)

    getattr(run_loop, sweep_name)("project-1")

    disk_promote.assert_not_called()
    assert any(call.kwargs.get("status") == "failed" for call in update.call_args_list)


def test_candidate_bundle_includes_untracked_and_rejects_binary(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    source = app / "model.py"
    source.write_text("VALUE = 1\n")
    baseline = snapshot_candidate_tree(cwd=tmp_path)
    source.write_text("VALUE = 2\n")
    (app / "new.py").write_text("NEW = True\n")
    final = snapshot_candidate_tree(cwd=tmp_path)

    bundle = build_candidate_change_bundle(
        feature_id="feature-1", cwd=tmp_path, baseline=baseline, final=final
    )

    assert {item["path"] for item in bundle.changes} == {
        "app/model.py",
        "app/new.py",
    }
    assert {item["path"] for item in bundle.content} == {
        "app/model.py",
        "app/new.py",
    }
    assert json.loads(bundle.canonical_json)["change_bundle_sha256"] == bundle.sha256

    (app / "new.py").write_bytes(b"\x00\xff")
    binary_final = snapshot_candidate_tree(cwd=tmp_path)
    with pytest.raises(ValueError, match="evaluator-blind"):
        build_candidate_change_bundle(
            feature_id="feature-1",
            cwd=tmp_path,
            baseline=baseline,
            final=binary_final,
        )


def test_candidate_bundle_rejects_uncommittable_directory_only_change(tmp_path):
    (tmp_path / "app").mkdir()
    baseline = snapshot_candidate_tree(cwd=tmp_path)
    (tmp_path / "empty_candidate_directory").mkdir()
    final = snapshot_candidate_tree(cwd=tmp_path)

    with pytest.raises(ValueError, match="directory-only"):
        build_candidate_change_bundle(
            feature_id="feature-1", cwd=tmp_path, baseline=baseline, final=final
        )


def test_candidate_snapshot_does_not_hide_nested_runtime_named_source(tmp_path):
    nested = tmp_path / "src" / "node_modules"
    nested.mkdir(parents=True)
    source = nested / "cheat.py"
    source.write_text("CHEAT = True\n")

    manifest = snapshot_candidate_tree(cwd=tmp_path)

    assert "src/node_modules/cheat.py" in {entry.path for entry in manifest}


def test_candidate_snapshot_rejects_hardlinks_and_test_manifest_rejects_symlink(
    tmp_path,
):
    original = tmp_path / "a.py"
    original.write_text("A = 1\n")
    os.link(original, tmp_path / "b.py")
    with pytest.raises(ValueError, match="single-link"):
        snapshot_candidate_tree(cwd=tmp_path)

    original.unlink()
    (tmp_path / "b.py").unlink()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "real.py").write_text("x = 1\n")
    (tests / "test_link.py").symlink_to(tests / "real.py")
    from bob.orchestrator.independent_test_writer import snapshot_test_roots

    with pytest.raises(ValueError, match="symlink forbidden"):
        snapshot_test_roots(cwd=tmp_path, allowed_test_roots=("tests",))


def test_red_gate_rejects_mixed_pass_and_fail_nodes(monkeypatch, tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    test_file = tests / "test_mixed.py"
    test_file.write_text(
        "def test_red():\n    actual = 1\n    assert actual == 2\n\n"
        "def test_padding():\n    actual = 1\n    assert actual == 1\n"
    )
    nodes = (
        "tests/test_mixed.py::test_padding",
        "tests/test_mixed.py::test_red",
    )
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="\n".join(nodes), stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=(
                    f"{nodes[0]} PASSED\n{nodes[1]} FAILED\n"
                    f"FAILED {nodes[1]} - AssertionError"
                ),
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer._run_candidate_pytest",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(_TestWriterProtocolError, match="every independently collected"):
        validate_writer_tests_red(
            cwd=tmp_path,
            test_files=("tests/test_mixed.py",),
            criterion_coverage=(CriterionCoverage(0, nodes),),
        )


def test_red_gate_does_not_trust_forged_failed_stdout(monkeypatch, tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    test_file = tests / "test_spoof.py"
    test_file.write_text(
        "def test_real_failure():\n    assert observed() == 2\n\n"
        "def test_passing_padding():\n"
        "    print('FAILED tests/test_spoof.py::test_passing_padding')\n"
        "    assert observed() == observed()\n"
    )
    nodes = (
        "tests/test_spoof.py::test_passing_padding",
        "tests/test_spoof.py::test_real_failure",
    )
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="\n".join(nodes), stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout=f"FAILED {nodes[0]}\n{nodes[0]} PASSED",
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer._run_candidate_pytest",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(_TestWriterProtocolError, match="every independently collected"):
        validate_writer_tests_red(
            cwd=tmp_path,
            test_files=("tests/test_spoof.py",),
            criterion_coverage=(CriterionCoverage(0, nodes),),
        )


def test_green_gate_rejects_skip_only_node(monkeypatch, tmp_path):
    node = "tests/test_behavior.py::test_behavior"
    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer._run_candidate_pytest",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, stdout=f"{node} SKIPPED\n1 skipped", stderr=""
        ),
    )
    execution = WriterTestExecution(
        collected_node_ids=(node,),
        test_argv=(sys.executable, "-m", "pytest", node),
        red_exit_code=1,
        red_output_sha256="1" * 64,
        red_failed_node_ids=(node,),
    )

    green = run_writer_tests_green(cwd=tmp_path, execution=execution)

    assert not green.passed
    assert green.passed_node_ids == ()


def test_failed_writer_namespace_is_restored_then_fresh_retry_succeeds(
    monkeypatch, tmp_path
):
    calls = 0

    class FakeExecutor:
        def __init__(self, *, default_options):
            pass

        async def execute(self, prompt, *, options):
            nonlocal calls
            calls += 1
            assignment = json.loads(
                prompt.split("ASSIGNMENT_JSON\n", 1)[1].split(
                    "\nEND_ASSIGNMENT_JSON", 1
                )[0]
            )
            nonce = re.search(
                r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE
            ).group(1)
            relative = f"{assignment['test_namespace']}/test_behavior.py"
            (tmp_path / relative).write_text(
                "def test_behavior():\n    actual = 1\n    assert actual == 2\n"
            )
            declared = relative if calls == 2 else relative + ".forged"
            payload = {
                "schema_version": "bob.independent-test-writer.v1",
                "role": "independent_test_writer",
                "principal_nonce": nonce,
                "status": "completed",
                "feature_id": "feature-1",
                "test_files": [declared],
                "test_command": ["pytest", declared],
                "criterion_coverage": [
                    {
                        "criterion_index": 0,
                        "test_ids": [f"{declared}::test_behavior"],
                    }
                ],
                "notes": [],
            }
            return ExecutionResult(
                text=f"```json\n{json.dumps(payload)}\n```",
                session_id=f"writer-session-{calls}",
            )

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor", FakeExecutor
    )
    red_node = MagicMock()
    red_node.side_effect = [
        subprocess.CompletedProcess(
            [], 0, stdout="tests/bob_generated/x::ignored", stderr=""
        ),
    ]
    # The first attempt fails before test execution.  The second uses the real
    # local pytest path and produces a behavioral red failure.
    from claude_code_sdk import ClaudeCodeOptions

    options = ClaudeCodeOptions(cwd=str(tmp_path), model="claude-opus-4-8")
    first = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature",
            feature_description="Behavior",
            acceptance_criteria=("behavior",),
            cwd=tmp_path,
            options=options,
        )
    )
    assert first.outcome == "protocol_error", first.error
    restored, _ = restore_failed_writer_namespace(
        cwd=tmp_path, allowed_test_roots=("tests",), result=first
    )
    assert restored
    second = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature",
            feature_description="Behavior",
            acceptance_criteria=("behavior",),
            cwd=tmp_path,
            options=options,
        )
    )
    assert second.ok
    assert second.evidence.session_id == "writer-session-2"


@pytest.mark.asyncio
async def test_finite_cost_monitor_observes_running_cost_advance(monkeypatch):
    from bob.orchestrator import run_loop

    running = SimpleNamespace(
        id="run-1",
        target_type="feature",
        target_id="feature-1",
        cost_usd=0.0,
    )
    costs = iter((0.0, 12.0))
    monkeypatch.setattr(run_loop.db, "query_agent_runs", lambda **_: [running])

    def get_run(_):
        running.cost_usd = next(costs)
        return running

    monkeypatch.setattr(run_loop.db, "get_agent_run", get_run)
    monkeypatch.setattr(run_loop, "_should_terminate_subagent", lambda cost: cost > 10)
    terminate = MagicMock()
    monkeypatch.setattr(run_loop, "_terminate_subagent_on_cost_cap", terminate)
    monkeypatch.setattr(
        "bob.orchestrator.subagent_reaper.get_tracked_pid", lambda _: 123,
        raising=False,
    )

    await run_loop._monitor_subagent_cost_cap(
        project_id="project-1",
        feature_id="feature-1",
        agent_run_id=None,
        check_interval_s=0.001,
    )

    terminate.assert_called_once_with(
        feature_id="feature-1", pid=123, reported_cost=12.0
    )


@pytest.mark.asyncio
async def test_dynamic_decomposition_disabled_never_spawns(monkeypatch, tmp_path):
    from bob.orchestrator import run_loop

    monkeypatch.setenv("BOB_DYNAMIC_DECOMPOSITION", "disabled")
    spawn = MagicMock()
    monkeypatch.setattr(run_loop, "spawn_sub_agent", spawn)
    outcome = await run_loop.handle_decomposition(
        project_id="project-1",
        feature=SimpleNamespace(
            id="feature-1",
            name="oversized",
            description="description",
            acceptance_criteria="[]",
            size_limit_justification="large",
        ),
        workspace=str(tmp_path),
    )

    assert not outcome["success"]
    assert "trusted planner" in outcome["error_message"]
    spawn.assert_not_called()


@pytest.mark.parametrize(
    "role",
    [
        "independent_test_writer",
        "implementer",
        "evaluator",
        "rca",
        "research",
        "puppeteer",
        "planner",
    ],
)
def test_required_opus_roles_pin_one_million_autocompact(monkeypatch, role):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")
    options = build_sub_agent_options(
        model="claude-opus-4-8", max_turns=None, agent_role=role
    )

    assert options.extra_args["autocompact"] == "1M"
    assert options.env["BOB_AGENT_ROLE"] == role


def test_opus_planner_pins_one_million_without_global_required_model(monkeypatch):
    from bob.orchestrator.claude_executor import build_sub_agent_options

    monkeypatch.delenv("BOB_REQUIRED_MODEL", raising=False)
    options = build_sub_agent_options(
        cwd=None, model="claude-opus-4-8", agent_role="planner"
    )

    assert options.extra_args["autocompact"] == "1M"


def test_final_sdk_boundary_overrides_mutated_opus_autocompact(monkeypatch):
    from claude_code_sdk import ClaudeCodeOptions
    from bob.orchestrator.claude_executor import _enforce_required_model_on_options

    monkeypatch.setenv("BOB_REQUIRED_MODEL", "claude-opus-4-8")
    debug_stream = object()
    caller_options = ClaudeCodeOptions(
        model="claude-opus-4-8",
        cwd="/controller/workspace",
        extra_args={"autocompact": "100k", "unrelated": "kept"},
        debug_stderr=debug_stream,
    )

    enforced = _enforce_required_model_on_options(caller_options)

    assert enforced is not caller_options
    assert enforced.extra_args == {"autocompact": "1M", "unrelated": "kept"}
    assert enforced.debug_stderr is debug_stream
    assert caller_options.extra_args["autocompact"] == "100k"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def test_exact_commit_binds_paths_content_and_mode(tmp_path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "bob@example.test", cwd=tmp_path)
    _git("config", "user.name", "Bob Test", cwd=tmp_path)
    target = tmp_path / "tool.py"
    target.write_text("VALUE = 1\n")
    _git("add", "tool.py", cwd=tmp_path)
    _git("commit", "-m", "base", cwd=tmp_path)
    admitted_parent = _git("rev-parse", "HEAD", cwd=tmp_path)
    admitted_tree = _git("rev-parse", "HEAD^{tree}", cwd=tmp_path)
    target.write_text("VALUE = 2\n")
    target.chmod(0o755)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()

    sha = commit_feature(
        feature_id="feature-1",
        message="exact",
        workspace=str(tmp_path),
        stage_paths=("tool.py",),
        expected_file_sha256={"tool.py": digest},
        expected_file_modes={"tool.py": "100755"},
        expected_parent_sha=admitted_parent,
        expected_parent_tree_sha=admitted_tree,
        skip_hooks=True,
    )
    assert sha == _git("rev-parse", "HEAD", cwd=tmp_path)
    assert _git("ls-tree", "HEAD", "tool.py", cwd=tmp_path).startswith("100755 ")

    target.write_text("VALUE = 3\n")
    with pytest.raises(GitCommitError, match="mode mismatch"):
        commit_feature(
            feature_id="feature-2",
            message="wrong mode",
            workspace=str(tmp_path),
            stage_paths=("tool.py",),
            expected_file_sha256={
                "tool.py": hashlib.sha256(target.read_bytes()).hexdigest()
            },
            expected_file_modes={"tool.py": "100644"},
            skip_hooks=True,
        )


def test_exact_commit_rejects_head_advanced_past_authenticated_attempt_base(tmp_path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "bob@example.test", cwd=tmp_path)
    _git("config", "user.name", "Bob Test", cwd=tmp_path)
    target = tmp_path / "target.py"
    target.write_text("TARGET = 1\n")
    _git("add", "target.py", cwd=tmp_path)
    _git("commit", "-m", "authenticated base", cwd=tmp_path)
    admitted_parent = _git("rev-parse", "HEAD", cwd=tmp_path)
    admitted_tree = _git("rev-parse", "HEAD^{tree}", cwd=tmp_path)

    unauthorized = tmp_path / "unauthorized.txt"
    unauthorized.write_text("hidden parent content\n")
    _git("add", "unauthorized.txt", cwd=tmp_path)
    _git("commit", "-m", "unauthorized parent advance", cwd=tmp_path)
    unauthorized_parent = _git("rev-parse", "HEAD", cwd=tmp_path)
    unauthorized.unlink()
    target.write_text("TARGET = 2\n")

    with pytest.raises(GitCommitError, match="authenticated attempt base"):
        commit_feature(
            feature_id="feature-parent-drift",
            message="must not inherit unauthorized parent",
            workspace=str(tmp_path),
            stage_paths=("target.py",),
            expected_file_sha256={
                "target.py": hashlib.sha256(target.read_bytes()).hexdigest()
            },
            expected_file_modes={"target.py": "100644"},
            expected_parent_sha=admitted_parent,
            expected_parent_tree_sha=admitted_tree,
            skip_hooks=True,
        )

    assert _git("rev-parse", "HEAD", cwd=tmp_path) == unauthorized_parent
    assert _git("rev-list", "--count", "HEAD", cwd=tmp_path) == "2"


def test_exact_commit_uses_literal_pathspec_and_disables_ref_hooks(tmp_path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "bob@example.test", cwd=tmp_path)
    _git("config", "user.name", "Bob Test", cwd=tmp_path)
    (tmp_path / "base.py").write_text("BASE = True\n")
    _git("add", "base.py", cwd=tmp_path)
    _git("commit", "-m", "base", cwd=tmp_path)

    literal = tmp_path / ":(glob)candidate.py"
    literal.write_text("VALUE = 2\n")
    marker = tmp_path / "reference-hook-ran"
    hook = tmp_path / ".git" / "hooks" / "reference-transaction"
    hook.write_text(f"#!/bin/sh\nprintf ran > {marker}\nexit 1\n")
    hook.chmod(0o700)
    digest = hashlib.sha256(literal.read_bytes()).hexdigest()

    sha = commit_feature(
        feature_id="feature-literal",
        message="literal",
        workspace=str(tmp_path),
        stage_paths=(literal.name,),
        expected_file_sha256={literal.name: digest},
        expected_file_modes={literal.name: "100644"},
        skip_hooks=True,
    )

    assert sha == _git("rev-parse", "HEAD", cwd=tmp_path)
    assert not marker.exists()
    assert literal.name in subprocess.check_output(
        [
            "git",
            "--literal-pathspecs",
            "ls-tree",
            "--name-only",
            "HEAD",
            "--",
            literal.name,
        ],
        cwd=tmp_path,
        text=True,
    )


def test_exact_commit_ignores_shared_index_injection(tmp_path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "bob@example.test", cwd=tmp_path)
    _git("config", "user.name", "Bob Test", cwd=tmp_path)
    target = tmp_path / "target.py"
    rogue = tmp_path / "rogue.py"
    target.write_text("TARGET = 1\n")
    rogue.write_text("ROGUE = 1\n")
    _git("add", "target.py", "rogue.py", cwd=tmp_path)
    _git("commit", "-m", "base", cwd=tmp_path)
    target.write_text("TARGET = 2\n")
    rogue.write_text("ROGUE = 2\n")
    _git("add", "rogue.py", cwd=tmp_path)

    sha = commit_feature(
        feature_id="feature-index",
        message="isolated index",
        workspace=str(tmp_path),
        stage_paths=("target.py",),
        expected_file_sha256={
            "target.py": hashlib.sha256(target.read_bytes()).hexdigest()
        },
        expected_file_modes={"target.py": "100644"},
        skip_hooks=True,
    )

    changed = set(_git("diff-tree", "--no-commit-id", "--name-only", "-r", sha, cwd=tmp_path).splitlines())
    assert changed == {"target.py"}
    assert _git("show", f"{sha}:rogue.py", cwd=tmp_path) == "ROGUE = 1"
    assert rogue.read_text() == "ROGUE = 2\n"


def test_exact_commit_intent_recovers_before_ref_update(tmp_path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "bob@example.test", cwd=tmp_path)
    _git("config", "user.name", "Bob Test", cwd=tmp_path)
    target = tmp_path / "target.py"
    target.write_text("TARGET = 1\n")
    _git("add", "target.py", cwd=tmp_path)
    _git("commit", "-m", "base", cwd=tmp_path)
    parent = _git("rev-parse", "HEAD", cwd=tmp_path)
    target.write_text("TARGET = 2\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    captured: dict[str, object] = {}

    def crash_after_intent(plan):
        captured.update(plan)
        raise RuntimeError("simulated controller crash")

    with pytest.raises(RuntimeError, match="simulated controller crash"):
        commit_feature(
            feature_id="feature-recover",
            message="recover",
            workspace=str(tmp_path),
            stage_paths=("target.py",),
            expected_file_sha256={"target.py": digest},
            expected_file_modes={"target.py": "100644"},
            skip_hooks=True,
            on_exact_commit_planned=crash_after_intent,
        )
    assert _git("rev-parse", "HEAD", cwd=tmp_path) == parent

    proof = finalize_exact_commit_intent(
        commit_sha=str(captured["commit_sha"]),
        parent_sha=str(captured["parent_sha"]),
        tree_sha=str(captured["tree_sha"]),
        expected_paths=("target.py",),
        expected_file_sha256={"target.py": digest},
        expected_file_modes={"target.py": "100644"},
        workspace=str(tmp_path),
    )

    assert _git("rev-parse", "HEAD", cwd=tmp_path) == captured["commit_sha"]
    assert proof["entries"][0]["content_sha256"] == digest


def test_exact_commit_recovery_rejects_intent_with_unauthorized_parent(tmp_path):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "bob@example.test", cwd=tmp_path)
    _git("config", "user.name", "Bob Test", cwd=tmp_path)
    target = tmp_path / "target.py"
    target.write_text("TARGET = 1\n")
    _git("add", "target.py", cwd=tmp_path)
    _git("commit", "-m", "authenticated base", cwd=tmp_path)
    admitted_parent = _git("rev-parse", "HEAD", cwd=tmp_path)
    admitted_tree = _git("rev-parse", "HEAD^{tree}", cwd=tmp_path)

    (tmp_path / "unauthorized.txt").write_text("hidden parent content\n")
    _git("add", "unauthorized.txt", cwd=tmp_path)
    _git("commit", "-m", "unauthorized parent advance", cwd=tmp_path)
    unauthorized_parent = _git("rev-parse", "HEAD", cwd=tmp_path)
    target.write_text("TARGET = 2\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    captured: dict[str, object] = {}

    with pytest.raises(RuntimeError, match="simulated controller crash"):
        commit_feature(
            feature_id="feature-bad-recovery-parent",
            message="bad recovery parent",
            workspace=str(tmp_path),
            stage_paths=("target.py",),
            expected_file_sha256={"target.py": digest},
            expected_file_modes={"target.py": "100644"},
            on_exact_commit_planned=lambda plan: (
                captured.update(plan),
                (_ for _ in ()).throw(RuntimeError("simulated controller crash")),
            ),
        )

    with pytest.raises(GitCommitError, match="authenticated attempt base"):
        finalize_exact_commit_intent(
            commit_sha=str(captured["commit_sha"]),
            parent_sha=str(captured["parent_sha"]),
            tree_sha=str(captured["tree_sha"]),
            expected_paths=("target.py",),
            expected_file_sha256={"target.py": digest},
            expected_file_modes={"target.py": "100644"},
            workspace=str(tmp_path),
            expected_parent_sha=admitted_parent,
            expected_parent_tree_sha=admitted_tree,
        )

    assert _git("rev-parse", "HEAD", cwd=tmp_path) == unauthorized_parent


def test_exact_commit_recovery_rejects_hash_mismatch_before_cas(tmp_path):
    _git("init", cwd=tmp_path)
    target = tmp_path / "target.py"
    removed = tmp_path / "removed.py"
    target.write_text("TARGET = 1\n")
    removed.write_text("REMOVE = True\n")
    _git("add", "target.py", "removed.py", cwd=tmp_path)
    _git("commit", "-m", "base", cwd=tmp_path)
    parent = _git("rev-parse", "HEAD", cwd=tmp_path)
    target.write_text("TARGET = 2\n")
    removed.unlink()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    captured: dict[str, object] = {}

    with pytest.raises(RuntimeError, match="crash"):
        commit_feature(
            feature_id="feature-recovery-proof",
            message="proof",
            workspace=str(tmp_path),
            stage_paths=("removed.py", "target.py"),
            expected_file_sha256={"removed.py": None, "target.py": digest},
            expected_file_modes={"removed.py": None, "target.py": "100644"},
            on_exact_commit_planned=lambda plan: (
                captured.update(plan),
                (_ for _ in ()).throw(RuntimeError("crash")),
            ),
        )

    with pytest.raises(GitCommitError, match="hash/type/mode"):
        finalize_exact_commit_intent(
            commit_sha=str(captured["commit_sha"]),
            parent_sha=str(captured["parent_sha"]),
            tree_sha=str(captured["tree_sha"]),
            expected_paths=("removed.py", "target.py"),
            expected_file_sha256={
                "removed.py": "f" * 64,
                "target.py": digest,
            },
            expected_file_modes={
                "removed.py": "100644",
                "target.py": "100644",
            },
            workspace=str(tmp_path),
        )
    assert _git("rev-parse", "HEAD", cwd=tmp_path) == parent


def test_exact_commit_ignores_inherited_git_redirection(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    attacker = tmp_path / "attacker"
    primary.mkdir()
    attacker.mkdir()
    for repo in (primary, attacker):
        _git("init", cwd=repo)
        (repo / "target.py").write_text(f"ROOT = {repo.name!r}\n")
        _git("add", "target.py", cwd=repo)
        _git("commit", "-m", "base", cwd=repo)
    attacker_head = _git("rev-parse", "HEAD", cwd=attacker)
    target = primary / "target.py"
    target.write_text("ROOT = 'updated'\n")
    monkeypatch.setenv("GIT_DIR", str(attacker / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(attacker))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(attacker / "objects-spoof"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(attacker / "index-spoof"))
    monkeypatch.setenv("GIT_REPLACE_REF_BASE", "refs/replace-attacker/")
    monkeypatch.setenv("LD_PRELOAD", "/does/not/exist/bob-attacker.so")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/does/not/exist")
    monkeypatch.setenv("PYTHONPATH", str(attacker))

    sha = commit_feature(
        feature_id="feature-sanitized-env",
        message="sanitized",
        workspace=str(primary),
        stage_paths=("target.py",),
        expected_file_sha256={
            "target.py": hashlib.sha256(target.read_bytes()).hexdigest()
        },
        expected_file_modes={"target.py": "100644"},
    )

    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_WORK_TREE")
    monkeypatch.delenv("GIT_OBJECT_DIRECTORY")
    monkeypatch.delenv("GIT_INDEX_FILE")
    monkeypatch.delenv("GIT_REPLACE_REF_BASE")
    monkeypatch.delenv("LD_PRELOAD")
    monkeypatch.delenv("LD_LIBRARY_PATH")
    monkeypatch.delenv("PYTHONPATH")
    assert _git("rev-parse", "HEAD", cwd=primary) == sha
    assert _git("rev-parse", "HEAD", cwd=attacker) == attacker_head


def test_exact_commit_requires_repository_root_workspace(tmp_path):
    _git("init", cwd=tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    target = nested / "target.py"
    target.write_text("TARGET = 1\n")
    _git("add", "nested/target.py", cwd=tmp_path)
    _git("commit", "-m", "base", cwd=tmp_path)
    target.write_text("TARGET = 2\n")

    with pytest.raises(GitRepoError, match="repository root"):
        commit_feature(
            feature_id="feature-nested",
            message="nested",
            workspace=str(nested),
            stage_paths=("target.py",),
            expected_file_sha256={
                "target.py": hashlib.sha256(target.read_bytes()).hexdigest()
            },
            expected_file_modes={"target.py": "100644"},
        )


@pytest.mark.parametrize("unsafe", ["tab\tpath.py", "control\x01path.py"])
def test_exact_commit_rejects_control_character_paths(tmp_path, unsafe):
    _git("init", cwd=tmp_path)
    _git("config", "user.email", "bob@example.test", cwd=tmp_path)
    _git("config", "user.name", "Bob Test", cwd=tmp_path)
    (tmp_path / "base.py").write_text("BASE = True\n")
    _git("add", "base.py", cwd=tmp_path)
    _git("commit", "-m", "base", cwd=tmp_path)

    with pytest.raises(ValueError, match="unsafe exact stage path"):
        commit_feature(
            feature_id="feature-unsafe",
            message="unsafe",
            workspace=str(tmp_path),
            stage_paths=(unsafe,),
            expected_file_sha256={unsafe: "0" * 64},
            expected_file_modes={unsafe: "100644"},
            skip_hooks=True,
        )
