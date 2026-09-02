"""Mock-only coverage for Bob's free-form spec to feature-DAG planner."""

from __future__ import annotations

import hashlib
import json
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from bob.feature_planner import (
    FeaturePlanValidationError,
    PPAT_SOURCE_PRECEDENCE,
    PlannerSourceFile,
    build_feature_planner_prompt,
    parse_and_validate_feature_plan,
    project_name_from_source,
)


def _feature(
    key: str = "PPAT-M0-01",
    *,
    depends_on: list[str] | None = None,
    execution_class: str = "local",
) -> dict:
    return {
        "key": key,
        "name": f"Feature {key}",
        "description": "Implement a bounded, independently testable behavior.",
        "priority": 10,
        "depends_on": list(depends_on or []),
        "acceptance_criteria": [
            "pytest: tests/test_contract.py verifies the public contract",
            "Command succeeds: python -m pytest tests/test_contract.py",
        ],
        "execution_class": execution_class,
        "source_trace": ["spec:L1"],
    }


def _agent_output(features: list[dict] | None = None) -> str:
    payload = {"features": features or [_feature()]}
    return "```yaml\n" + yaml.safe_dump(payload, sort_keys=False) + "```"


def _execution_result(text: str, *, is_error: bool = False, error_message: str = ""):
    return SimpleNamespace(
        text=text,
        is_error=is_error,
        error_message=error_message,
    )


def _sdk_options(**kwargs):
    from claude_code_sdk import ClaudeCodeOptions

    kwargs.pop("agent_role", None)
    return ClaudeCodeOptions(**kwargs)


def test_plain_markdown_is_not_required_to_be_a_yaml_mapping():
    source = "# Power projection tool\n\nForecast future accelerator power.\n"

    assert project_name_from_source(source, "power-requirements") == "power-requirements"


def test_invalid_yaml_is_still_valid_plaintext_source():
    source = "The UI accepts templates like {{{{name::::}} without interpreting them."

    assert project_name_from_source(source, "application") == "application"


def test_yaml_mapping_name_remains_a_display_name_convenience():
    assert project_name_from_source("name: ppat\ndescription: power tool\n", "fallback") == "ppat"


def test_prompt_requires_complete_schema_and_line_level_trace():
    prompt = build_feature_planner_prompt(
        "Primary goal\nForecast MI500 power", ["Read package registers"]
    )

    for required in (
        "key:",
        "depends_on:",
        "acceptance_criteria:",
        "execution_class:",
        "source_trace:",
        "local, hardware_read, hardware_mutation, release",
        "UNTRUSTED REQUIREMENT DATA",
        "L1: Primary goal",
        "L2: Forecast MI500 power",
        'source="reference-1"',
    ):
        assert required in prompt


def test_valid_plan_preserves_scheduler_and_trace_fields():
    expected = [
        _feature("FOUNDATION"),
        _feature(
            "READ-POWER",
            depends_on=["FOUNDATION"],
            execution_class="hardware_read",
        ),
    ]

    parsed = parse_and_validate_feature_plan(_agent_output(expected))

    assert parsed == expected
    assert parsed[1]["depends_on"] == ["FOUNDATION"]
    assert parsed[1]["execution_class"] == "hardware_read"
    assert parsed[1]["source_trace"] == expected[1]["source_trace"]


@pytest.mark.parametrize(
    ("trace", "message"),
    [
        ("invented:L1", "unknown source_id"),
        ("spec:L1-L9", "outside trusted source"),
        ("spec:1-2", "must use source_id"),
        ("spec:L3-L2", "outside trusted source"),
    ],
)
def test_file_backed_source_trace_is_bound_to_trusted_manifest(trace, message):
    feature = _feature()
    feature["source_trace"] = [trace]
    sources = (
        PlannerSourceFile(
            source_id="spec",
            filename="application-spec.txt",
            sha256="0" * 64,
            line_count=4,
        ),
    )

    with pytest.raises(FeaturePlanValidationError, match=message):
        parse_and_validate_feature_plan(_agent_output([feature]), sources=sources)


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("no structured plan", "exactly one fenced YAML block"),
        ("Here is the plan:\n" + _agent_output(), "no prose"),
        (
            _agent_output() + "\n" + _agent_output([_feature("SECOND")]),
            "exactly one fenced YAML block",
        ),
        (
            "```yaml\nfeatures:\n  - key: A\n    key: B\n```",
            "duplicate key",
        ),
    ],
)
def test_ambiguous_or_malformed_output_fails_closed(output, message):
    with pytest.raises(FeaturePlanValidationError, match=message):
        parse_and_validate_feature_plan(output)


def test_bare_list_output_is_rejected_by_strict_planner():
    bare_list = "```yaml\n" + yaml.safe_dump([_feature()], sort_keys=False) + "```"

    with pytest.raises(FeaturePlanValidationError, match="must be a mapping"):
        parse_and_validate_feature_plan(bare_list)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda features: features[0].pop("source_trace"), "source_trace"),
        (lambda features: features[0].update(depends_on=["MISSING"]), "unknown key"),
        (lambda features: features[0].update(execution_class="maybe"), "must be one of"),
        (lambda features: features[0].update(acceptance_criteria=[]), "non-empty list"),
        (lambda features: features[0].update(source_trace=[]), "non-empty list"),
        (lambda features: features[0].update(extra_controller_knob=True), "unknown field"),
        (lambda features: features.append(_feature("PPAT-M0-01")), "duplicate feature key"),
    ],
)
def test_invalid_feature_contract_fails_closed(mutate, message):
    features = [_feature()]
    mutate(features)

    with pytest.raises(FeaturePlanValidationError, match=message):
        parse_and_validate_feature_plan(_agent_output(features))


def test_dependency_cycle_fails_closed():
    features = [
        _feature("A", depends_on=["C"]),
        _feature("B", depends_on=["A"]),
        _feature("C", depends_on=["B"]),
    ]

    with pytest.raises(FeaturePlanValidationError, match="dependency cycle"):
        parse_and_validate_feature_plan(_agent_output(features))


def test_planner_defaults_to_exact_opus_4_8_and_does_not_override_unlimited_turns(
    monkeypatch,
):
    from bob.cli import _run_generate_features

    monkeypatch.delenv("BOB_FEATURE_PLANNER_MODEL", raising=False)
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "unlimited")
    executor = MagicMock()
    executor.execute = AsyncMock(
        return_value=_execution_result(_agent_output())
    )

    with patch(
        "bob.orchestrator.claude_executor.build_sub_agent_options",
        side_effect=_sdk_options,
    ) as build_options, patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor",
        return_value=executor,
    ):
        result = _run_generate_features("Build a power projection tool")

    assert result == [_feature()]
    assert build_options.call_args.kwargs["model"] == "claude-opus-4-8"
    assert "max_turns" not in build_options.call_args.kwargs


def test_planner_model_can_be_configured_with_environment(monkeypatch):
    from bob.cli import _run_generate_features

    monkeypatch.setenv("BOB_FEATURE_PLANNER_MODEL", "claude-opus-4-8")
    executor = MagicMock()
    executor.execute = AsyncMock(
        return_value=_execution_result(_agent_output())
    )

    with patch(
        "bob.orchestrator.claude_executor.build_sub_agent_options",
        side_effect=_sdk_options,
    ) as build_options, patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor",
        return_value=executor,
    ):
        _run_generate_features("Build it")

    kwargs = build_options.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-8"
    assert kwargs["allowed_tools"] == ["Read"]
    assert kwargs["permission_mode"] == "default"
    assert kwargs["mcp_servers"] == {}
    assert "Write" in kwargs["disallowed_tools"]
    assert "Bash" in kwargs["disallowed_tools"]
    assert isinstance(kwargs["cwd"], pathlib.Path)


def test_required_source_precedence_fails_closed_before_spawn(monkeypatch):
    from bob.cli import _run_generate_features

    monkeypatch.setenv("BOB_PLANNER_SOURCE_PRECEDENCE_REQUIRED", "1")
    monkeypatch.delenv("BOB_PLANNER_SOURCE_PRECEDENCE", raising=False)
    with patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor"
    ) as executor_type:
        with pytest.raises(FeaturePlanValidationError, match="is required"):
            _run_generate_features("Build PPAT")
    executor_type.assert_not_called()


def test_required_source_precedence_is_manifest_and_prompt_bound(monkeypatch):
    from bob.cli import _run_generate_features

    monkeypatch.setenv("BOB_PLANNER_SOURCE_PRECEDENCE_REQUIRED", "1")
    monkeypatch.setenv("BOB_PLANNER_SOURCE_PRECEDENCE", PPAT_SOURCE_PRECEDENCE)
    captured: dict[str, object] = {}

    class InspectingExecutor:
        def __init__(self, *, default_options):
            self.options = default_options

        async def execute(self, prompt):
            captured["prompt"] = prompt
            manifest_path = pathlib.Path(self.options.cwd) / "source-manifest.yaml"
            manifest_bytes = manifest_path.read_bytes()
            manifest = yaml.safe_load(manifest_bytes)
            captured["manifest"] = manifest
            captured["manifest_bytes"] = manifest_bytes
            return _execution_result(_agent_output())

    with patch(
        "bob.orchestrator.claude_executor.build_sub_agent_options",
        side_effect=_sdk_options,
    ), patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor", InspectingExecutor
    ):
        assert _run_generate_features("Build PPAT", ["5.6 review"]) == [_feature()]

    assert PPAT_SOURCE_PRECEDENCE in captured["prompt"]
    manifest = captured["manifest"]
    assert manifest["source_precedence"] == PPAT_SOURCE_PRECEDENCE
    assert manifest["source_precedence_sha256"] == hashlib.sha256(
        PPAT_SOURCE_PRECEDENCE.encode("utf-8")
    ).hexdigest()
    assert captured["manifest_bytes"] == (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert hashlib.sha256(captured["manifest_bytes"]).hexdigest() in captured[
        "prompt"
    ]


def test_required_source_precedence_rejects_substitution(monkeypatch):
    from bob.cli import _run_generate_features

    monkeypatch.setenv("BOB_PLANNER_SOURCE_PRECEDENCE_REQUIRED", "1")
    monkeypatch.setenv("BOB_PLANNER_SOURCE_PRECEDENCE", "Prefer the older draft.")
    with pytest.raises(FeaturePlanValidationError, match="pinned PPAT rule"):
        _run_generate_features("Build PPAT")


def test_unknown_planner_model_fails_before_executor_construction(monkeypatch):
    from bob.cli import _run_generate_features

    monkeypatch.setenv("BOB_FEATURE_PLANNER_MODEL", "opus-typo")

    with patch(
        "bob.orchestrator.claude_executor.build_sub_agent_options"
    ) as build_options, patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor"
    ) as executor_type:
        with pytest.raises(ValueError, match="Unknown model"):
            _run_generate_features("Build it")

    build_options.assert_not_called()
    executor_type.assert_not_called()


def test_invalid_provider_response_is_never_returned(monkeypatch):
    from bob.cli import _run_generate_features

    monkeypatch.setenv("BOB_FEATURE_PLANNER_MODEL", "claude-opus-4-8")
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=_execution_result("looks good"))

    with patch(
        "bob.orchestrator.claude_executor.build_sub_agent_options",
        side_effect=_sdk_options,
    ), patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor",
        return_value=executor,
    ):
        with pytest.raises(FeaturePlanValidationError):
            _run_generate_features("Build it")


def test_large_sources_use_bounded_prompt_and_private_read_only_workspace(monkeypatch):
    from bob.cli import _run_generate_features

    large_spec = "# PPAT\n" + ("future power projection requirement\n" * 8_000)
    large_review = "# Review\n" + ("preserve primary goal\n" * 2_000)
    assert len((large_spec + large_review).encode("utf-8")) > 134 * 1024

    captured: dict[str, object] = {}

    def fake_build_options(**kwargs):
        captured["options_kwargs"] = kwargs
        return _sdk_options(**kwargs)

    def fake_executor_type(*, default_options):
        captured["effective_options"] = default_options
        return executor

    async def fake_execute(prompt):
        captured["prompt"] = prompt
        kwargs = captured["options_kwargs"]
        assert isinstance(kwargs, dict)
        workspace = pathlib.Path(kwargs["cwd"])
        captured["workspace"] = workspace

        assert workspace.is_dir()
        assert workspace.stat().st_mode & 0o777 == 0o700
        assert (workspace / "application-spec.txt").read_text() == large_spec
        assert (workspace / "reference-001.txt").read_text() == large_review
        assert (workspace / "source-manifest.yaml").is_file()
        for filename in (
            "application-spec.txt",
            "reference-001.txt",
            "source-manifest.yaml",
        ):
            assert (workspace / filename).stat().st_mode & 0o777 == 0o600

        return _execution_result(_agent_output())

    executor = MagicMock()
    executor.execute = AsyncMock(side_effect=fake_execute)
    monkeypatch.setenv("BOB_FEATURE_PLANNER_MODEL", "claude-opus-4-8")

    with patch(
        "bob.orchestrator.claude_executor.build_sub_agent_options",
        side_effect=fake_build_options,
    ) as build_options, patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor",
        side_effect=fake_executor_type,
    ) as executor_type:
        result = _run_generate_features(large_spec, [large_review])

    assert result == [_feature()]
    prompt = captured["prompt"]
    assert isinstance(prompt, str)
    assert len(prompt.encode("utf-8")) < 100 * 1024
    assert large_spec not in prompt
    assert large_review not in prompt
    assert "application-spec.txt" in prompt
    assert "reference-001.txt" in prompt
    assert "source-manifest.yaml" in prompt

    kwargs = build_options.call_args.kwargs
    assert kwargs["allowed_tools"] == ["Read"]
    assert set(kwargs["disallowed_tools"]) >= {
        "Write",
        "Edit",
        "Bash",
        "WebFetch",
        "WebSearch",
    }
    assert kwargs["permission_mode"] == "default"
    assert kwargs["mcp_servers"] == {}
    executor_type.assert_called_once()
    effective_options = captured["effective_options"]
    assert effective_options.debug_stderr is not None
    assert effective_options.extra_args["debug-to-stderr"] is None
    assert not pathlib.Path(captured["workspace"]).exists()


def test_sdk_failure_surfaces_sanitized_stderr_and_cleans_temp_files(monkeypatch):
    from bob.cli import _run_generate_features

    source_sentinel = "CONFIDENTIAL-NORMATIVE-CONTENT-DO-NOT-REPORT"
    secret = "sk-ant-supersecretcredential123456"
    captured: dict[str, pathlib.Path] = {}

    class FailingExecutor:
        def __init__(self, *, default_options):
            self.options = default_options
            captured["workspace"] = pathlib.Path(default_options.cwd)
            captured["stderr"] = pathlib.Path(default_options.debug_stderr.name)

        async def execute(self, prompt):
            stderr = self.options.debug_stderr
            stderr.write("Error: provider rejected request code=MODEL_DENIED\n")
            stderr.write(f"authorization: Bearer {secret}\n")
            stderr.write(f"source dump: {source_sentinel}\n")
            stderr.write(prompt)
            stderr.flush()
            raise RuntimeError(
                f"Check stderr output for details ANTHROPIC_API_KEY={secret}"
            )

    monkeypatch.setenv("BOB_FEATURE_PLANNER_MODEL", "claude-opus-4-8")
    with patch(
        "bob.orchestrator.claude_executor.build_sub_agent_options",
        side_effect=_sdk_options,
    ), patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor",
        FailingExecutor,
    ):
        with pytest.raises(FeaturePlanValidationError) as raised:
            _run_generate_features(source_sentinel)

    message = str(raised.value)
    assert "Claude planner execution failed" in message
    assert "MODEL_DENIED" in message
    assert "Check stderr output for details" in message
    assert source_sentinel not in message
    assert secret not in message
    assert "ANTHROPIC_API_KEY=" not in message or "<redacted>" in message
    assert "You are Bob's feature-DAG planner" not in message
    assert len(message) < 5000
    assert not captured["workspace"].exists()
    assert not captured["stderr"].exists()


def test_planner_uses_ephemeral_home_without_copying_user_claude_state(
    monkeypatch, tmp_path
):
    from bob.cli import _run_generate_features

    user_home = tmp_path / "real-user-home"
    user_claude = user_home / ".claude"
    user_claude.mkdir(parents=True)
    user_sentinel = user_claude / "do-not-copy.plugin"
    user_sentinel.write_text("USER-PLUGIN-SENTINEL")
    credential = "sk-ant-test-forwarding-only-123456"
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("CLAUDE_API_KEY", credential)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("BOB_FEATURE_PLANNER_MODEL", "claude-opus-4-8")

    captured: dict[str, object] = {}

    class InspectingExecutor:
        def __init__(self, *, default_options):
            self.options = default_options

        async def execute(self, prompt):
            env = self.options.env
            workspace = pathlib.Path(self.options.cwd)
            captured["workspace"] = workspace
            captured["runtime_paths"] = [
                pathlib.Path(env[name])
                for name in (
                    "HOME",
                    "CLAUDE_CONFIG_DIR",
                    "XDG_CONFIG_HOME",
                    "XDG_CACHE_HOME",
                    "XDG_STATE_HOME",
                    "XDG_DATA_HOME",
                )
            ]

            assert env["HOME"] != str(user_home)
            assert env["ANTHROPIC_API_KEY"] == credential
            assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
            for runtime_path in captured["runtime_paths"]:
                assert runtime_path.is_dir()
                assert runtime_path.is_relative_to(workspace)
                assert runtime_path.stat().st_mode & 0o777 == 0o700
                assert not (runtime_path / "do-not-copy.plugin").exists()

            extra = self.options.extra_args
            assert extra["setting-sources"] == ""
            assert extra["no-session-persistence"] is None
            assert extra["strict-mcp-config"] is None
            assert extra["disable-slash-commands"] is None
            assert extra["bare"] is None
            assert extra["restricted"] is None
            assert extra["tools"] == "Read"
            return _execution_result(_agent_output())

    with patch(
        "bob.skills_installer.install_skills_to_workspace"
    ), patch(
        "bob.skills_installer.verify_skills_integrity"
    ), patch(
        "bob.orchestrator.claude_executor.ClaudeExecutor",
        InspectingExecutor,
    ):
        assert _run_generate_features("Build PPAT") == [_feature()]

    assert user_sentinel.read_text() == "USER-PLUGIN-SENTINEL"
    assert not pathlib.Path(captured["workspace"]).exists()
    for runtime_path in captured["runtime_paths"]:
        assert not runtime_path.exists()


def test_cli_accepts_markdown_and_emits_all_contract_fields(tmp_path):
    from bob.cli import main

    source = "# PPAT\n\nProject future accelerator power and produce tornado plots.\n"
    spec_path = tmp_path / "requirements.md"
    output_path = tmp_path / "features.yaml"
    spec_path.write_text(source)
    features = [_feature()]

    with patch("bob.cli._run_generate_features", return_value=features) as planner:
        result = CliRunner().invoke(
            main,
            [
                "generate-features",
                str(spec_path),
                "--output",
                str(output_path),
                "--model",
                "claude-opus-4-8",
            ],
        )

    assert result.exit_code == 0, result.output
    assert planner.call_args.args[0] == source
    assert planner.call_args.kwargs["model"] == "claude-opus-4-8"
    emitted = yaml.safe_load(output_path.read_text())
    assert emitted["name"] == "requirements"
    assert emitted["features"] == features


def test_cli_persists_precedence_and_plan_provenance(monkeypatch, tmp_path):
    from bob.cli import main

    source = "# PPAT\n\nProject future accelerator power.\n"
    spec_path = tmp_path / "requirements.md"
    output_path = tmp_path / "features.yaml"
    spec_path.write_text(source)
    features = [_feature()]
    monkeypatch.setenv("BOB_PLANNER_SOURCE_PRECEDENCE_REQUIRED", "1")

    with patch("bob.cli._run_generate_features", return_value=features) as planner:
        result = CliRunner().invoke(
            main,
            [
                "generate-features",
                str(spec_path),
                "--output",
                str(output_path),
                "--source-precedence",
                PPAT_SOURCE_PRECEDENCE,
            ],
        )

    assert result.exit_code == 0, result.output
    assert planner.call_args.kwargs["source_precedence"] == PPAT_SOURCE_PRECEDENCE
    emitted = yaml.safe_load(output_path.read_text())
    provenance = emitted["planner_provenance"]
    assert provenance["source_precedence"] == PPAT_SOURCE_PRECEDENCE
    assert provenance["source_precedence_sha256"] == hashlib.sha256(
        PPAT_SOURCE_PRECEDENCE.encode("utf-8")
    ).hexdigest()
    assert provenance["feature_plan_sha256"] == hashlib.sha256(
        json.dumps(features, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert len(provenance["source_manifest_sha256"]) == 64


def test_cli_json_output_is_canonical_utf8_with_final_lf(tmp_path):
    from bob.cli import main

    spec_path = tmp_path / "requirements.md"
    output_path = tmp_path / "features.json"
    spec_path.write_text("# PPAT\nProject future accelerator power.\n")
    features = [_feature()]

    with patch("bob.cli._run_generate_features", return_value=features):
        result = CliRunner().invoke(
            main,
            ["generate-features", str(spec_path), "--output", str(output_path)],
        )

    assert result.exit_code == 0, result.output
    expected = {
        "name": "requirements",
        "features": features,
    }
    expected_bytes = (
        json.dumps(
            expected,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert output_path.read_bytes() == expected_bytes
    assert output_path.read_bytes().endswith(b"\n")
    assert "\\u2014" not in output_path.read_text(encoding="utf-8")


def test_cli_passes_utf8_markdown_review_as_normative_reference(tmp_path):
    from bob.cli import main

    spec_path = tmp_path / "application.md"
    review_path = tmp_path / "review-5.6.md"
    output_path = tmp_path / "features.yaml"
    spec_path.write_text("# Application\nBuild PPAT.\n")
    review = "# 5.6 Review\nThe primary goal is future-architecture projection.\n"
    review_path.write_text(review, encoding="utf-8")

    with patch("bob.cli._run_generate_features", return_value=[]) as planner:
        result = CliRunner().invoke(
            main,
            [
                "generate-features",
                str(spec_path),
                "--refs",
                str(review_path),
                "--output",
                str(output_path),
            ],
        )

    assert result.exit_code == 0, result.output
    assert planner.call_args.args[1] == [review]


def test_cli_fails_closed_on_non_utf8_reference(tmp_path):
    from bob.cli import main

    spec_path = tmp_path / "application.txt"
    reference_path = tmp_path / "review.md"
    output_path = tmp_path / "features.yaml"
    spec_path.write_text("Build PPAT.")
    reference_path.write_bytes(b"\xff\xfe\x00")

    with patch("bob.cli._run_generate_features") as planner:
        result = CliRunner().invoke(
            main,
            [
                "generate-features",
                str(spec_path),
                "--refs",
                str(reference_path),
                "--output",
                str(output_path),
            ],
        )

    assert result.exit_code == 1
    assert "normative reference" in result.output
    planner.assert_not_called()
    assert not output_path.exists()


def test_cli_leaves_no_output_when_strict_planner_rejects_response(tmp_path):
    from bob.cli import main

    spec_path = tmp_path / "requirements.txt"
    output_path = tmp_path / "features.yaml"
    spec_path.write_text("Build a local model and validate it on AMD hardware.")

    with patch(
        "bob.cli._run_generate_features",
        side_effect=FeaturePlanValidationError("unknown dependency BAD"),
    ):
        result = CliRunner().invoke(
            main,
            ["generate-features", str(spec_path), "--output", str(output_path)],
        )

    assert result.exit_code == 1
    assert "rejected" in result.output
    assert not output_path.exists()
