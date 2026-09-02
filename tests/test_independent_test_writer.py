"""Tests for the reusable independent Claude test-writer role."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

import pytest
from claude_code_sdk import ClaudeCodeOptions

from bob.orchestrator.claude_executor import ExecutionResult
from bob.orchestrator.independent_test_writer import (
    ROLE_NAME,
    SCHEMA_VERSION,
    TestFileEvidence as _TestFileEvidence,
    TestWriterProtocolError as _TestWriterProtocolError,
    parse_test_writer_response,
    run_independent_test_writer,
    verify_frozen_test_files,
)


def _protocol_object(
    *,
    feature_id: str = "feature-1",
    nonce: str = "nonce-1",
    status: str = "completed",
    test_files: list[str] | None = None,
    coverage: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "role": ROLE_NAME,
        "principal_nonce": nonce,
        "status": status,
        "feature_id": feature_id,
        "test_files": ["tests/test_feature.py"] if test_files is None else test_files,
        "test_command": ["pytest", "-q", "tests/test_feature.py"] if status == "completed" else [],
        "criterion_coverage": (
            [{"criterion_index": 0, "test_ids": ["tests/test_feature.py::test_behavior"]}]
            if coverage is None
            else coverage
        ),
        "notes": [],
    }


def _response(payload: dict[str, object], *, noise: bool = False) -> str:
    fenced = f"```json\n{json.dumps(payload)}\n```"
    return f"Tests are ready.\n{fenced}\nDone." if noise else fenced


def _assignment(prompt: str) -> dict[str, object]:
    text = prompt.split("ASSIGNMENT_JSON\n", 1)[1].split(
        "\nEND_ASSIGNMENT_JSON", 1
    )[0]
    return json.loads(text)


def test_parser_accepts_one_protocol_object_in_noisy_output() -> None:
    parsed = parse_test_writer_response(
        _response(_protocol_object(), noise=True),
        expected_feature_id="feature-1",
        expected_principal_nonce="nonce-1",
        criterion_count=1,
    )

    assert parsed.status == "completed"
    assert parsed.test_files == ("tests/test_feature.py",)
    assert parsed.criterion_coverage[0].test_ids == (
        "tests/test_feature.py::test_behavior",
    )


def test_parser_rejects_conflicting_protocol_objects() -> None:
    first = _protocol_object(status="completed")
    second = _protocol_object(status="blocked")
    text = _response(first) + "\n" + _response(second)

    with pytest.raises(_TestWriterProtocolError, match="conflicting"):
        parse_test_writer_response(
            text,
            expected_feature_id="feature-1",
            expected_principal_nonce="nonce-1",
            criterion_count=1,
        )


@pytest.mark.parametrize(
    "bad_path",
    ["../source.py", "/tmp/test_feature.py", "src/test_feature.py", "tests\\test_feature.py"],
)
def test_parser_rejects_test_files_outside_allowed_roots(bad_path: str) -> None:
    with pytest.raises(_TestWriterProtocolError):
        parse_test_writer_response(
            _response(_protocol_object(test_files=[bad_path])),
            expected_feature_id="feature-1",
            expected_principal_nonce="nonce-1",
            criterion_count=1,
        )


def test_parser_requires_exact_acceptance_criterion_coverage() -> None:
    payload = _protocol_object(
        coverage=[{"criterion_index": 1, "test_ids": ["tests/test_feature.py::test_other"]}]
    )

    with pytest.raises(_TestWriterProtocolError, match="cover every criterion"):
        parse_test_writer_response(
            _response(payload),
            expected_feature_id="feature-1",
            expected_principal_nonce="nonce-1",
            criterion_count=2,
        )


def test_parser_rejects_wrong_spawn_nonce() -> None:
    with pytest.raises(_TestWriterProtocolError, match="nonce"):
        parse_test_writer_response(
            _response(_protocol_object(nonce="old-principal")),
            expected_feature_id="feature-1",
            expected_principal_nonce="this-principal",
            criterion_count=1,
        )


def test_role_uses_fresh_executor_and_exact_caller_options(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []

    class FakeExecutor:
        def __init__(self, *, default_options):
            calls.append(("init", default_options))

        async def execute(self, prompt, *, options):
            calls.append(("execute_options", options))
            calls.append(("prompt", prompt))
            nonce = re.search(r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE).group(1)
            namespace = str(_assignment(prompt)["test_namespace"])
            relative = f"{namespace}/test_feature.py"
            test_path = tmp_path / relative
            test_bytes = b"def test_behavior():\n    actual = 1 + 1\n    assert actual == 3\n"
            test_path.write_bytes(test_bytes)
            payload = _protocol_object(
                nonce=nonce,
                test_files=[relative],
                coverage=[{"criterion_index": 0, "test_ids": [f"{relative}::test_behavior"]}],
            )
            return ExecutionResult(
                text=_response(payload, noise=True),
                session_id="session-test-writer",
                duration_ms=321,
                num_turns=3,
                total_cost_usd=0.25,
                tool_uses=["Read", "Write"],
            )

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        FakeExecutor,
    )
    options = ClaudeCodeOptions(
        cwd=str(tmp_path),
        model="claude-opus-4-6",
        max_turns=17,
        allowed_tools=["Read", "Write", "Bash"],
    )

    result = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature one",
            feature_description="Provide behavior one",
            acceptance_criteria=["Behavior one is observable"],
            cwd=tmp_path,
            options=options,
        )
    )

    assert result.ok
    role_options = calls[0][1]
    assert calls[1] == ("execute_options", role_options)
    assert role_options.model == options.model
    assert role_options.max_turns == options.max_turns
    assert role_options.env["BOB_AGENT_ROLE"] == "independent_test_writer"
    prompt = calls[2][1]
    assert "independent TEST-WRITER principal" in prompt
    assert "Do not implement the feature" in prompt
    assert "Do not run git commands" in prompt
    assert result.evidence.session_id == "session-test-writer"
    assert result.evidence.model == "claude-opus-4-6"
    assert result.evidence.max_turns == 17
    assert result.evidence.tool_uses == ("Read", "Write")
    assert len(result.evidence.principal_nonce) == 32
    assert result.evidence.prompt_sha256 == hashlib.sha256(prompt.encode()).hexdigest()
    artifact = result.evidence.changed_files[0]
    assert artifact.path.endswith("/test_feature.py")
    assert artifact.operation == "created"
    assert artifact.sha256 == hashlib.sha256(
        b"def test_behavior():\n    actual = 1 + 1\n    assert actual == 3\n"
    ).hexdigest()


def test_each_invocation_constructs_a_new_principal(monkeypatch, tmp_path: Path) -> None:
    instances: list[object] = []
    nonces: list[str] = []

    class FakeExecutor:
        def __init__(self, *, default_options):
            instances.append(self)

        async def execute(self, prompt, *, options):
            nonce = re.search(r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE).group(1)
            nonces.append(nonce)
            assignment = _assignment(prompt)
            feature_id = assignment["feature_id"]
            relative = f"{assignment['test_namespace']}/test_{feature_id}.py"
            path = tmp_path / relative
            path.write_text("def test_behavior():\n    actual = 1\n    assert actual == 2\n")
            return ExecutionResult(
                text=_response(
                    _protocol_object(
                        feature_id=feature_id,
                        nonce=nonce,
                        test_files=[relative],
                        coverage=[{"criterion_index": 0, "test_ids": [f"{relative}::test_behavior"]}],
                    )
                ),
                session_id=f"session-{feature_id}",
            )

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        FakeExecutor,
    )
    options = ClaudeCodeOptions(cwd=str(tmp_path), model="claude-opus-4-6")

    first = asyncio.run(
        run_independent_test_writer(
            feature_id="one",
            feature_title="One",
            feature_description="One",
            acceptance_criteria=["One"],
            cwd=tmp_path,
            options=options,
        )
    )
    second = asyncio.run(
        run_independent_test_writer(
            feature_id="two",
            feature_title="Two",
            feature_description="Two",
            acceptance_criteria=["Two"],
            cwd=tmp_path,
            options=options,
        )
    )

    assert first.ok and second.ok
    assert len(instances) == 2
    assert instances[0] is not instances[1]
    assert len(set(nonces)) == 2


def test_role_fails_closed_on_source_change(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "app.py"
    source.write_text("VALUE = 1\n")

    class FakeExecutor:
        def __init__(self, *, default_options):
            pass

        async def execute(self, prompt, *, options):
            source.write_text("VALUE = 2\n")
            return ExecutionResult(text="not even valid JSON")

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        FakeExecutor,
    )
    options = ClaudeCodeOptions(cwd=str(tmp_path))

    result = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature",
            feature_description="Description",
            acceptance_criteria=["Criterion"],
            cwd=tmp_path,
            options=options,
        )
    )

    assert result.outcome == "scope_violation"
    assert result.evidence.unauthorized_changes == ("src/app.py",)
    assert result.evidence.changed_files[0].operation == "modified"


def test_role_rejects_omitted_or_false_file_declarations(monkeypatch, tmp_path: Path) -> None:
    class FakeExecutor:
        def __init__(self, *, default_options):
            pass

        async def execute(self, prompt, *, options):
            nonce = re.search(r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE).group(1)
            namespace = str(_assignment(prompt)["test_namespace"])
            path = tmp_path / namespace / "actual.py"
            path.write_text("def test_actual():\n    assert True\n")
            return ExecutionResult(
                text=_response(_protocol_object(nonce=nonce, test_files=["tests/claimed.py"]))
            )

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        FakeExecutor,
    )
    options = ClaudeCodeOptions(cwd=str(tmp_path))

    result = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature",
            feature_description="Description",
            acceptance_criteria=["Criterion"],
            cwd=tmp_path,
            options=options,
        )
    )

    assert result.outcome == "protocol_error"
    assert "do not exactly match" in result.error


def test_completed_role_must_change_at_least_one_test(monkeypatch, tmp_path: Path) -> None:
    class FakeExecutor:
        def __init__(self, *, default_options):
            pass

        async def execute(self, prompt, *, options):
            nonce = re.search(r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE).group(1)
            payload = _protocol_object(nonce=nonce, test_files=[])
            return ExecutionResult(text=_response(payload))

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        FakeExecutor,
    )
    options = ClaudeCodeOptions(cwd=str(tmp_path))

    result = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature",
            feature_description="Description",
            acceptance_criteria=["Criterion"],
            cwd=tmp_path,
            options=options,
        )
    )

    assert result.outcome == "protocol_error"
    assert "at least one test file" in result.error


def test_completed_role_must_not_delete_tests(monkeypatch, tmp_path: Path) -> None:
    test_path = tmp_path / "tests" / "test_feature.py"
    test_path.parent.mkdir()
    test_path.write_text("def test_old():\n    assert True\n")

    class FakeExecutor:
        def __init__(self, *, default_options):
            pass

        async def execute(self, prompt, *, options):
            nonce = re.search(r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE).group(1)
            test_path.unlink()
            return ExecutionResult(text=_response(_protocol_object(nonce=nonce)))

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        FakeExecutor,
    )
    options = ClaudeCodeOptions(cwd=str(tmp_path))

    result = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature",
            feature_description="Description",
            acceptance_criteria=["Criterion"],
            cwd=tmp_path,
            options=options,
        )
    )

    assert result.outcome == "scope_violation"
    assert "non-additive" in result.error


def test_frozen_test_verifier_detects_changed_and_deleted_bytes(tmp_path: Path) -> None:
    changed_path = tmp_path / "tests" / "test_changed.py"
    deleted_path = tmp_path / "tests" / "test_deleted.py"
    changed_path.parent.mkdir()
    original = b"def test_behavior():\n    assert value() == 1\n"
    changed_path.write_bytes(original)
    deleted_path.write_bytes(original)
    evidence = (
        # Size is evidence metadata; byte identity is enforced by SHA-256.
        _TestFileEvidence(
            path="tests/test_changed.py",
            operation="created",
            sha256=hashlib.sha256(original).hexdigest(),
            size_bytes=len(original),
        ),
        _TestFileEvidence(
            path="tests/test_deleted.py",
            operation="created",
            sha256=hashlib.sha256(original).hexdigest(),
            size_bytes=len(original),
        ),
    )
    changed_path.write_text("def test_behavior():\n    assert True\n")
    deleted_path.unlink()

    violations = verify_frozen_test_files(cwd=tmp_path, frozen_files=evidence)

    assert [(item.path, item.reason) for item in violations] == [
        ("tests/test_changed.py", "content_changed"),
        ("tests/test_deleted.py", "deleted_or_unreadable"),
    ]


def test_role_returns_executor_error_without_parsing(monkeypatch, tmp_path: Path) -> None:
    class FakeExecutor:
        def __init__(self, *, default_options):
            pass

        async def execute(self, prompt, *, options):
            return ExecutionResult(is_error=True, error_message="provider unavailable")

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        FakeExecutor,
    )
    options = ClaudeCodeOptions(cwd=str(tmp_path))

    result = asyncio.run(
        run_independent_test_writer(
            feature_id="feature-1",
            feature_title="Feature",
            feature_description="Description",
            acceptance_criteria=["Criterion"],
            cwd=tmp_path,
            options=options,
        )
    )

    assert result.outcome == "executor_error"
    assert result.error == "provider unavailable"
    assert not result.ok


def test_role_refuses_cwd_options_mismatch_before_spawn(monkeypatch, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    options = ClaudeCodeOptions(cwd=str(other))

    class MustNotConstruct:
        def __init__(self, **kwargs):
            raise AssertionError("executor must not spawn")

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        MustNotConstruct,
    )

    with pytest.raises(ValueError, match="cwd mismatch"):
        asyncio.run(
            run_independent_test_writer(
                feature_id="feature-1",
                feature_title="Feature",
                feature_description="Description",
                acceptance_criteria=["Criterion"],
                cwd=tmp_path,
                options=options,
            )
        )
