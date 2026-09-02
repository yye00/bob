"""No-provider and adversarial tests for proposal-only packet planning."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from bob.atomic_packet_planner import (
    PACKET_COMPILER_ROLE,
    PACKET_FAMILY_SCHEMA,
    PACKET_MODEL,
    PACKET_REVIEW_SCHEMA,
    PACKET_REVIEWER_ROLE,
    AtomicPacketContainmentError,
    AtomicPacketValidationError,
    PacketRoleExecution,
    _execute_packet_role,
    _parse_model_json_response,
    _write_canonical_output,
    build_packet_obligations,
    canonical_json_bytes,
    canonical_sha256,
    compile_packet_family_proposal,
    controller_completion_marker,
    load_canonical_proposal_witness,
    load_feature_plan,
    load_public_catalog_projection,
    review_packet_family_proposal,
    validate_packet_family_proposal,
    validate_packet_family_review,
)
from bob.cli import main
from bob.feature_planner import PlannerSourceFile


def _feature() -> dict:
    return {
        "key": "PPAT-M0-UNIT",
        "name": "Unit contract child",
        "description": "Implement one bounded unit-profile behavior.",
        "priority": 1,
        "depends_on": [],
        "acceptance_criteria": [
            "Returns the canonical unit for a known quantity kind.",
            "Rejects an unknown quantity kind with a typed error.",
        ],
        "execution_class": "local",
        "source_trace": ["spec:L1-L2"],
    }


def _plan() -> dict:
    return {"name": "ppat", "features": [_feature()]}


def _catalog() -> dict:
    return {
        "schema_version": "ppat.public-packet-catalog-projection.v1",
        "authority": "development_only_no_release_trust",
        "entries": [
            {
                "subject_id": "api:unit-profile:1",
                "kind": "api_contract",
                "availability_stage": "build",
            },
            {
                "subject_id": "fixture:unit-profile:public",
                "kind": "fixture",
                "availability_stage": "verification",
            },
            {
                "subject_id": "oracle:unit-contract:public",
                "kind": "oracle",
                "availability_stage": "verification",
            },
            {
                "subject_id": "profile:local-python-public",
                "kind": "acceptance_profile",
                "availability_stage": "build",
            },
            {
                "subject_id": "python_module",
                "kind": "artifact_kind",
                "availability_stage": "build",
            },
            {
                "subject_id": "urn:ppat:unit-profile:1",
                "kind": "schema",
                "availability_stage": "build",
            },
        ],
    }


def _sources() -> tuple[PlannerSourceFile, ...]:
    text = "Canonical unit behavior\nUnknown values reject\n"
    return (
        PlannerSourceFile(
            source_id="spec",
            filename="application-spec.txt",
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            line_count=2,
        ),
    )


def _span(start: int = 1, end: int = 2) -> dict:
    return {"source_id": "spec", "start_line": start, "end_line": end}


def _packet(slug: str = "unit-contract") -> dict:
    return {
        "slug": slug,
        "parent_design_feature": "PPAT-M0-UNIT",
        "source_spans": [_span()],
        "authority_boundary": "unit_contract",
        "observable_behavior": "Map one known quantity kind and reject unknown values.",
        "primary_artifact": {
            "kind": "python_module",
            "target_paths": ["app/src/power_sim/contracts/unit_profile.py"],
        },
        "inputs": {
            "schema_ids": ["urn:ppat:unit-profile:1"],
            "fixture_ids": ["fixture:unit-profile:public"],
            "package_lock_ids": [],
            "oracle_ids": ["oracle:unit-contract:public"],
        },
        "output": {
            "kind": "in_process",
            "schema_id": None,
            "path": None,
            "api_contract": "api:unit-profile:1",
            "persistence": "forbidden",
        },
        "error_map": [
            {"condition": "Unknown quantity kind", "outcome": "unknown_quantity_kind"}
        ],
        "dependencies": {
            "build_requires": [],
            "consumes_or_binds": ["urn:ppat:unit-profile:1"],
            "verification_requires": ["oracle:unit-contract:public"],
            "activation_requires": [],
        },
        "external_prerequisite_ids": [],
        "acceptance_profile_id": "profile:local-python-public",
        "acceptance_predicates": [
            "Known input returns its exact canonical unit.",
            "Unknown input produces the typed closed error.",
        ],
        "non_goals": ["Prefix conversion", "Hardware telemetry"],
    }


def _proposal(*packets: dict) -> dict:
    chosen = list(packets or (_packet(),))
    slugs = [packet["slug"] for packet in chosen]
    return {
        "schema_version": PACKET_FAMILY_SCHEMA,
        "proposal_feature_key": "PPAT-M0-UNIT",
        "packets": chosen,
        "loss_ledger": [
            {
                "obligation_id": "criterion-001",
                "source_span": _span(),
                "packet_slugs": slugs,
            },
            {
                "obligation_id": "criterion-002",
                "source_span": _span(),
                "packet_slugs": slugs,
            },
            {
                "obligation_id": "source-obligation-001",
                "source_span": _span(),
                "packet_slugs": slugs,
            },
        ],
    }


def _review(proposal: dict, recommendation: str = "ready") -> dict:
    digest = canonical_sha256(proposal)
    slug = proposal["packets"][0]["slug"]
    return {
        "schema_version": PACKET_REVIEW_SCHEMA,
        "proposal_feature_key": "PPAT-M0-UNIT",
        "family_proposal_sha256": digest,
        "criterion_coverage": [
            {
                "obligation_id": "criterion-001",
                "status": "covered",
                "packet_slugs": [slug],
                "explanation": "The known-value predicate covers it.",
            },
            {
                "obligation_id": "criterion-002",
                "status": "covered",
                "packet_slugs": [slug],
                "explanation": "The typed negative predicate covers it.",
            },
        ],
        "source_obligation_coverage": [
            {
                "obligation_id": "source-obligation-001",
                "status": "covered",
                "packet_slugs": [slug],
                "explanation": "The exact assigned source span is represented.",
            }
        ],
        "findings": [],
        "recommendation": recommendation,
    }


def _fenced(value: object) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False) + "\n```"


def _validate(value: dict) -> dict:
    return validate_packet_family_proposal(
        value,
        feature=_feature(),
        sources=_sources(),
        obligations=build_packet_obligations(_feature()),
    )


def test_valid_semantic_packet_family_and_loss_ledger_round_trip():
    proposal = _proposal()
    assert _validate(copy.deepcopy(proposal)) == proposal
    assert json.loads(canonical_json_bytes(proposal)) == proposal
    assert canonical_json_bytes(proposal).endswith(b"\n")


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "digest",
        "result_hash",
        "runtime_identity",
        "base_commit",
        "admission_state",
        "verdict",
        "test_command",
        "argv",
        "candidate_lineage",
        "release_receipt",
        "attempt_nonce",
    ],
)
def test_controller_reserved_model_keys_are_rejected_recursively(forbidden_key):
    proposal = _proposal()
    proposal["packets"][0]["inputs"][forbidden_key] = "model-controlled"
    with pytest.raises(AtomicPacketValidationError, match="controller-reserved"):
        _validate(proposal)


def test_unknown_non_reserved_nested_key_is_rejected():
    proposal = _proposal()
    proposal["packets"][0]["primary_artifact"]["surprise"] = True
    with pytest.raises(AtomicPacketValidationError, match="unknown surprise"):
        _validate(proposal)


@pytest.mark.parametrize("line", [0, 3, 999])
def test_source_span_must_be_inside_exact_manifest_bounds(line):
    proposal = _proposal()
    proposal["packets"][0]["source_spans"] = [_span(line, line)]
    with pytest.raises(AtomicPacketValidationError, match="line range"):
        _validate(proposal)


def test_packet_span_cannot_escape_owning_feature_span():
    sources = (PlannerSourceFile("spec", "application-spec.txt", "0" * 64, 22),)
    proposal = _proposal()
    proposal["packets"][0]["source_spans"] = [_span(2, 3)]
    with pytest.raises(AtomicPacketValidationError, match="escapes"):
        validate_packet_family_proposal(proposal, feature=_feature(), sources=sources)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown"])
def test_loss_ledger_is_bijective_over_assigned_obligations(mutation):
    proposal = _proposal()
    if mutation == "missing":
        proposal["loss_ledger"].pop()
    elif mutation == "duplicate":
        proposal["loss_ledger"][2]["obligation_id"] = "criterion-001"
    else:
        proposal["loss_ledger"][2]["obligation_id"] = "invented-obligation"
    with pytest.raises(
        AtomicPacketValidationError, match="loss_ledger|duplicate|unknown"
    ):
        _validate(proposal)


def test_loss_ledger_span_must_be_controller_assigned_not_merely_in_bounds():
    proposal = _proposal()
    proposal["loss_ledger"][0]["source_span"] = _span(1, 1)
    with pytest.raises(AtomicPacketValidationError, match="not assigned"):
        _validate(proposal)


def test_every_packet_must_be_referenced_from_loss_ledger():
    second = _packet("unreferenced")
    proposal = _proposal(_packet(), second)
    for entry in proposal["loss_ledger"]:
        entry["packet_slugs"] = ["unit-contract"]
    with pytest.raises(AtomicPacketValidationError, match="every proposed packet"):
        _validate(proposal)


def test_ledger_mapping_must_be_covered_by_mapped_packet_source_spans():
    proposal = _proposal()
    proposal["packets"][0]["source_spans"] = [_span(1, 1)]
    with pytest.raises(AtomicPacketValidationError, match="do not cover"):
        _validate(proposal)


def test_split_packets_may_collectively_cover_one_ledger_span():
    first = _packet("first-half")
    first["source_spans"] = [_span(1, 1)]
    second = _packet("second-half")
    second["source_spans"] = [_span(2, 2)]
    proposal = _proposal(first, second)
    assert _validate(proposal) == proposal


def test_build_dependency_must_be_sibling_or_known_planner_dependency():
    proposal = _proposal()
    proposal["packets"][0]["dependencies"]["build_requires"] = ["invented-packet"]
    with pytest.raises(AtomicPacketValidationError, match="undeclared/unknown"):
        _validate(proposal)


def test_dependency_cannot_reference_own_packet_slug():
    proposal = _proposal()
    proposal["packets"][0]["dependencies"]["build_requires"] = ["unit-contract"]
    with pytest.raises(AtomicPacketValidationError, match="self-dependency"):
        _validate(proposal)


def test_dependency_cannot_be_repeated_across_relation_classes():
    proposal = _proposal()
    dependency = "oracle:unit-contract:public"
    proposal["packets"][0]["dependencies"]["consumes_or_binds"].append(dependency)
    with pytest.raises(AtomicPacketValidationError, match="repeats dependency"):
        _validate(proposal)


def test_sibling_build_dependency_cycle_is_rejected():
    first = _packet("first")
    second = _packet("second")
    first["dependencies"]["build_requires"] = ["second"]
    second["dependencies"]["build_requires"] = ["first"]
    proposal = _proposal(first, second)
    with pytest.raises(
        AtomicPacketValidationError, match="scheduling dependency cycle"
    ):
        _validate(proposal)


def test_verification_activation_mixed_cycle_is_rejected():
    first = _packet("first")
    second = _packet("second")
    first["dependencies"]["verification_requires"] = ["second"]
    second["dependencies"]["activation_requires"] = ["first"]
    proposal = _proposal(first, second)
    with pytest.raises(
        AtomicPacketValidationError, match="scheduling dependency cycle"
    ):
        _validate(proposal)


def test_known_planner_parent_dependency_is_allowed():
    feature = _feature()
    feature["depends_on"] = ["PPAT-M0-FOUNDATION"]
    proposal = _proposal()
    proposal["packets"][0]["dependencies"]["build_requires"] = ["PPAT-M0-FOUNDATION"]
    assert (
        validate_packet_family_proposal(proposal, feature=feature, sources=_sources())
        == proposal
    )


def test_every_planner_dependency_must_be_preserved_and_retyped():
    feature = _feature()
    feature["depends_on"] = ["PPAT-M0-FOUNDATION"]
    with pytest.raises(AtomicPacketValidationError, match="drops planner dependencies"):
        validate_packet_family_proposal(
            _proposal(), feature=feature, sources=_sources()
        )


@pytest.mark.parametrize(
    "claim",
    [
        "admitted",
        "admission-approved",
        "verdict-passed",
        "runtime-identity-verified",
        "provider-session-attested",
        "release-authorized",
        "production-ready",
        "authority-granted",
    ],
)
def test_outcome_fields_cannot_claim_controller_state(claim):
    proposal = _proposal()
    proposal["packets"][0]["error_map"][0]["outcome"] = claim
    with pytest.raises(AtomicPacketValidationError, match="controller authority/state"):
        _validate(proposal)


def test_problem_domain_text_and_reviewer_criticism_may_quote_reserved_words():
    proposal = _proposal()
    proposal["packets"][0]["observable_behavior"] = (
        "Reject a forged runtime identity and a quoted verdict token."
    )
    proposal["packets"][0]["acceptance_predicates"][0] = (
        "A literal TODO or TBD input is rejected as problem-domain data."
    )
    proposal["packets"][0]["error_map"][0]["outcome"] = "runtime_identity_invalid"
    assert _validate(proposal) == proposal
    review = _review(proposal)
    review["findings"] = [
        {
            "code": "IMPROPER-CLAIM",
            "severity": "info",
            "packet_slugs": ["unit-contract"],
            "message": "The text discusses a verdict but does not issue one.",
        }
    ]
    assert (
        validate_packet_family_review(
            review,
            feature=_feature(),
            proposal=proposal,
            family_proposal_sha256=canonical_sha256(proposal),
        )
        == review
    )


@pytest.mark.parametrize(
    "placeholder", ["TBD", "TODO: later", "placeholder", "to be determined"]
)
def test_predicates_and_errors_cannot_be_placeholder_only(placeholder):
    proposal = _proposal()
    proposal["packets"][0]["acceptance_predicates"][0] = placeholder
    with pytest.raises(AtomicPacketValidationError, match="placeholder"):
        _validate(proposal)


def test_tagged_output_union_rejects_incompatible_fields():
    proposal = _proposal()
    proposal["packets"][0]["output"]["schema_id"] = "urn:smuggled"
    with pytest.raises(AtomicPacketValidationError, match="incompatible"):
        _validate(proposal)


@pytest.mark.parametrize("count", [0, 1, 6])
def test_packet_requires_two_to_five_observable_predicates(count):
    proposal = _proposal()
    proposal["packets"][0]["acceptance_predicates"] = [
        f"predicate {index}" for index in range(count)
    ]
    with pytest.raises(AtomicPacketValidationError, match="2..5"):
        _validate(proposal)


def test_parser_rejects_prose_duplicate_keys_and_nonfinite_values():
    with pytest.raises(AtomicPacketValidationError, match="exactly one"):
        _parse_model_json_response(
            "looks good\n" + _fenced(_proposal()), label="compiler"
        )
    with pytest.raises(AtomicPacketValidationError, match="duplicate JSON key"):
        _parse_model_json_response(
            '```json\n{"schema_version":"x","schema_version":"y"}\n```',
            label="compiler",
        )
    with pytest.raises(AtomicPacketValidationError, match="non-finite"):
        _parse_model_json_response('```json\n{"x":NaN}\n```', label="compiler")


def test_span_validation_uses_exact_bounds_across_twenty_two_sources():
    sources = tuple(
        PlannerSourceFile(
            source_id="spec" if index == 0 else f"reference-{index}",
            filename=(
                "application-spec.txt" if index == 0 else f"reference-{index:03d}.txt"
            ),
            sha256=f"{index:064x}",
            line_count=index + 1,
        )
        for index in range(22)
    )
    feature = _feature()
    feature["source_trace"] = ["reference-21:L22"]
    proposal = _proposal()
    exact_span = {
        "source_id": "reference-21",
        "start_line": 22,
        "end_line": 22,
    }
    proposal["packets"][0]["source_spans"] = [exact_span]
    for entry in proposal["loss_ledger"]:
        entry["source_span"] = exact_span
    assert (
        validate_packet_family_proposal(proposal, feature=feature, sources=sources)
        == proposal
    )
    proposal["packets"][0]["source_spans"][0]["end_line"] = 23
    with pytest.raises(AtomicPacketValidationError, match="line range"):
        validate_packet_family_proposal(proposal, feature=feature, sources=sources)


def test_review_is_complete_and_digest_echo_is_the_only_hash_key_exception():
    proposal = _proposal()
    review = _review(proposal)
    assert (
        validate_packet_family_review(
            review,
            feature=_feature(),
            proposal=proposal,
            family_proposal_sha256=canonical_sha256(proposal),
        )
        == review
    )
    review["findings"].append(
        {
            "code": "R1",
            "severity": "info",
            "packet_slugs": [],
            "message": "Informational note.",
            "prompt_hash": "0" * 64,
        }
    )
    with pytest.raises(AtomicPacketValidationError, match="controller-reserved"):
        validate_packet_family_review(
            review,
            feature=_feature(),
            proposal=proposal,
            family_proposal_sha256=canonical_sha256(proposal),
        )


def test_review_cannot_echo_an_alternate_family_digest():
    proposal = _proposal()
    review = _review(proposal)
    review["family_proposal_sha256"] = "0" * 64
    with pytest.raises(AtomicPacketValidationError, match="wrong proposal digest"):
        validate_packet_family_review(
            review,
            feature=_feature(),
            proposal=proposal,
            family_proposal_sha256=canonical_sha256(proposal),
        )


def test_ready_review_cannot_hide_gap_or_warning():
    proposal = _proposal()
    review = _review(proposal)
    review["criterion_coverage"][0]["status"] = "gap"
    review["criterion_coverage"][0]["packet_slugs"] = []
    with pytest.raises(AtomicPacketValidationError, match="conflicts"):
        validate_packet_family_review(
            review,
            feature=_feature(),
            proposal=proposal,
            family_proposal_sha256=canonical_sha256(proposal),
        )


def test_compile_uses_full_file_backed_sources_and_emits_controller_witness(
    monkeypatch,
):
    source = "Canonical unit behavior\nUnknown values reject\n"
    captured = {}

    def fake_execute(**kwargs):
        workspace = kwargs["workspace"]
        captured["workspace"] = workspace
        captured["prompt"] = kwargs["prompt"]
        captured["role"] = kwargs["role"]
        assert (workspace / "application-spec.txt").read_text() == source
        assignment = json.loads((workspace / "packet-assignment.json").read_text())
        assert assignment["role"] == PACKET_COMPILER_ROLE
        assert len(assignment["obligations"]) == 3
        assert assignment["public_catalog"] == _catalog()
        assert assignment["public_catalog_projection_sha256"] == canonical_sha256(
            _catalog()
        )
        return PacketRoleExecution(_fenced(_proposal()), "1" * 64)

    monkeypatch.setattr("bob.atomic_packet_planner._execute_packet_role", fake_execute)
    witness = compile_packet_family_proposal(
        spec_content=source,
        ref_texts=[],
        feature_plan=_plan(),
        feature_plan_sha256="2" * 64,
        feature_key="PPAT-M0-UNIT",
        public_catalog=_catalog(),
        public_catalog_projection_sha256=canonical_sha256(_catalog()),
    )
    assert witness["authority"] == "proposal_only"
    assert witness["controller_completion"] == controller_completion_marker()
    assert witness["controller_completion"]["direct_admission_forbidden"] is True
    provenance = witness["provenance"]
    assert provenance["role"] == PACKET_COMPILER_ROLE
    assert provenance["model"] == PACKET_MODEL
    assert provenance["family_proposal_sha256"] == canonical_sha256(_proposal())
    assert provenance["session_witness_sha256"] == "1" * 64
    assert provenance["attestation_status"] == "unsigned_observation_not_portable_proof"
    assert provenance["controller_signature_required"] is True
    assert provenance["public_catalog_projection_sha256"] == canonical_sha256(
        _catalog()
    )
    assert source not in captured["prompt"]
    assert len(captured["prompt"].encode()) < 64 * 1024
    assert not Path(captured["workspace"]).exists()


def _compiled_witness(monkeypatch, *, session: str = "1" * 64) -> dict:
    monkeypatch.setattr(
        "bob.atomic_packet_planner._execute_packet_role",
        lambda **kwargs: PacketRoleExecution(_fenced(_proposal()), session),
    )
    return compile_packet_family_proposal(
        spec_content="Canonical unit behavior\nUnknown values reject\n",
        ref_texts=[],
        feature_plan=_plan(),
        feature_plan_sha256="2" * 64,
        feature_key="PPAT-M0-UNIT",
        public_catalog=_catalog(),
        public_catalog_projection_sha256=canonical_sha256(_catalog()),
    )


def test_reviewer_is_fresh_role_and_binds_compiler_session(monkeypatch):
    proposal_witness = _compiled_witness(monkeypatch)

    def fake_review(**kwargs):
        assignment = json.loads(
            (kwargs["workspace"] / "packet-assignment.json").read_text()
        )
        assert kwargs["role"] == PACKET_REVIEWER_ROLE
        assert assignment["compiler_session_witness_sha256"] == "1" * 64
        return PacketRoleExecution(_fenced(_review(_proposal())), "3" * 64)

    monkeypatch.setattr("bob.atomic_packet_planner._execute_packet_role", fake_review)
    witness = review_packet_family_proposal(
        spec_content="Canonical unit behavior\nUnknown values reject\n",
        ref_texts=[],
        feature_plan=_plan(),
        feature_plan_sha256="2" * 64,
        proposal_witness=proposal_witness,
        public_catalog=_catalog(),
        public_catalog_projection_sha256=canonical_sha256(_catalog()),
    )
    assert witness["authority"] == "review_recommendation_only"
    assert witness["controller_completion"]["direct_admission_forbidden"] is True
    provenance = witness["provenance"]
    assert provenance["role"] == PACKET_REVIEWER_ROLE
    assert provenance["compiler_session_witness_sha256"] == "1" * 64
    assert provenance["session_witness_sha256"] == "3" * 64
    assert provenance["compiler_attestation_status"] == "unsigned_reloaded_claim"
    assert provenance["session_separation_proven"] is False
    assert provenance["controller_signature_required"] is True


def test_reviewer_rejects_same_provider_session(monkeypatch):
    proposal_witness = _compiled_witness(monkeypatch)
    monkeypatch.setattr(
        "bob.atomic_packet_planner._execute_packet_role",
        lambda **kwargs: PacketRoleExecution(_fenced(_review(_proposal())), "1" * 64),
    )
    with pytest.raises(
        AtomicPacketValidationError, match="claimed compiler provider session"
    ):
        review_packet_family_proposal(
            spec_content="Canonical unit behavior\nUnknown values reject\n",
            ref_texts=[],
            feature_plan=_plan(),
            feature_plan_sha256="2" * 64,
            proposal_witness=proposal_witness,
            public_catalog=_catalog(),
            public_catalog_projection_sha256=canonical_sha256(_catalog()),
        )


def test_reviewer_rejects_tampered_proposal_before_model_spawn(monkeypatch):
    witness = _compiled_witness(monkeypatch)
    witness["family_proposal"]["packets"][0]["observable_behavior"] = "Tampered"
    spawn = AsyncMock()
    monkeypatch.setattr("bob.atomic_packet_planner._execute_packet_role", spawn)
    with pytest.raises(AtomicPacketValidationError, match="semantic digest changed"):
        review_packet_family_proposal(
            spec_content="Canonical unit behavior\nUnknown values reject\n",
            ref_texts=[],
            feature_plan=_plan(),
            feature_plan_sha256="2" * 64,
            proposal_witness=witness,
            public_catalog=_catalog(),
            public_catalog_projection_sha256=canonical_sha256(_catalog()),
        )
    spawn.assert_not_called()


def test_hardened_executor_pins_exact_model_1m_role_and_provider_session(tmp_path):
    captured = {}

    def fake_options(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            cwd=kwargs["cwd"],
            model=kwargs["model"],
            max_turns=None,
            extra_args={**kwargs["extra_args"], "autocompact": "1M"},
            env={**kwargs["env"], "BOB_AGENT_ROLE": kwargs["agent_role"]},
            allowed_tools=kwargs["allowed_tools"],
            disallowed_tools=kwargs["disallowed_tools"],
            permission_mode=kwargs["permission_mode"],
            mcp_servers=kwargs["mcp_servers"],
        )

    executor = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                text=_fenced(_proposal()),
                is_error=False,
                error_message="",
                session_id="provider-session-one",
                tool_uses=["Read"],
            )
        )
    )
    with (
        patch(
            "bob.orchestrator.claude_executor.build_sub_agent_options",
            side_effect=fake_options,
        ),
        patch(
            "bob.orchestrator.claude_executor._attach_stderr_capture",
            side_effect=lambda options, buffer: options,
        ),
        patch(
            "bob.orchestrator.claude_executor.ClaudeExecutor",
            return_value=executor,
        ),
    ):
        execution = _execute_packet_role(
            workspace=tmp_path,
            prompt="read files",
            role=PACKET_COMPILER_ROLE,
            source_texts=(),
        )
    assert captured["model"] == PACKET_MODEL
    assert captured["max_turns"] is None
    assert captured["agent_role"] == PACKET_COMPILER_ROLE
    assert captured["allowed_tools"] == ["Read"]
    assert captured["mcp_servers"] == {}
    assert captured["permission_mode"] == "default"
    assert (
        execution.session_witness_sha256
        == hashlib.sha256(b"provider-session-one").hexdigest()
    )


def test_hardened_executor_rejects_missing_session_and_forbidden_tool(tmp_path):
    def fake_options(**kwargs):
        return SimpleNamespace(
            cwd=kwargs["cwd"],
            model=PACKET_MODEL,
            max_turns=None,
            extra_args={**kwargs["extra_args"], "autocompact": "1M"},
            env={"BOB_AGENT_ROLE": PACKET_COMPILER_ROLE},
            allowed_tools=kwargs["allowed_tools"],
            disallowed_tools=kwargs["disallowed_tools"],
            permission_mode=kwargs["permission_mode"],
            mcp_servers=kwargs["mcp_servers"],
        )

    result = SimpleNamespace(
        text=_fenced(_proposal()),
        is_error=False,
        error_message="",
        session_id="",
        tool_uses=["Bash"],
    )
    with (
        patch(
            "bob.orchestrator.claude_executor.build_sub_agent_options",
            side_effect=fake_options,
        ),
        patch(
            "bob.orchestrator.claude_executor._attach_stderr_capture",
            side_effect=lambda options, buffer: options,
        ),
        patch(
            "bob.orchestrator.claude_executor.ClaudeExecutor",
            return_value=SimpleNamespace(execute=AsyncMock(return_value=result)),
        ),pytest.raises(AtomicPacketValidationError, match="forbidden tools")
    ):
        _execute_packet_role(
            workspace=tmp_path,
            prompt="read files",
            role=PACKET_COMPILER_ROLE,
            source_texts=(),
        )


def test_hardened_executor_revalidates_options_after_stderr_capture(tmp_path):
    def fake_options(**kwargs):
        return SimpleNamespace(
            cwd=kwargs["cwd"],
            model=PACKET_MODEL,
            max_turns=None,
            extra_args={**kwargs["extra_args"], "autocompact": "1M"},
            env={**kwargs["env"], "BOB_AGENT_ROLE": PACKET_COMPILER_ROLE},
            allowed_tools=kwargs["allowed_tools"],
            disallowed_tools=kwargs["disallowed_tools"],
            permission_mode=kwargs["permission_mode"],
            mcp_servers=kwargs["mcp_servers"],
        )

    weakened = SimpleNamespace(
        cwd=tmp_path,
        model=PACKET_MODEL,
        max_turns=None,
        extra_args={"autocompact": "1M", "tools": "Read"},
        env={"BOB_AGENT_ROLE": PACKET_COMPILER_ROLE},
        allowed_tools=["Read"],
        disallowed_tools=[],
        permission_mode="default",
        mcp_servers={},
    )
    with (
        patch(
            "bob.orchestrator.claude_executor.build_sub_agent_options",
            side_effect=fake_options,
        ),
        patch(
            "bob.orchestrator.claude_executor._attach_stderr_capture",
            return_value=weakened,
        ),pytest.raises(AtomicPacketValidationError, match="not preserved")
    ):
        _execute_packet_role(
            workspace=tmp_path,
            prompt="read files",
            role=PACKET_COMPILER_ROLE,
            source_texts=(),
        )


def test_cli_commands_are_registered_and_proposal_output_is_canonical(tmp_path):
    plan_path = tmp_path / "features.json"
    spec_path = tmp_path / "spec.md"
    output = tmp_path / "proposal.json"
    catalog_path = tmp_path / "public-catalog.json"
    plan_path.write_bytes(canonical_json_bytes(_plan()))
    catalog_path.write_bytes(canonical_json_bytes(_catalog()))
    spec_path.write_text("Canonical unit behavior\nUnknown values reject\n")
    fake_witness = {
        "schema_version": "bob.packet-family-proposal-witness.v1",
        "authority": "proposal_only",
        "family_proposal": _proposal(),
        "provenance": {"test": True},
    }
    runner = CliRunner()
    with patch(
        "bob.atomic_packet_planner.compile_packet_family_proposal",
        return_value=fake_witness,
    ):
        result = runner.invoke(
            main,
            [
                "propose-task-packets",
                str(plan_path),
                "PPAT-M0-UNIT",
                "--spec",
                str(spec_path),
                "--public-catalog",
                str(catalog_path),
                "--public-catalog-sha256",
                canonical_sha256(_catalog()),
                "--output",
                str(output),
            ],
        )
    assert result.exit_code == 0, result.output
    assert output.read_bytes() == canonical_json_bytes(fake_witness)
    assert output.stat().st_mode & 0o777 == 0o600
    assert "not admitted" in result.output
    assert "review-task-packets" in main.commands


def test_public_catalog_rejects_digest_tamper_and_model_invented_identifier(tmp_path):
    catalog_path = tmp_path / "public-catalog.json"
    catalog_path.write_bytes(canonical_json_bytes(_catalog()))
    with pytest.raises(AtomicPacketValidationError, match="digest mismatch"):
        load_public_catalog_projection(catalog_path, expected_sha256="0" * 64)

    proposal = _proposal()
    proposal["packets"][0]["inputs"]["oracle_ids"] = ["oracle:invented"]
    with pytest.raises(AtomicPacketValidationError, match="cataloged external input"):
        validate_packet_family_proposal(
            proposal,
            feature=_feature(),
            sources=_sources(),
            public_catalog=_catalog(),
        )


def test_public_catalog_allows_unique_prospective_output_contract():
    proposal = _proposal()
    proposal["packets"][0]["output"]["api_contract"] = "api:new-unit-output:1"
    validated = validate_packet_family_proposal(
        proposal,
        feature=_feature(),
        sources=_sources(),
        public_catalog=_catalog(),
    )
    assert validated["packets"][0]["output"]["api_contract"] == (
        "api:new-unit-output:1"
    )


def test_cli_persists_no_clobber_containment_continuation(tmp_path):
    plan_path = tmp_path / "features.json"
    spec_path = tmp_path / "spec.md"
    catalog_path = tmp_path / "public-catalog.json"
    output = tmp_path / "continuation.json"
    plan_path.write_bytes(canonical_json_bytes(_plan()))
    spec_path.write_text("Canonical unit behavior\nUnknown values reject\n")
    catalog_path.write_bytes(canonical_json_bytes(_catalog()))
    with patch(
        "bob.atomic_packet_planner.compile_packet_family_proposal",
        side_effect=AtomicPacketContainmentError(
            "bounded split required", split_axis="packet_family"
        ),
    ):
        result = CliRunner().invoke(
            main,
            [
                "propose-task-packets",
                str(plan_path),
                "PPAT-M0-UNIT",
                "--spec",
                str(spec_path),
                "--public-catalog",
                str(catalog_path),
                "--public-catalog-sha256",
                canonical_sha256(_catalog()),
                "--output",
                str(output),
            ],
        )
    assert result.exit_code != 0
    marker = json.loads(output.read_text())
    assert marker["continuation_required"] is True
    assert marker["global_continuation_limit"] is None

    with pytest.raises(AtomicPacketValidationError, match="refusing to overwrite"):
        _write_canonical_output(output, {"replacement": True})


def test_canonical_proposal_loader_rejects_pretty_print_and_trailing_space(tmp_path):
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps({"x": 1}, indent=2) + "\n")
    with pytest.raises(AtomicPacketValidationError, match="not canonical"):
        load_canonical_proposal_witness(path)


def test_security_packet_envelope_requests_unlimited_lossless_continuation():
    proposal = _proposal()
    proposal["packets"] = [_packet(f"packet-{index}") for index in range(257)]
    with pytest.raises(AtomicPacketContainmentError) as captured:
        _validate(proposal)
    marker = captured.value.to_dict()
    assert marker["security_containment"] is True
    assert marker["semantic_orchestration_limit"] is False
    assert marker["continuation_required"] is True
    assert marker["global_continuation_limit"] is None
    assert marker["split_axis"] == "planner_feature"


def test_input_loader_rejects_symlink_hardlink_and_fifo(tmp_path):
    plan = tmp_path / "features.json"
    plan.write_bytes(canonical_json_bytes(_plan()))
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(plan)
    with pytest.raises(AtomicPacketValidationError, match="opened safely"):
        load_feature_plan(symlink)

    hardlink = tmp_path / "hardlink.json"
    hardlink.hardlink_to(plan)
    with pytest.raises(AtomicPacketValidationError, match="exactly one link"):
        load_feature_plan(plan)
    hardlink.unlink()

    fifo = tmp_path / "plan.fifo"
    os.mkfifo(fifo)
    with pytest.raises(AtomicPacketValidationError, match="regular file"):
        load_feature_plan(fifo)


def test_canonical_output_is_no_clobber_single_link_and_parent_fsynced(
    tmp_path, monkeypatch
):
    output = tmp_path / "witness.json"
    fsynced_directory = []
    real_fsync = os.fsync

    def recording_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            fsynced_directory.append(True)
        return real_fsync(descriptor)

    monkeypatch.setattr("bob.atomic_packet_planner.os.fsync", recording_fsync)
    _write_canonical_output(output, {"safe": True})
    assert output.read_bytes() == canonical_json_bytes({"safe": True})
    assert output.stat().st_nlink == 1
    assert output.stat().st_mode & 0o777 == 0o600
    assert len(fsynced_directory) >= 2

    original = output.read_bytes()
    with pytest.raises(AtomicPacketValidationError, match="refusing to overwrite"):
        _write_canonical_output(output, {"safe": False})
    assert output.read_bytes() == original
