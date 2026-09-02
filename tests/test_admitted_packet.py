from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from claude_code_sdk import ClaudeCodeOptions

from bob.admitted_packet import (
    AdmittedPacketError,
    assert_exact_writer_result,
    assert_feature_matches_packet,
    assert_packet_change_paths,
    canonical_json_bytes,
    load_admitted_packet_context,
    packet_binding_payload,
)
from bob.git_ops import get_exact_workspace_base
from bob.orchestrator.claude_executor import ExecutionResult
from bob.orchestrator.independent_test_writer import (
    ROLE_NAME,
    SCHEMA_VERSION,
    build_test_writer_prompt,
    run_independent_test_writer,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
FAMILY_ID = "ppat-family-" + "1" * 32
PACKET_ID = "ppat-packet-" + "2" * 32
FEATURE_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:ppat:{PACKET_ID}"))


def test_exact_workspace_base_binds_cumulative_head_tree_and_cleanliness(tmp_path):
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "config", "user.email", "bob@example.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Bob Test"], cwd=workspace, check=True
    )
    tracked = workspace / "base.txt"
    tracked.write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=workspace, check=True)
    proof = get_exact_workspace_base(workspace=str(workspace))
    assert proof["clean"] is True
    assert proof["commit"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=workspace, text=True
    ).strip()
    assert proof["tree"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=workspace, text=True
    ).strip()
    tracked.write_text("changed\n")
    assert get_exact_workspace_base(workspace=str(workspace))["clean"] is False


def _packet() -> dict[str, object]:
    return {
        "slug": "projection-engine",
        "parent_design_feature": "parent-power-analysis",
        "source_spans": [
            {"source_id": "application", "start_line": 1, "end_line": 2}
        ],
        "authority_boundary": "Development result only; controller owns admission.",
        "observable_behavior": "Project power for a supplied architecture record.",
        "primary_artifact": {
            "kind": "module",
            "target_paths": ["app/src/ppat/projection.py"],
        },
        "inputs": {
            "schema_ids": [],
            "fixture_ids": [],
            "package_lock_ids": [],
            "oracle_ids": [],
        },
        "output": {
            "kind": "serialized",
            "schema_id": "projection.v1",
            "path": "projection.json",
            "api_contract": None,
            "persistence": "required",
        },
        "error_map": [{"condition": "invalid input", "outcome": "typed error"}],
        "dependencies": {
            "build_requires": [],
            "consumes_or_binds": [],
            "verification_requires": [],
            "activation_requires": [],
        },
        "external_prerequisite_ids": [],
        "acceptance_profile_id": "unit",
        "acceptance_predicates": ["valid projection", "invalid input rejected"],
        "non_goals": ["hardware collection"],
    }


def _documents(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str], dict, dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    (workspace / "app" / "src" / "ppat").mkdir(parents=True)
    (workspace / "app" / "tests").mkdir(parents=True)
    publication = tmp_path / "controller" / "packets" / "projection-engine"
    route_path = publication / "source-route" / "application-L1-L2.txt"
    route_path.parent.mkdir(parents=True)
    route_raw = b"line one\nline two\n"
    route_path.write_bytes(route_raw)
    feature_slug = re.sub(r"[^A-Za-z0-9]+", "-", FEATURE_ID).strip("-").lower()[:32]
    namespace_digest = hashlib.sha256(f"{FEATURE_ID}\0{0}".encode()).hexdigest()[:16]
    namespace = f"app/tests/bob_generated/{feature_slug}-a0-{namespace_digest}"
    test_path = f"{namespace}/test_projection_engine.py"
    nodes = [
        f"{test_path}::test_acceptance_001",
        f"{test_path}::test_acceptance_002",
    ]
    packet = _packet()
    projection = {
        "schema_version": "ppat.candidate-task-projection.v1",
        "authority": "development_only_no_release_trust",
        "family_id": FAMILY_ID,
        "packet_id": PACKET_ID,
        "proposal_feature_key": "projection-engine",
        "semantic_packet": packet,
        "source_routes": [
            {
                "source_id": "application",
                "start_line": 1,
                "end_line": 2,
                "route_path": "source-route/application-L1-L2.txt",
                "source_sha256": SHA_A,
                "span_sha256": hashlib.sha256(route_raw).hexdigest(),
                "span_size_bytes": len(route_raw),
            }
        ],
        "public_contract": {
            "target_paths": ["app/src/ppat/projection.py"],
            "writer_test_namespace": namespace,
            "writer_test_path": test_path,
            "writer_node_ids": nodes,
            "acceptance_predicates": list(packet["acceptance_predicates"]),
            "non_goals": list(packet["non_goals"]),
        },
    }
    projection_raw = canonical_json_bytes(projection)
    projection_path = publication / "candidate-projection.json"
    projection_path.write_bytes(projection_raw)
    red = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-c",
        "/dev/null",
        "--rootdir=.",
        "--noconftest",
        "-p",
        "no:cacheprovider",
        "--color=no",
        "-vv",
        *nodes,
    ]
    profile = {
        "schema_version": "ppat.packet-execution-profile.v1",
        "authority": "development_only_no_release_trust",
        "family_id": FAMILY_ID,
        "packet_id": PACKET_ID,
        "candidate_projection_sha256": hashlib.sha256(projection_raw).hexdigest(),
        "admitted_family_sha256": SHA_A,
        "registry_entry_sha256": SHA_B,
        "registry_head_sha256": SHA_C,
        "spec_admission_sha256": SHA_D,
        "policy_lock_sha256": "e" * 64,
        "catalog_lock_sha256": "7" * 64,
        "base": {"commit": "1" * 40, "tree": "2" * 40},
        "attempt_base": {"commit": "1" * 40, "tree": "2" * 40},
        "runtime_identity_sha256": "f" * 64,
        "model": {"id": "claude-opus-4-8"},
        "target_paths": ["app/src/ppat/projection.py"],
        "baseline_targets": [
            {"path": "app/src/ppat/projection.py", "state": "absent"}
        ],
        "test_execution": {
            "writer_node_ids": nodes,
            "red_exact_nodes": red,
            "green_exact_nodes": red,
            "full_suite": [
                "/usr/bin/python3",
                "-I",
                "-B",
                "-m",
                "pytest",
                "-c",
                "/dev/null",
                "--rootdir=/workspace/app",
                "-p",
                "no:cacheprovider",
                "--color=no",
                "-q",
                "/workspace/app/tests",
            ],
        },
        "dependency_resolution": {
            "build_requires": [
                {
                    "kind": "external",
                    "prerequisite_kind": "python_module",
                    "subject_id": "python-module:numpy",
                    "evidence_sha256": "8" * 64,
                    "state": "satisfied",
                }
            ],
            "consumes_or_binds": [],
            "verification_requires": [],
            "activation_requires": [],
        },
        "generation": {
            "attempt_id": "attempt-0",
            "attempt_number": 0,
            "execution_class": "local",
            "feature_id": FEATURE_ID,
            "parent_design_feature": "projection-engine",
        },
        "trusted_lineage": {},
        "initial_evidence": {
            "baseline_targets": [
                {"path": "app/src/ppat/projection.py", "state": "absent"}
            ],
            "source_routes": [
                {
                    "route_path": "source-route/application-L1-L2.txt",
                    "span_sha256": hashlib.sha256(route_raw).hexdigest(),
                    "span_size_bytes": len(route_raw),
                }
            ],
        },
        "expected_artifacts": {
            "output": dict(packet["output"]),
            "production_paths": ["app/src/ppat/projection.py"],
            "writer_node_ids": nodes,
            "writer_test_path": test_path,
        },
        "capability_profile": {
            "network": "provider-broker-only-for-semantic-roles",
            "candidate": "packet-targets-rw-otherwise-ro",
            "tests": "writer-namespace-rw-otherwise-ro",
            "git": "absent",
            "controller_state": "absent",
            "provider": "controller-brokered-pinned-opus",
        },
        "resource_profile": {
            "memory_bytes": 1024,
            "pids": 32,
            "output_bytes": 4096,
            "test_timeout_seconds": 30,
            "semantic_turn_cap": None,
            "semantic_cost_cap": None,
        },
        "locks": sorted(
            [
                f"family:{FAMILY_ID}",
                f"packet:{PACKET_ID}",
                f"writer:{test_path}",
                "target:app/src/ppat/projection.py",
            ]
        ),
    }
    attempt_payload = {
        "attempt_id": "attempt-0",
        "attempt_number": 0,
        "family_id": FAMILY_ID,
        "feature_id": FEATURE_ID,
        "packet_id": PACKET_ID,
        "previous_attempt_receipt_sha256": None,
        "registry_entry_sha256": SHA_B,
        "attempt_base_commit": "1" * 40,
        "attempt_base_tree": "2" * 40,
    }
    attempt_digest = hashlib.sha256(
        json.dumps(attempt_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    profile["trusted_lineage"] = {
        "admitted_family_sha256": SHA_A,
        "attempt_base_commit": "1" * 40,
        "attempt_base_tree": "2" * 40,
        "attempt_lineage_sha256": attempt_digest,
        "base_commit": "1" * 40,
        "base_tree": "2" * 40,
        "campaign_identity_sha256": "4" * 64,
        "catalog_lock_sha256": "7" * 64,
        "family_id": FAMILY_ID,
        "packet_id": PACKET_ID,
        "plan_canonical_sha256": "5" * 64,
        "proposal_feature_key": "projection-engine",
        "previous_attempt_receipt_sha256": None,
        "registry_entry_sha256": SHA_B,
        "registry_head_sha256": SHA_C,
        "registry_sequence": 1,
        "source_bundle_sha256": "6" * 64,
        "spec_admission_sha256": SHA_D,
    }
    profile_raw = canonical_json_bytes(profile)
    profile_path = publication / "packet-execution-profile.json"
    profile_path.write_bytes(profile_raw)
    env = {
        "BOB_ADMITTED_PACKET_REQUIRED": "1",
        "BOB_PACKET_PROJECTION": str(projection_path),
        "BOB_PACKET_PROJECTION_SHA256": hashlib.sha256(projection_raw).hexdigest(),
        "BOB_PACKET_EXECUTION_PROFILE": str(profile_path),
        "BOB_PACKET_EXECUTION_PROFILE_SHA256": hashlib.sha256(profile_raw).hexdigest(),
    }
    return workspace, projection_path, profile_path, env, projection, profile


def _rewrite(path: Path, value: dict, env: dict[str, str], digest_name: str) -> None:
    raw = canonical_json_bytes(value)
    path.write_bytes(raw)
    env[digest_name] = hashlib.sha256(raw).hexdigest()


def test_absent_profile_preserves_legacy_behavior(tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    assert load_admitted_packet_context(workspace=workspace, environ={}) is None


def test_valid_two_file_profile_binds_projection_routes_and_commands(tmp_path: Path) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None
    assert context.feature_id == FEATURE_ID
    assert context.writer_node_ids[-1].endswith("::test_acceptance_002")
    assert context.source_routes[0].content == "line one\nline two\n"
    assert context.protected_evidence_bindings["registry_entry_sha256"] == SHA_B


def test_pending_verification_dependency_allows_generation_dispatch(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    row = profile["dependency_resolution"]["build_requires"].pop()
    row["state"] = "pending"
    profile["dependency_resolution"]["verification_requires"].append(row)
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None
    assert context.execution_profile["dependency_resolution"][
        "verification_requires"
    ][0]["state"] == "pending"


def test_pending_build_dependency_blocks_generation_dispatch(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile["dependency_resolution"]["build_requires"][0]["state"] = "pending"
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="build_requires.*not satisfied"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_safe_model_assignment_omits_every_protected_controller_identity(tmp_path: Path) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None
    rendered = json.dumps(context.safe_model_assignment(), sort_keys=True)
    for forbidden in (
        "registry_entry_sha256",
        "registry_head_sha256",
        "spec_admission_sha256",
        "runtime_identity_sha256",
        "trusted_lineage",
        "base",
        SHA_B,
        SHA_C,
        SHA_D,
    ):
        assert forbidden not in rendered


def test_packet_writer_prompt_uses_only_safe_projection(tmp_path: Path) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None
    prompt = build_test_writer_prompt(
        feature_id=FEATURE_ID,
        feature_title="BROAD PARENT SECRET",
        feature_description="registry_entry_sha256 should never appear",
        acceptance_criteria=context.acceptance_predicates,
        principal_nonce="abc",
        allowed_test_roots=("app/tests",),
        test_namespace=context.writer_test_namespace,
        additional_context="spec_admission_sha256",
        packet_context=context,
    )
    assert "BROAD PARENT SECRET" not in prompt
    assert "registry_entry_sha256" not in prompt
    assert "spec_admission_sha256" not in prompt
    assert context.writer_test_path in prompt


@pytest.mark.parametrize(
    "missing",
    [
        "BOB_PACKET_PROJECTION",
        "BOB_PACKET_PROJECTION_SHA256",
        "BOB_PACKET_EXECUTION_PROFILE",
        "BOB_PACKET_EXECUTION_PROFILE_SHA256",
    ],
)
def test_required_or_partial_configuration_fails_closed(tmp_path: Path, missing: str) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    env.pop(missing)
    with pytest.raises(AdmittedPacketError, match="incomplete"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_projection_tamper_is_rejected_before_parsing(tmp_path: Path) -> None:
    workspace, projection_path, _, env, _, _ = _documents(tmp_path)
    projection_path.write_bytes(projection_path.read_bytes() + b" ")
    with pytest.raises(AdmittedPacketError, match="digest"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_noncanonical_profile_is_rejected_even_with_matching_digest(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    raw = json.dumps(profile, indent=2, sort_keys=True).encode() + b"\n"
    profile_path.write_bytes(raw)
    env["BOB_PACKET_EXECUTION_PROFILE_SHA256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(AdmittedPacketError, match="canonical"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_stale_projection_binding_is_rejected(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile["candidate_projection_sha256"] = "0" * 64
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="stale projection"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_sibling_packet_confusion_is_rejected(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile["packet_id"] = "ppat-packet-" + "9" * 32
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="sibling confusion"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_profile_and_parent_symlinks_are_rejected(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, _ = _documents(tmp_path)
    actual = profile_path.with_suffix(".actual")
    profile_path.rename(actual)
    profile_path.symlink_to(actual.name)
    with pytest.raises(AdmittedPacketError, match="opened safely"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_hardlinked_profile_is_rejected(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, _ = _documents(tmp_path)
    os.link(profile_path, profile_path.with_suffix(".alias"))
    with pytest.raises(AdmittedPacketError, match="single-link"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_controller_documents_inside_candidate_workspace_are_rejected(tmp_path: Path) -> None:
    workspace, projection_path, _, env, _, _ = _documents(tmp_path)
    unsafe = workspace / "projection.json"
    unsafe.write_bytes(projection_path.read_bytes())
    env["BOB_PACKET_PROJECTION"] = str(unsafe)
    with pytest.raises(AdmittedPacketError, match="outside"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_route_tamper_and_hardlink_are_rejected(tmp_path: Path) -> None:
    workspace, projection_path, _, env, _, _ = _documents(tmp_path)
    route = projection_path.parent / "source-route" / "application-L1-L2.txt"
    route.write_text("tampered\n")
    with pytest.raises(AdmittedPacketError, match="expected regular|mismatch"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, projection_path, _, env, _, _ = _documents(tmp_path / "again")
    route = projection_path.parent / "source-route" / "application-L1-L2.txt"
    os.link(route, route.with_suffix(".alias"))
    with pytest.raises(AdmittedPacketError, match="expected regular"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_unknown_projection_and_profile_keys_are_rejected(tmp_path: Path) -> None:
    workspace, projection_path, _, env, projection, _ = _documents(tmp_path)
    projection["admission"] = "forged"
    _rewrite(projection_path, projection, env, "BOB_PACKET_PROJECTION_SHA256")
    with pytest.raises(AdmittedPacketError, match="keys mismatch"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, profile_path, env, _, profile = _documents(tmp_path / "again")
    profile["extra"] = "forged"
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="keys mismatch"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_target_node_and_command_confusion_are_rejected(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile["target_paths"] = ["app/src/ppat/sibling.py"]
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="target paths differ"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, profile_path, env, _, profile = _documents(tmp_path / "nodes")
    profile["test_execution"]["writer_node_ids"][0] += "_sibling"
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="deterministic|expected artifacts"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, profile_path, env, _, profile = _documents(tmp_path / "command")
    profile["test_execution"]["green_exact_nodes"] = ["pytest", "sibling.py"]
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="exact packet nodes"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_broad_feature_and_extra_writer_or_production_paths_are_rejected(tmp_path: Path) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None
    with pytest.raises(AdmittedPacketError, match="broader/different"):
        assert_feature_matches_packet(
            context,
            feature_id=FEATURE_ID,
            acceptance_criteria=("build the entire PPAT application",),
        )
    with pytest.raises(AdmittedPacketError, match="outside"):
        assert_packet_change_paths(
            context,
            ["app/src/ppat/projection.py", "app/src/ppat/sibling.py"],
            include_test=False,
            label="bundle",
        )
    with pytest.raises(AdmittedPacketError, match="exactly"):
        assert_exact_writer_result(
            context,
            namespace=context.writer_test_namespace,
            test_files=(context.writer_test_path, "app/tests/extra.py"),
            collected_node_ids=context.writer_node_ids,
            test_argv=context.red_test_command,
        )


def test_binding_payload_carries_protected_identity_without_release_trust(tmp_path: Path) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None
    payload = packet_binding_payload(context, role="evaluator", session_id="session-3")
    assert payload["authority"] == "development_only_no_release_trust"
    assert payload["family_id"] == FAMILY_ID
    assert payload["packet_id"] == PACKET_ID
    assert payload["registry_entry_sha256"] == SHA_B
    assert payload["provider_session_id"] == "session-3"
    assert "release" not in payload


def test_projection_mutation_helper_does_not_hide_stale_profile(tmp_path: Path) -> None:
    workspace, projection_path, _, env, projection, _ = _documents(tmp_path)
    mutated = copy.deepcopy(projection)
    mutated["semantic_packet"]["observable_behavior"] = "sibling behavior"
    _rewrite(projection_path, mutated, env, "BOB_PACKET_PROJECTION_SHA256")
    with pytest.raises(AdmittedPacketError, match="stale projection"):
        load_admitted_packet_context(workspace=workspace, environ=env)


@pytest.mark.parametrize(
    ("section", "extra_key"),
    [
        ("semantic_packet", "controller_digest"),
        ("public_contract", "admission"),
    ],
)
def test_unknown_nested_projection_keys_are_rejected(
    tmp_path: Path, section: str, extra_key: str
) -> None:
    workspace, projection_path, _, env, projection, _ = _documents(tmp_path)
    projection[section][extra_key] = "forged"
    _rewrite(projection_path, projection, env, "BOB_PACKET_PROJECTION_SHA256")
    with pytest.raises(AdmittedPacketError, match="keys mismatch"):
        load_admitted_packet_context(workspace=workspace, environ=env)


@pytest.mark.parametrize(
    ("section", "extra_key"),
    [
        ("generation", "sibling_packet"),
        ("trusted_lineage", "release_verdict"),
        ("initial_evidence", "untrusted"),
        ("expected_artifacts", "extra_path"),
        ("capability_profile", "shell"),
        ("resource_profile", "gpu_count"),
    ],
)
def test_unknown_nested_controller_profile_keys_are_rejected(
    tmp_path: Path, section: str, extra_key: str
) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile[section][extra_key] = "forged"
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="keys mismatch"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_attempt_lineage_and_previous_receipt_are_cryptographically_bound(
    tmp_path: Path,
) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile["generation"]["attempt_id"] = "substituted-attempt"
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="attempt lineage"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, profile_path, env, _, profile = _documents(tmp_path / "previous")
    profile["trusted_lineage"]["previous_attempt_receipt_sha256"] = "7" * 64
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="attempt lineage"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_capability_widening_and_semantic_resource_caps_are_rejected(
    tmp_path: Path,
) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile["capability_profile"]["git"] = "read-write"
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="capability"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, profile_path, env, _, profile = _documents(tmp_path / "cap")
    profile["resource_profile"]["semantic_turn_cap"] = 10
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="semantic orchestration cap"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_stale_baseline_and_candidate_path_aliases_fail_closed(tmp_path: Path) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    target = workspace / "app" / "src" / "ppat" / "projection.py"
    target.write_text("changed after admission\n")
    with pytest.raises(AdmittedPacketError, match="baseline is stale"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, _, env, _, _ = _documents(tmp_path / "symlink")
    target = workspace / "app" / "src" / "ppat" / "projection.py"
    target.symlink_to("elsewhere.py")
    with pytest.raises(AdmittedPacketError, match="opened safely"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, profile_path, env, _, profile = _documents(tmp_path / "hardlink")
    target = workspace / "app" / "src" / "ppat" / "projection.py"
    target.write_text("present\n")
    alias = workspace / "app" / "src" / "ppat" / "alias.py"
    os.link(target, alias)
    raw = target.read_bytes()
    present = {
        "path": "app/src/ppat/projection.py",
        "state": "present",
        "mode": target.stat().st_mode & 0o7777,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    profile["baseline_targets"] = [present]
    profile["initial_evidence"]["baseline_targets"] = [present]
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="single-link"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_writer_namespace_alias_or_hardlink_is_rejected(tmp_path: Path) -> None:
    workspace, _, _, env, projection, _ = _documents(tmp_path)
    namespace = workspace / projection["public_contract"]["writer_test_namespace"]
    namespace.parent.mkdir(parents=True, exist_ok=True)
    real = workspace / "real-writer-dir"
    real.mkdir()
    namespace.symlink_to(real, target_is_directory=True)
    with pytest.raises(AdmittedPacketError, match="symlink|alias"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, _, env, projection, _ = _documents(tmp_path / "hardlink")
    path = workspace / projection["public_contract"]["writer_test_path"]
    path.parent.mkdir(parents=True)
    path.write_text("def test_acceptance_001(): pass\n")
    os.link(path, path.with_suffix(".alias"))
    with pytest.raises(AdmittedPacketError, match="single-link"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_red_command_prefix_and_extra_test_nodes_are_rejected(tmp_path: Path) -> None:
    workspace, _, profile_path, env, _, profile = _documents(tmp_path)
    profile["test_execution"]["red_exact_nodes"][0] = "/tmp/fake-python"
    profile["test_execution"]["green_exact_nodes"][0] = "/tmp/fake-python"
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="prefix"):
        load_admitted_packet_context(workspace=workspace, environ=env)

    workspace, _, profile_path, env, _, profile = _documents(tmp_path / "extra")
    extra = profile["test_execution"]["writer_node_ids"][0].replace(
        "001", "003"
    )
    profile["test_execution"]["writer_node_ids"].append(extra)
    profile["test_execution"]["red_exact_nodes"].append(extra)
    profile["test_execution"]["green_exact_nodes"].append(extra)
    _rewrite(profile_path, profile, env, "BOB_PACKET_EXECUTION_PROFILE_SHA256")
    with pytest.raises(AdmittedPacketError, match="expected artifacts|deterministic"):
        load_admitted_packet_context(workspace=workspace, environ=env)


def test_packet_writer_creates_and_collects_exactly_prescribed_file_and_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None

    class FakeExecutor:
        def __init__(self, *, default_options):
            self.options = default_options

        async def execute(self, prompt, *, options):
            nonce = re.search(
                r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE
            ).group(1)
            path = workspace / context.writer_test_path
            path.write_text(
                "def test_acceptance_001():\n"
                "    observed = 1\n"
                "    assert observed == 2\n\n"
                "def test_acceptance_002():\n"
                "    observed = 'invalid'\n"
                "    assert observed == 'rejected'\n"
            )
            payload = {
                "schema_version": SCHEMA_VERSION,
                "role": ROLE_NAME,
                "principal_nonce": nonce,
                "status": "completed",
                "feature_id": FEATURE_ID,
                "test_files": [context.writer_test_path],
                "test_command": list(context.green_test_command),
                "criterion_coverage": [
                    {"criterion_index": index, "test_ids": [node]}
                    for index, node in enumerate(context.writer_node_ids)
                ],
                "notes": [],
            }
            return ExecutionResult(
                text="```json\n" + json.dumps(payload) + "\n```",
                session_id="packet-writer-session",
                tool_uses=["Read", "Write"],
            )

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor", FakeExecutor
    )
    result = asyncio.run(
        run_independent_test_writer(
            feature_id=FEATURE_ID,
            feature_title="must not leak",
            feature_description="must not leak",
            acceptance_criteria=context.acceptance_predicates,
            cwd=workspace,
            options=ClaudeCodeOptions(
                cwd=str(workspace), model="claude-opus-4-8"
            ),
            allowed_test_roots=("app/tests",),
            packet_context=context,
        )
    )
    assert result.ok
    assert result.test_files == (context.writer_test_path,)
    assert result.evidence.test_execution is not None
    assert result.evidence.test_execution.collected_node_ids == context.writer_node_ids
    assert result.evidence.test_execution.test_argv == context.red_test_command
    assert result.evidence.packet_binding == packet_binding_payload(
        context,
        role=ROLE_NAME,
        session_id="packet-writer-session",
    )


def test_packet_writer_extra_file_fails_before_any_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _, _, env, _, _ = _documents(tmp_path)
    context = load_admitted_packet_context(workspace=workspace, environ=env)
    assert context is not None

    class MaliciousExecutor:
        def __init__(self, *, default_options):
            pass

        async def execute(self, prompt, *, options):
            nonce = re.search(
                r"^PRINCIPAL_NONCE=([0-9a-f]+)$", prompt, re.MULTILINE
            ).group(1)
            exact = workspace / context.writer_test_path
            exact.write_text("def test_acceptance_001():\n    assert 1 == 2\n")
            extra = exact.parent / "test_sibling.py"
            extra.write_text("def test_sibling():\n    assert 1 == 2\n")
            payload = {
                "schema_version": SCHEMA_VERSION,
                "role": ROLE_NAME,
                "principal_nonce": nonce,
                "status": "completed",
                "feature_id": FEATURE_ID,
                "test_files": [context.writer_test_path, extra.relative_to(workspace).as_posix()],
                "test_command": list(context.green_test_command),
                "criterion_coverage": [
                    {"criterion_index": index, "test_ids": [node]}
                    for index, node in enumerate(context.writer_node_ids)
                ],
                "notes": [],
            }
            return ExecutionResult(
                text="```json\n" + json.dumps(payload) + "\n```",
                session_id="malicious-writer",
            )

    monkeypatch.setattr(
        "bob.orchestrator.independent_test_writer.ClaudeExecutor",
        MaliciousExecutor,
    )
    result = asyncio.run(
        run_independent_test_writer(
            feature_id=FEATURE_ID,
            feature_title="packet",
            feature_description="packet",
            acceptance_criteria=context.acceptance_predicates,
            cwd=workspace,
            options=ClaudeCodeOptions(cwd=str(workspace), model="claude-opus-4-8"),
            allowed_test_roots=("app/tests",),
            packet_context=context,
        )
    )
    assert result.outcome == "scope_violation"
    assert result.evidence.unauthorized_changes == (
        (Path(context.writer_test_namespace) / "test_sibling.py").as_posix(),
    )
