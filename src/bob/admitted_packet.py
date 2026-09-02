"""Fail-closed consumption of one controller-admitted atomic packet.

The candidate projection and the controller execution profile are deliberately
separate documents.  Only the projection (plus controller-verified source-route
bytes) is safe to place in a model prompt.  Registry, admission, runtime, base,
and attempt-lineage identities remain parent-only evidence.

This module does not grant release authority.  A valid profile only narrows one
Bob development attempt to the packet selected by an external controller.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

PROJECTION_SCHEMA_VERSION = "ppat.candidate-task-projection.v1"
EXECUTION_PROFILE_SCHEMA_VERSION = "ppat.packet-execution-profile.v1"
AUTHORITY = "development_only_no_release_trust"

REQUIRED_ENV = "BOB_ADMITTED_PACKET_REQUIRED"
PROJECTION_PATH_ENV = "BOB_PACKET_PROJECTION"
PROJECTION_SHA256_ENV = "BOB_PACKET_PROJECTION_SHA256"
EXECUTION_PROFILE_PATH_ENV = "BOB_PACKET_EXECUTION_PROFILE"
EXECUTION_PROFILE_SHA256_ENV = "BOB_PACKET_EXECUTION_PROFILE_SHA256"

MAX_PROJECTION_BYTES = 4 * 1024 * 1024
MAX_EXECUTION_PROFILE_BYTES = 4 * 1024 * 1024
MAX_ROUTE_BYTES = 4 * 1024 * 1024
MAX_ROUTES = 128
MAX_TARGET_PATHS = 128
MAX_NODE_IDS = 128
MAX_COMMAND_TOKENS = 512
MAX_MATERIALIZATION_WITNESS_BYTES = 1024 * 1024

MATERIALIZATION_WITNESS_SCHEMA_VERSION = "bob.packet-target-materialization.v1"
MATERIALIZATION_WITNESS_FILENAME = "bob-target-materialization.json"

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_FAMILY_RE = re.compile(r"ppat-family-[0-9a-f]{32}\Z")
_PACKET_RE = re.compile(r"ppat-packet-[0-9a-f]{32}\Z")
_FEATURE_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_TEST_FUNCTION_RE = re.compile(r"test_acceptance_([0-9]{3})\Z")

_PROJECTION_KEYS = frozenset(
    {
        "schema_version",
        "authority",
        "family_id",
        "packet_id",
        "proposal_feature_key",
        "semantic_packet",
        "source_routes",
        "public_contract",
    }
)
_PUBLIC_CONTRACT_KEYS = frozenset(
    {
        "target_paths",
        "writer_test_namespace",
        "writer_test_path",
        "writer_node_ids",
        "acceptance_predicates",
        "non_goals",
    }
)
_EXECUTION_PROFILE_KEYS = frozenset(
    {
        "schema_version",
        "authority",
        "family_id",
        "packet_id",
        "candidate_projection_sha256",
        "admitted_family_sha256",
        "registry_entry_sha256",
        "registry_head_sha256",
        "spec_admission_sha256",
        "policy_lock_sha256",
        "catalog_lock_sha256",
        "base",
        "attempt_base",
        "runtime_identity_sha256",
        "model",
        "target_paths",
        "baseline_targets",
        "test_execution",
        "dependency_resolution",
        "generation",
        "trusted_lineage",
        "initial_evidence",
        "expected_artifacts",
        "capability_profile",
        "resource_profile",
        "locks",
    }
)


class AdmittedPacketError(ValueError):
    """The controller packet boundary is absent, malformed, or violated."""


@dataclass(frozen=True)
class SourceRoute:
    source_id: str
    start_line: int
    end_line: int
    route_path: str
    source_sha256: str
    span_sha256: str
    span_size_bytes: int
    content: str


@dataclass(frozen=True)
class AdmittedPacketContext:
    """Trusted parent view of one loaded packet assignment."""

    projection: Mapping[str, Any]
    execution_profile: Mapping[str, Any]
    projection_path: Path
    execution_profile_path: Path
    projection_sha256: str
    execution_profile_sha256: str
    workspace_path: Path
    target_materialization_path: Path
    target_materialization_sha256: str
    target_materialization: Mapping[str, Any]
    source_routes: tuple[SourceRoute, ...]
    feature_id: str
    writer_test_namespace: str
    writer_test_path: str
    writer_node_ids: tuple[str, ...]
    production_target_paths: tuple[str, ...]
    red_test_command: tuple[str, ...]
    green_test_command: tuple[str, ...]
    full_suite_command: tuple[str, ...]

    @property
    def family_id(self) -> str:
        return str(self.projection["family_id"])

    @property
    def packet_id(self) -> str:
        return str(self.projection["packet_id"])

    @property
    def proposal_feature_key(self) -> str:
        return str(self.projection["proposal_feature_key"])

    @property
    def acceptance_predicates(self) -> tuple[str, ...]:
        values = self.projection["public_contract"]["acceptance_predicates"]
        return tuple(str(value) for value in values)

    @property
    def dependency_resolution(self) -> Mapping[str, Any]:
        """Controller-authenticated relation states, never model prompt data."""

        return self.execution_profile["dependency_resolution"]

    @property
    def allowed_commit_paths(self) -> tuple[str, ...]:
        return tuple(sorted((*self.production_target_paths, self.writer_test_path)))

    @property
    def protected_evidence_bindings(self) -> dict[str, Any]:
        """Return parent-only identities that must accompany every receipt."""

        profile = self.execution_profile
        return {
            "authority": AUTHORITY,
            "family_id": self.family_id,
            "packet_id": self.packet_id,
            "feature_id": self.feature_id,
            "candidate_projection_sha256": self.projection_sha256,
            "packet_execution_profile_sha256": self.execution_profile_sha256,
            "target_materialization_sha256": self.target_materialization_sha256,
            "admitted_family_sha256": profile["admitted_family_sha256"],
            "registry_entry_sha256": profile["registry_entry_sha256"],
            "registry_head_sha256": profile["registry_head_sha256"],
            "spec_admission_sha256": profile["spec_admission_sha256"],
            "policy_lock_sha256": profile["policy_lock_sha256"],
            "catalog_lock_sha256": profile["catalog_lock_sha256"],
            "runtime_identity_sha256": profile["runtime_identity_sha256"],
            "base": profile["base"],
            "attempt_base": profile["attempt_base"],
            "trusted_lineage": profile["trusted_lineage"],
            "generation": profile["generation"],
        }

    def safe_model_assignment(self) -> dict[str, Any]:
        """Return the only packet data authorized for semantic-role prompts."""

        assert_materialized_target_custody(self)
        projection = self.projection
        return {
            "schema_version": projection["schema_version"],
            "authority": projection["authority"],
            "family_id": projection["family_id"],
            "packet_id": projection["packet_id"],
            "proposal_feature_key": projection["proposal_feature_key"],
            "semantic_packet": projection["semantic_packet"],
            "public_contract": projection["public_contract"],
            "source_routes": [
                {
                    "source_id": route.source_id,
                    "start_line": route.start_line,
                    "end_line": route.end_line,
                    "route_path": route.route_path,
                    "span_sha256": route.span_sha256,
                    "content": route.content,
                }
                for route in self.source_routes
            ],
        }


def canonical_json_bytes(value: object) -> bytes:
    """Canonical UTF-8 JSON file bytes (including one terminal LF)."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def admitted_packet_required(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    raw = env.get(REQUIRED_ENV)
    if raw is None or not raw.strip():
        return False
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on", "required"}:
        return True
    # A typo must never silently disable a campaign boundary.
    return normalized not in {"0", "false", "no", "off", "disabled"}


def _exact(value: object, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise AdmittedPacketError(
            f"{label} keys mismatch (missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)})"
        )
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise AdmittedPacketError(f"{label} must be a lowercase SHA-256")
    return value


def _nonempty(value: object, label: str, *, max_chars: int = 100_000) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\x00" in value
        or len(value) > max_chars
    ):
        raise AdmittedPacketError(f"{label} must be a bounded non-empty string")
    return value


def _relative_path(value: object, label: str) -> str:
    text = _nonempty(value, label, max_chars=4096)
    if "\\" in text:
        raise AdmittedPacketError(f"{label} must be a POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AdmittedPacketError(f"{label} must stay within the candidate workspace")
    if path.as_posix() != text:
        raise AdmittedPacketError(f"{label} is not canonical")
    return text


def _unique_string_list(
    value: object,
    label: str,
    *,
    min_items: int = 0,
    max_items: int,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not min_items <= len(value) <= max_items
        or not all(isinstance(item, str) and item and "\x00" not in item for item in value)
    ):
        raise AdmittedPacketError(f"{label} has an invalid string-list shape")
    result = tuple(value)
    if len(set(result)) != len(result):
        raise AdmittedPacketError(f"{label} contains duplicates")
    return result


def _absolute_components(path: Path, label: str) -> tuple[str, ...]:
    raw = os.fspath(path)
    if not os.path.isabs(raw) or "\x00" in raw:
        raise AdmittedPacketError(f"{label} must be an absolute literal path")
    # Do not normalize aliases away: the controller must provide one canonical
    # spelling and every component is opened without following links.
    parts = PurePosixPath(raw).parts
    if not parts or parts[0] != "/" or any(part in {"", ".", ".."} for part in parts[1:]):
        raise AdmittedPacketError(f"{label} contains a path alias")
    if str(PurePosixPath(*parts)) != raw:
        raise AdmittedPacketError(f"{label} is not a canonical absolute path")
    return tuple(parts[1:])


def _open_parent_dirfd(path: Path, label: str) -> tuple[int, str]:
    parts = _absolute_components(path, label)
    if not parts:
        raise AdmittedPacketError(f"{label} cannot name the filesystem root")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open("/", flags)
    try:
        for part in parts[:-1]:
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except OSError as exc:
                raise AdmittedPacketError(
                    f"{label} parent component cannot be opened safely: {exc}"
                ) from exc
            info = os.fstat(next_descriptor)
            if not stat.S_ISDIR(info.st_mode):
                os.close(next_descriptor)
                raise AdmittedPacketError(f"{label} parent component is not a directory")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, parts[-1]
    except Exception:
        os.close(descriptor)
        raise


def _read_controller_file(
    path: Path,
    *,
    expected_sha256: str,
    max_bytes: int,
    label: str,
    required_mode: int | None = None,
    required_uid: int | None = None,
) -> tuple[dict[str, Any], bytes]:
    expected = _sha(expected_sha256, f"{label} expected digest")
    parent_fd, leaf = _open_parent_dirfd(path, label)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(leaf, flags, dir_fd=parent_fd)
    except OSError as exc:
        os.close(parent_fd)
        raise AdmittedPacketError(f"{label} cannot be opened safely: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise AdmittedPacketError(f"{label} must be a regular single-link file")
        if required_mode is not None and stat.S_IMODE(before.st_mode) != required_mode:
            raise AdmittedPacketError(f"{label} has an unexpected mode")
        if required_uid is not None and before.st_uid != required_uid:
            raise AdmittedPacketError(f"{label} has an unexpected owner")
        if before.st_mode & 0o022:
            raise AdmittedPacketError(f"{label} must not be group/world writable")
        if before.st_size > max_bytes:
            raise AdmittedPacketError(f"{label} exceeds its security byte envelope")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise AdmittedPacketError(f"{label} exceeds its security byte envelope")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_mode,
            before.st_nlink,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_mode,
            after.st_nlink,
        ):
            raise AdmittedPacketError(f"{label} changed while being read")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
        os.close(parent_fd)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise AdmittedPacketError(f"{label} digest does not match controller expectation")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdmittedPacketError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise AdmittedPacketError(f"{label} is not canonical JSON with exactly one LF")
    return value, raw


def _path_is_outside_workspace(path: Path, workspace: Path, label: str) -> None:
    # Both paths are validated through nofollow opens elsewhere.  commonpath is
    # lexical here by design: an alias spelling must not smuggle a profile into
    # the candidate tree.
    try:
        common = os.path.commonpath((os.fspath(path), os.fspath(workspace)))
    except ValueError as exc:
        raise AdmittedPacketError(f"{label} and workspace are incomparable") from exc
    if common == os.fspath(workspace):
        raise AdmittedPacketError(f"{label} must be controller-owned outside the candidate workspace")


def _validate_semantic_packet(value: object) -> Mapping[str, Any]:
    required = frozenset(
        {
            "slug",
            "parent_design_feature",
            "source_spans",
            "authority_boundary",
            "observable_behavior",
            "primary_artifact",
            "inputs",
            "output",
            "error_map",
            "dependencies",
            "external_prerequisite_ids",
            "acceptance_profile_id",
            "acceptance_predicates",
            "non_goals",
        }
    )
    packet = _exact(value, required, "semantic_packet")
    _nonempty(packet["slug"], "semantic_packet.slug", max_chars=128)
    _nonempty(packet["parent_design_feature"], "semantic_packet.parent_design_feature", max_chars=256)
    _nonempty(packet["authority_boundary"], "semantic_packet.authority_boundary")
    _nonempty(packet["observable_behavior"], "semantic_packet.observable_behavior")
    spans = packet["source_spans"]
    if not isinstance(spans, list) or not spans:
        raise AdmittedPacketError("semantic_packet.source_spans must be non-empty")
    for index, raw_span in enumerate(spans):
        span = _exact(
            raw_span,
            frozenset({"source_id", "start_line", "end_line"}),
            f"semantic_packet.source_spans[{index}]",
        )
        _nonempty(span["source_id"], "source span source_id", max_chars=256)
        if (
            isinstance(span["start_line"], bool)
            or not isinstance(span["start_line"], int)
            or span["start_line"] < 1
            or isinstance(span["end_line"], bool)
            or not isinstance(span["end_line"], int)
            or span["end_line"] < span["start_line"]
        ):
            raise AdmittedPacketError("semantic packet source span is invalid")
    artifact = _exact(
        packet["primary_artifact"],
        frozenset({"kind", "target_paths"}),
        "semantic_packet.primary_artifact",
    )
    _nonempty(artifact["kind"], "primary artifact kind", max_chars=128)
    _unique_string_list(
        artifact["target_paths"],
        "primary artifact target_paths",
        min_items=1,
        max_items=MAX_TARGET_PATHS,
    )
    inputs = _exact(
        packet["inputs"],
        frozenset({"schema_ids", "fixture_ids", "package_lock_ids", "oracle_ids"}),
        "semantic_packet.inputs",
    )
    for name in ("schema_ids", "fixture_ids", "package_lock_ids", "oracle_ids"):
        _unique_string_list(inputs[name], f"semantic_packet.inputs.{name}", max_items=128)
    output = _exact(
        packet["output"],
        frozenset({"kind", "schema_id", "path", "api_contract", "persistence"}),
        "semantic_packet.output",
    )
    if output["kind"] not in {"serialized", "in_process"}:
        raise AdmittedPacketError("semantic packet output kind is invalid")
    for name in ("schema_id", "path", "api_contract", "persistence"):
        if output[name] is not None:
            _nonempty(output[name], f"semantic packet output {name}")
    if output["kind"] == "serialized" and (
        output["schema_id"] is None
        or output["path"] is None
        or output["api_contract"] is not None
    ):
        raise AdmittedPacketError("serialized output union fields are inconsistent")
    if output["kind"] == "in_process" and (
        output["schema_id"] is not None
        or output["path"] is not None
        or output["api_contract"] is None
    ):
        raise AdmittedPacketError("in-process output union fields are inconsistent")
    errors = packet["error_map"]
    if not isinstance(errors, list) or not errors:
        raise AdmittedPacketError("semantic packet error_map must be non-empty")
    for index, raw_error in enumerate(errors):
        error = _exact(
            raw_error,
            frozenset({"condition", "outcome"}),
            f"semantic_packet.error_map[{index}]",
        )
        _nonempty(error["condition"], "error condition")
        _nonempty(error["outcome"], "error outcome")
    dependencies = _exact(
        packet["dependencies"],
        frozenset(
            {
                "build_requires",
                "consumes_or_binds",
                "verification_requires",
                "activation_requires",
            }
        ),
        "semantic_packet.dependencies",
    )
    for name in dependencies:
        _unique_string_list(dependencies[name], f"semantic dependencies {name}", max_items=128)
    _unique_string_list(
        packet["external_prerequisite_ids"],
        "semantic_packet.external_prerequisite_ids",
        max_items=128,
    )
    _nonempty(packet["acceptance_profile_id"], "acceptance_profile_id", max_chars=256)
    predicates = _unique_string_list(
        packet["acceptance_predicates"],
        "semantic_packet.acceptance_predicates",
        min_items=2,
        max_items=5,
    )
    if any(not item.strip() for item in predicates):
        raise AdmittedPacketError("semantic packet contains an empty acceptance predicate")
    _unique_string_list(packet["non_goals"], "semantic_packet.non_goals", max_items=64)
    return packet


def _validate_projection(value: object) -> Mapping[str, Any]:
    projection = _exact(value, _PROJECTION_KEYS, "candidate projection")
    if projection["schema_version"] != PROJECTION_SCHEMA_VERSION:
        raise AdmittedPacketError("candidate projection schema version is unsupported")
    if projection["authority"] != AUTHORITY:
        raise AdmittedPacketError("candidate projection has forbidden authority")
    if not isinstance(projection["family_id"], str) or _FAMILY_RE.fullmatch(projection["family_id"]) is None:
        raise AdmittedPacketError("candidate projection family_id is malformed")
    if not isinstance(projection["packet_id"], str) or _PACKET_RE.fullmatch(projection["packet_id"]) is None:
        raise AdmittedPacketError("candidate projection packet_id is malformed")
    if not isinstance(projection["proposal_feature_key"], str) or _FEATURE_KEY_RE.fullmatch(projection["proposal_feature_key"]) is None:
        raise AdmittedPacketError("candidate projection feature key is malformed")
    packet = _validate_semantic_packet(projection["semantic_packet"])
    public = _exact(projection["public_contract"], _PUBLIC_CONTRACT_KEYS, "public_contract")
    targets = tuple(
        _relative_path(item, "public_contract.target_paths entry")
        for item in _unique_string_list(public["target_paths"], "public_contract.target_paths", min_items=1, max_items=MAX_TARGET_PATHS)
    )
    namespace = _relative_path(public["writer_test_namespace"], "public_contract.writer_test_namespace")
    test_path = _relative_path(public["writer_test_path"], "public_contract.writer_test_path")
    if PurePosixPath(test_path).parent.as_posix() != namespace:
        raise AdmittedPacketError("writer test path is outside its exact namespace")
    if not PurePosixPath(test_path).name.startswith("test_") or not test_path.endswith(".py"):
        raise AdmittedPacketError("writer test path is not one exact Python test file")
    predicates = _unique_string_list(public["acceptance_predicates"], "public_contract.acceptance_predicates", min_items=2, max_items=5)
    non_goals = _unique_string_list(public["non_goals"], "public_contract.non_goals", max_items=64)
    if predicates != tuple(packet["acceptance_predicates"]) or non_goals != tuple(packet["non_goals"]):
        raise AdmittedPacketError("public contract does not exactly project packet predicates/non-goals")
    public_nodes = _unique_string_list(
        public["writer_node_ids"],
        "public_contract.writer_node_ids",
        min_items=2,
        max_items=MAX_NODE_IDS,
    )
    expected_nodes = tuple(
        f"{test_path}::test_acceptance_{index:03d}"
        for index in range(1, len(predicates) + 1)
    )
    if public_nodes != expected_nodes:
        raise AdmittedPacketError(
            "public writer nodes are not the deterministic acceptance mapping"
        )
    artifact = packet["primary_artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {"kind", "target_paths"} or tuple(artifact["target_paths"]) != targets:
        raise AdmittedPacketError("public target paths do not exactly project primary_artifact")
    routes = projection["source_routes"]
    if not isinstance(routes, list) or not 1 <= len(routes) <= MAX_ROUTES:
        raise AdmittedPacketError("candidate projection source_routes are empty or oversized")
    return projection


def _command(value: object, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_COMMAND_TOKENS
        or not all(
            isinstance(token, str) and token and "\x00" not in token
            for token in value
        )
    ):
        raise AdmittedPacketError(f"{label} must be a bounded safe argv")
    return tuple(value)


def _validate_baseline_targets(
    value: object, target_paths: Sequence[str], label: str
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or len(value) != len(target_paths):
        raise AdmittedPacketError(f"{label} does not cover the exact target paths")
    result: list[Mapping[str, Any]] = []
    for index, (raw, expected_path) in enumerate(zip(value, target_paths, strict=True)):
        if not isinstance(raw, dict) or raw.get("path") != expected_path:
            raise AdmittedPacketError(f"{label}[{index}] path/order mismatch")
        state = raw.get("state")
        if state == "absent":
            entry = _exact(raw, frozenset({"path", "state"}), f"{label}[{index}]")
        elif state == "present":
            entry = _exact(
                raw,
                frozenset({"path", "state", "mode", "size_bytes", "sha256"}),
                f"{label}[{index}]",
            )
            if (
                isinstance(entry["mode"], bool)
                or not isinstance(entry["mode"], int)
                or not 0 <= entry["mode"] <= 0o7777
                or isinstance(entry["size_bytes"], bool)
                or not isinstance(entry["size_bytes"], int)
                or entry["size_bytes"] < 0
            ):
                raise AdmittedPacketError(f"{label}[{index}] metadata is invalid")
            _sha(entry["sha256"], f"{label}[{index}] digest")
        else:
            raise AdmittedPacketError(f"{label}[{index}] state is invalid")
        result.append(entry)
    return tuple(result)


def _validate_dependency_resolution(value: object) -> None:
    dependencies = _exact(
        value,
        frozenset(
            {
                "build_requires",
                "consumes_or_binds",
                "verification_requires",
                "activation_requires",
            }
        ),
        "dependency_resolution",
    )
    for relation, rows in dependencies.items():
        if not isinstance(rows, list) or len(rows) > 128:
            raise AdmittedPacketError(f"dependency_resolution.{relation} is invalid")
        for index, raw in enumerate(rows):
            if not isinstance(raw, dict):
                raise AdmittedPacketError("dependency resolution row is not an object")
            if raw.get("kind") == "intra_family_packet":
                row = _exact(
                    raw,
                    frozenset({"kind", "packet_id", "slug"}),
                    f"dependency_resolution.{relation}[{index}]",
                )
                if not isinstance(row["packet_id"], str) or _PACKET_RE.fullmatch(row["packet_id"]) is None:
                    raise AdmittedPacketError("dependency packet_id is malformed")
                _nonempty(row["slug"], "dependency slug", max_chars=128)
            elif raw.get("kind") == "external":
                row = _exact(
                    raw,
                    frozenset(
                        {
                            "kind",
                            "prerequisite_kind",
                            "subject_id",
                            "evidence_sha256",
                            "state",
                        }
                    ),
                    f"dependency_resolution.{relation}[{index}]",
                )
                _nonempty(
                    row["prerequisite_kind"],
                    "external dependency prerequisite kind",
                    max_chars=128,
                )
                _nonempty(row["subject_id"], "external dependency subject", max_chars=256)
                _sha(row["evidence_sha256"], "external dependency evidence")
                state = row["state"]
                if state not in {"satisfied", "pending", "unavailable"}:
                    raise AdmittedPacketError("external dependency state is invalid")
                if relation in {"build_requires", "consumes_or_binds"} and state != "satisfied":
                    raise AdmittedPacketError(
                        f"external {relation} dependency is not satisfied for dispatch"
                    )
            else:
                raise AdmittedPacketError("dependency resolution kind is invalid")


def _validate_profile(value: object, projection: Mapping[str, Any], projection_sha256: str) -> Mapping[str, Any]:
    profile = _exact(value, _EXECUTION_PROFILE_KEYS, "packet execution profile")
    if profile["schema_version"] != EXECUTION_PROFILE_SCHEMA_VERSION or profile["authority"] != AUTHORITY:
        raise AdmittedPacketError("packet execution profile schema/authority mismatch")
    if profile["family_id"] != projection["family_id"] or profile["packet_id"] != projection["packet_id"]:
        raise AdmittedPacketError("projection/profile family or packet sibling confusion")
    if profile["candidate_projection_sha256"] != projection_sha256:
        raise AdmittedPacketError("packet execution profile binds a stale projection")
    for key in (
        "admitted_family_sha256",
        "registry_entry_sha256",
        "registry_head_sha256",
        "spec_admission_sha256",
        "policy_lock_sha256",
        "catalog_lock_sha256",
        "runtime_identity_sha256",
    ):
        _sha(profile[key], key)
    base = profile["base"]
    if not isinstance(base, dict) or set(base) != {"commit", "tree"} or not all(
        isinstance(base[key], str) and re.fullmatch(r"[0-9a-f]{40,64}", base[key])
        for key in ("commit", "tree")
    ):
        raise AdmittedPacketError("packet execution base identity is malformed")
    attempt_base = profile["attempt_base"]
    if not isinstance(attempt_base, dict) or set(attempt_base) != {"commit", "tree"} or not all(
        isinstance(attempt_base[key], str)
        and re.fullmatch(r"[0-9a-f]{40,64}", attempt_base[key])
        for key in ("commit", "tree")
    ):
        raise AdmittedPacketError("packet attempt base identity is malformed")
    model = _exact(profile["model"], frozenset({"id"}), "execution model")
    if model["id"] != "claude-opus-4-8":
        raise AdmittedPacketError("packet execution model must be exactly claude-opus-4-8")
    target_paths = tuple(
        _relative_path(item, "execution target path")
        for item in _unique_string_list(profile["target_paths"], "execution target_paths", min_items=1, max_items=MAX_TARGET_PATHS)
    )
    if target_paths != tuple(projection["public_contract"]["target_paths"]):
        raise AdmittedPacketError("execution target paths differ from the candidate projection")
    baselines = _validate_baseline_targets(
        profile["baseline_targets"], target_paths, "baseline_targets"
    )
    _validate_dependency_resolution(profile["dependency_resolution"])
    generation = _exact(
        profile["generation"],
        frozenset(
            {
                "attempt_id",
                "attempt_number",
                "execution_class",
                "feature_id",
                "parent_design_feature",
            }
        ),
        "generation",
    )
    attempt_id = _nonempty(generation["attempt_id"], "generation.attempt_id", max_chars=256)
    attempt_number = generation["attempt_number"]
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int) or attempt_number < 0:
        raise AdmittedPacketError("generation.attempt_number is invalid")
    if generation["execution_class"] != "local":
        raise AdmittedPacketError("generation.execution_class must be local")
    feature_id = _nonempty(generation["feature_id"], "generation.feature_id", max_chars=256)
    expected_feature_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"urn:ppat:{projection['packet_id']}")
    )
    if feature_id != expected_feature_id:
        raise AdmittedPacketError("generation feature_id has sibling/parent confusion")
    if generation["parent_design_feature"] != projection["proposal_feature_key"]:
        raise AdmittedPacketError("generation parent feature differs from proposal feature")
    feature_slug = re.sub(r"[^A-Za-z0-9]+", "-", feature_id).strip("-").lower()
    feature_slug = (feature_slug or "feature")[:32]
    namespace_digest = hashlib.sha256(
        f"{feature_id}\0{0}".encode()
    ).hexdigest()[:16]
    expected_namespace = (
        f"app/tests/bob_generated/{feature_slug}-a0-{namespace_digest}"
    )
    packet_slug = str(projection["semantic_packet"]["slug"])
    expected_test_path = (
        f"{expected_namespace}/test_{packet_slug.replace('-', '_')}.py"
    )
    if (
        projection["public_contract"]["writer_test_namespace"]
        != expected_namespace
        or projection["public_contract"]["writer_test_path"]
        != expected_test_path
    ):
        raise AdmittedPacketError(
            "writer namespace/path is not the deterministic packet mapping"
        )

    lineage_keys = frozenset(
        {
            "admitted_family_sha256",
            "attempt_lineage_sha256",
            "attempt_base_commit",
            "attempt_base_tree",
            "base_commit",
            "base_tree",
            "campaign_identity_sha256",
            "catalog_lock_sha256",
            "family_id",
            "packet_id",
            "plan_canonical_sha256",
            "proposal_feature_key",
            "previous_attempt_receipt_sha256",
            "registry_entry_sha256",
            "registry_head_sha256",
            "registry_sequence",
            "source_bundle_sha256",
            "spec_admission_sha256",
        }
    )
    lineage = _exact(profile["trusted_lineage"], lineage_keys, "trusted_lineage")
    for key in (
        "admitted_family_sha256",
        "attempt_lineage_sha256",
        "campaign_identity_sha256",
        "catalog_lock_sha256",
        "plan_canonical_sha256",
        "registry_entry_sha256",
        "registry_head_sha256",
        "source_bundle_sha256",
        "spec_admission_sha256",
    ):
        _sha(lineage[key], f"trusted_lineage.{key}")
    previous = lineage["previous_attempt_receipt_sha256"]
    if previous is not None:
        _sha(previous, "trusted_lineage.previous_attempt_receipt_sha256")
    if (
        lineage["admitted_family_sha256"] != profile["admitted_family_sha256"]
        or lineage["registry_entry_sha256"] != profile["registry_entry_sha256"]
        or lineage["registry_head_sha256"] != profile["registry_head_sha256"]
        or lineage["spec_admission_sha256"] != profile["spec_admission_sha256"]
        or lineage["catalog_lock_sha256"] != profile["catalog_lock_sha256"]
        or lineage["base_commit"] != base["commit"]
        or lineage["base_tree"] != base["tree"]
        or lineage["attempt_base_commit"] != attempt_base["commit"]
        or lineage["attempt_base_tree"] != attempt_base["tree"]
        or lineage["family_id"] != profile["family_id"]
        or lineage["packet_id"] != profile["packet_id"]
        or lineage["proposal_feature_key"] != projection["proposal_feature_key"]
    ):
        raise AdmittedPacketError("trusted lineage does not bind the profile/projection")
    if isinstance(lineage["registry_sequence"], bool) or not isinstance(lineage["registry_sequence"], int) or lineage["registry_sequence"] < 1:
        raise AdmittedPacketError("trusted lineage registry_sequence is invalid")
    attempt_payload = {
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "family_id": profile["family_id"],
        "feature_id": feature_id,
        "packet_id": profile["packet_id"],
        "previous_attempt_receipt_sha256": previous,
        "registry_entry_sha256": profile["registry_entry_sha256"],
        "attempt_base_commit": attempt_base["commit"],
        "attempt_base_tree": attempt_base["tree"],
    }
    attempt_digest = hashlib.sha256(
        json.dumps(
            attempt_payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if lineage["attempt_lineage_sha256"] != attempt_digest:
        raise AdmittedPacketError("attempt lineage digest is stale or forged")

    initial = _exact(
        profile["initial_evidence"],
        frozenset({"baseline_targets", "source_routes"}),
        "initial_evidence",
    )
    initial_baselines = _validate_baseline_targets(
        initial["baseline_targets"], target_paths, "initial_evidence.baseline_targets"
    )
    if initial_baselines != baselines:
        raise AdmittedPacketError("initial evidence baseline differs from profile baseline")
    routes = initial["source_routes"]
    projected_routes = projection["source_routes"]
    if not isinstance(routes, list) or len(routes) != len(projected_routes):
        raise AdmittedPacketError("initial evidence source routes are incomplete")
    for index, (raw, projected) in enumerate(zip(routes, projected_routes, strict=True)):
        row = _exact(
            raw,
            frozenset({"route_path", "span_sha256", "span_size_bytes"}),
            f"initial_evidence.source_routes[{index}]",
        )
        if any(row[key] != projected[key] for key in row):
            raise AdmittedPacketError("initial evidence source route identity mismatch")

    expected = _exact(
        profile["expected_artifacts"],
        frozenset({"output", "production_paths", "writer_node_ids", "writer_test_path"}),
        "expected_artifacts",
    )
    if (
        expected["output"] != projection["semantic_packet"]["output"]
        or expected["production_paths"] != list(target_paths)
        or expected["writer_node_ids"] != projection["public_contract"]["writer_node_ids"]
        or expected["writer_test_path"] != projection["public_contract"]["writer_test_path"]
    ):
        raise AdmittedPacketError("expected artifacts differ from the packet projection")

    capability = _exact(
        profile["capability_profile"],
        frozenset({"network", "candidate", "tests", "git", "controller_state", "provider"}),
        "capability_profile",
    )
    expected_capability = {
        "network": "provider-broker-only-for-semantic-roles",
        "candidate": "packet-targets-rw-otherwise-ro",
        "tests": "writer-namespace-rw-otherwise-ro",
        "git": "absent",
        "controller_state": "absent",
        "provider": "controller-brokered-pinned-opus",
    }
    if dict(capability) != expected_capability:
        raise AdmittedPacketError("packet capability profile is widened or unknown")
    resources = _exact(
        profile["resource_profile"],
        frozenset(
            {
                "memory_bytes",
                "pids",
                "output_bytes",
                "test_timeout_seconds",
                "semantic_turn_cap",
                "semantic_cost_cap",
            }
        ),
        "resource_profile",
    )
    for key in ("memory_bytes", "pids", "output_bytes", "test_timeout_seconds"):
        if isinstance(resources[key], bool) or not isinstance(resources[key], int) or resources[key] <= 0:
            raise AdmittedPacketError(f"resource_profile.{key} is invalid")
    if resources["semantic_turn_cap"] is not None or resources["semantic_cost_cap"] is not None:
        raise AdmittedPacketError("packet profile introduced a semantic orchestration cap")

    locks = _unique_string_list(profile["locks"], "packet locks", min_items=1, max_items=MAX_TARGET_PATHS + 3)
    expected_locks = tuple(
        sorted(
            {
                f"family:{profile['family_id']}",
                f"packet:{profile['packet_id']}",
                f"writer:{projection['public_contract']['writer_test_path']}",
                *(f"target:{path}" for path in target_paths),
            }
        )
    )
    if locks != expected_locks:
        raise AdmittedPacketError("packet locks do not exactly cover packet targets")
    return profile


def _test_execution_fields(profile: Mapping[str, Any], projection: Mapping[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    execution = _exact(
        profile["test_execution"],
        frozenset(
            {"writer_node_ids", "red_exact_nodes", "green_exact_nodes", "full_suite"}
        ),
        "test_execution",
    )
    nodes = _unique_string_list(execution["writer_node_ids"], "test_execution node IDs", min_items=2, max_items=MAX_NODE_IDS)
    test_path = str(projection["public_contract"]["writer_test_path"])
    predicates = tuple(projection["public_contract"]["acceptance_predicates"])
    expected_nodes = tuple(
        f"{test_path}::test_acceptance_{index:03d}"
        for index in range(1, len(predicates) + 1)
    )
    if nodes != expected_nodes:
        raise AdmittedPacketError("writer nodes are not the deterministic acceptance mapping")
    red = _command(execution["red_exact_nodes"], "red_exact_nodes")
    green = _command(execution["green_exact_nodes"], "green_exact_nodes")
    full = _command(execution["full_suite"], "full_suite")
    if red[-len(nodes) :] != nodes or green[-len(nodes) :] != nodes:
        raise AdmittedPacketError("red/green commands do not end in the exact packet nodes")
    if red != green:
        raise AdmittedPacketError("red and green node commands must be identical")
    expected_prefix = (
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
    )
    if red[: -len(nodes)] != expected_prefix:
        raise AdmittedPacketError(
            "packet red/green command prefix differs from Bob's exact verifier"
        )
    expected_full_tail = (
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
    )
    if (
        not Path(full[0]).is_absolute()
        or full[1:] != expected_full_tail
        or not re.fullmatch(r"python(?:[0-9]+(?:\.[0-9]+)*)?", Path(full[0]).name)
    ):
        raise AdmittedPacketError("packet full-suite command is not the exact verifier argv")
    return test_path, nodes, red, green, full


def _route_base(projection_path: Path, profile_path: Path) -> Path:
    """Return the canonical common publication root for routed source bytes."""

    projection_parts = _absolute_components(projection_path, "candidate projection path")
    profile_parts = _absolute_components(profile_path, "execution profile path")
    shared: list[str] = []
    for left, right in zip(projection_parts[:-1], profile_parts[:-1], strict=False):
        if left != right:
            break
        shared.append(left)
    if not shared:
        raise AdmittedPacketError("projection/profile have no common controller publication root")
    return Path("/", *shared)


def _load_routes(projection: Mapping[str, Any], *, projection_path: Path, profile_path: Path) -> tuple[SourceRoute, ...]:
    base = _route_base(projection_path, profile_path)
    result: list[SourceRoute] = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(projection["source_routes"]):
        keys = {"source_id", "start_line", "end_line", "route_path", "source_sha256", "span_sha256", "span_size_bytes"}
        route = _exact(raw, frozenset(keys), f"source_routes[{index}]")
        source_id = _nonempty(route["source_id"], "source route source_id", max_chars=256)
        if isinstance(route["start_line"], bool) or not isinstance(route["start_line"], int) or route["start_line"] < 1:
            raise AdmittedPacketError("source route start_line is invalid")
        if isinstance(route["end_line"], bool) or not isinstance(route["end_line"], int) or route["end_line"] < route["start_line"]:
            raise AdmittedPacketError("source route end_line is invalid")
        relative = _relative_path(route["route_path"], "source route path")
        if relative in seen_paths:
            raise AdmittedPacketError("source route path is duplicated")
        seen_paths.add(relative)
        source_sha = _sha(route["source_sha256"], "source route source digest")
        span_sha = _sha(route["span_sha256"], "source route span digest")
        size = route["span_size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_ROUTE_BYTES:
            raise AdmittedPacketError("source route size is invalid")
        # route_path is relative to the controller publication root shared by
        # the two admission documents.  It is opened through the same nofollow
        # dirfd chain as the documents themselves.
        route_path = base / relative
        value, _raw_file = _read_route_file(
            route_path, span_sha, size, f"source route {relative}"
        )
        result.append(
            SourceRoute(
                source_id=source_id,
                start_line=route["start_line"],
                end_line=route["end_line"],
                route_path=relative,
                source_sha256=source_sha,
                span_sha256=span_sha,
                span_size_bytes=size,
                content=value,
            )
        )
    return tuple(result)


def _read_route_file(path: Path, expected_sha256: str, expected_size: int, label: str) -> tuple[str, bytes]:
    parent_fd, leaf = _open_parent_dirfd(path, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(leaf, flags, dir_fd=parent_fd)
    except OSError as exc:
        os.close(parent_fd)
        raise AdmittedPacketError(f"{label} cannot be opened safely: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != expected_size:
            raise AdmittedPacketError(f"{label} is not the expected regular single-link file")
        raw = b""
        while len(raw) <= MAX_ROUTE_BYTES:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_ROUTE_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_nlink) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink):
            raise AdmittedPacketError(f"{label} changed while being read")
    finally:
        os.close(descriptor)
        os.close(parent_fd)
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise AdmittedPacketError(f"{label} size/digest mismatch")
    try:
        return raw.decode("utf-8", errors="strict"), raw
    except UnicodeError as exc:
        raise AdmittedPacketError(f"{label} is not UTF-8") from exc


def _open_workspace_dirfd(workspace: Path) -> int:
    parent_fd, leaf = _open_parent_dirfd(workspace, "candidate workspace")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(leaf, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise AdmittedPacketError(
            f"candidate workspace cannot be opened without following links: {exc}"
        ) from exc
    finally:
        os.close(parent_fd)
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise AdmittedPacketError("candidate workspace is not a directory")
    return descriptor


def _candidate_target_entry(workspace_fd: int, relative: str) -> dict[str, Any]:
    parts = PurePosixPath(relative).parts
    current = os.dup(workspace_fd)
    owned: list[int] = [current]
    dir_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        for component in parts[:-1]:
            try:
                child = os.open(component, dir_flags, dir_fd=current)
            except OSError as exc:
                raise AdmittedPacketError(
                    f"candidate target parent is missing/aliased: {relative}"
                ) from exc
            owned.append(child)
            current = child
        try:
            target = os.open(
                parts[-1],
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=current,
            )
        except FileNotFoundError:
            return {"path": relative, "state": "absent"}
        except OSError as exc:
            raise AdmittedPacketError(
                f"candidate target cannot be opened safely: {relative}"
            ) from exc
        try:
            before = os.fstat(target)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise AdmittedPacketError(
                    f"candidate target is not a regular single-link file: {relative}"
                )
            digest = hashlib.sha256()
            while chunk := os.read(target, 1024 * 1024):
                digest.update(chunk)
            after = os.fstat(target)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
                before.st_nlink,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
                after.st_nlink,
            ):
                raise AdmittedPacketError(
                    f"candidate target changed while being witnessed: {relative}"
                )
            return {
                "path": relative,
                "state": "present",
                "mode": stat.S_IMODE(before.st_mode),
                "size_bytes": before.st_size,
                "sha256": digest.hexdigest(),
            }
        finally:
            os.close(target)
    finally:
        for descriptor in reversed(owned):
            os.close(descriptor)


def _open_candidate_target_parent(workspace_fd: int, relative: str) -> tuple[int, str]:
    """Open an exact target parent beneath *workspace_fd* without aliases."""

    parts = PurePosixPath(relative).parts
    current = os.dup(workspace_fd)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        for component in parts[:-1]:
            try:
                child = os.open(component, flags, dir_fd=current)
            except OSError as exc:
                raise AdmittedPacketError(
                    f"candidate target parent is missing/aliased: {relative}"
                ) from exc
            info = os.fstat(child)
            if not stat.S_ISDIR(info.st_mode):
                os.close(child)
                raise AdmittedPacketError(
                    f"candidate target parent is not a directory: {relative}"
                )
            os.close(current)
            current = child
        return current, parts[-1]
    except Exception:
        os.close(current)
        raise


def _candidate_target_witness_entry(
    workspace_fd: int, relative: str
) -> dict[str, Any]:
    """Witness one present target through a stable no-follow descriptor."""

    parent_fd, leaf = _open_candidate_target_parent(workspace_fd, relative)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        try:
            descriptor = os.open(leaf, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise AdmittedPacketError(
                f"materialized candidate target cannot be opened safely: {relative}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise AdmittedPacketError(
                    f"materialized candidate target is not a regular single-link file: {relative}"
                )
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
            after = os.fstat(descriptor)
            stable_fields = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
                "st_nlink",
            )
            if any(getattr(before, key) != getattr(after, key) for key in stable_fields):
                raise AdmittedPacketError(
                    f"materialized candidate target changed while witnessed: {relative}"
                )
            return {
                "path": relative,
                "dev": before.st_dev,
                "ino": before.st_ino,
                "mode": stat.S_IMODE(before.st_mode),
                "size_bytes": before.st_size,
                "sha256": digest.hexdigest(),
                "link_count": before.st_nlink,
                "owner_uid": before.st_uid,
            }
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)


def _materialize_absent_target(workspace_fd: int, relative: str) -> dict[str, Any]:
    """Create one admitted-absent target under trusted-parent custody."""

    parent_fd, leaf = _open_candidate_target_parent(workspace_fd, relative)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(leaf, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise AdmittedPacketError(
                f"admitted-absent target already exists or cannot be created safely: {relative}"
            ) from exc
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size != 0
        ):
            raise AdmittedPacketError(
                f"new candidate target failed trusted materialization checks: {relative}"
            )
        os.fsync(descriptor)
        os.fsync(parent_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)
    # A fresh no-follow walk detects a renamed/swapped parent or leaf between
    # creation and publication of the controller-consumable witness.
    return _candidate_target_witness_entry(workspace_fd, relative)


def _validate_writer_path_custody(workspace_fd: int, test_path: str) -> None:
    """Reject aliases/hardlinks in the existing prefix of the writer path."""

    parts = PurePosixPath(test_path).parts
    current = os.dup(workspace_fd)
    owned: list[int] = [current]
    dir_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        for component in parts[:-1]:
            try:
                child = os.open(component, dir_flags, dir_fd=current)
            except FileNotFoundError:
                return
            except OSError as exc:
                raise AdmittedPacketError(
                    "writer test path contains a symlink/non-directory alias"
                ) from exc
            owned.append(child)
            current = child
        try:
            test_fd = os.open(
                parts[-1],
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
        except FileNotFoundError:
            return
        except OSError as exc:
            raise AdmittedPacketError("writer test path is an unsafe alias") from exc
        try:
            info = os.fstat(test_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise AdmittedPacketError(
                    "existing writer test path is not a regular single-link file"
                )
        finally:
            os.close(test_fd)
    finally:
        for descriptor in reversed(owned):
            os.close(descriptor)


def _validate_candidate_custody(
    workspace: Path,
    projection: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> None:
    targets = tuple(str(value) for value in profile["target_paths"])
    test_path = str(projection["public_contract"]["writer_test_path"])
    target_objects = tuple(PurePosixPath(path) for path in targets)
    if any(PurePosixPath("app/src") not in path.parents for path in target_objects):
        raise AdmittedPacketError("production target is outside locked app/src")
    if PurePosixPath("app/tests") not in PurePosixPath(test_path).parents:
        raise AdmittedPacketError("writer test path is outside locked app/tests")
    all_objects = (*target_objects, PurePosixPath(test_path))
    for index, left in enumerate(all_objects):
        for right in all_objects[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                raise AdmittedPacketError(
                    "packet allowlist paths overlap or alias one another"
                )
    workspace_fd = _open_workspace_dirfd(workspace)
    try:
        actual = tuple(
            _candidate_target_entry(workspace_fd, path) for path in targets
        )
        expected = tuple(profile["baseline_targets"])
        if actual != expected:
            raise AdmittedPacketError(
                "candidate production baseline is stale or does not match profile"
            )
        _validate_writer_path_custody(workspace_fd, test_path)
    finally:
        os.close(workspace_fd)


def load_admitted_packet_context(
    *,
    workspace: str | Path,
    environ: Mapping[str, str] | None = None,
) -> AdmittedPacketContext | None:
    """Load and cross-bind the controller's two packet documents.

    Legacy behavior is preserved only when the campaign does not require a
    packet and none of the four packet-document variables is present.  Any
    partial packet configuration fails closed.
    """

    env = os.environ if environ is None else environ
    required = admitted_packet_required(env)
    names = (
        PROJECTION_PATH_ENV,
        PROJECTION_SHA256_ENV,
        EXECUTION_PROFILE_PATH_ENV,
        EXECUTION_PROFILE_SHA256_ENV,
    )
    present = {name: bool(env.get(name, "").strip()) for name in names}
    if not required and not any(present.values()):
        return None
    if not all(present.values()):
        missing = sorted(name for name, active in present.items() if not active)
        raise AdmittedPacketError(
            "admitted packet configuration is incomplete; missing " + ", ".join(missing)
        )
    workspace_path = Path(os.path.abspath(os.fspath(workspace)))
    _absolute_components(workspace_path, "candidate workspace")
    projection_path = Path(env[PROJECTION_PATH_ENV])
    profile_path = Path(env[EXECUTION_PROFILE_PATH_ENV])
    _path_is_outside_workspace(projection_path, workspace_path, "candidate projection")
    _path_is_outside_workspace(profile_path, workspace_path, "execution profile")
    projection_value, projection_raw = _read_controller_file(
        projection_path,
        expected_sha256=env[PROJECTION_SHA256_ENV],
        max_bytes=MAX_PROJECTION_BYTES,
        label="candidate projection",
    )
    projection = _validate_projection(projection_value)
    projection_sha = hashlib.sha256(projection_raw).hexdigest()
    profile_value, profile_raw = _read_controller_file(
        profile_path,
        expected_sha256=env[EXECUTION_PROFILE_SHA256_ENV],
        max_bytes=MAX_EXECUTION_PROFILE_BYTES,
        label="packet execution profile",
    )
    profile = _validate_profile(profile_value, projection, projection_sha)
    test_path, nodes, red, green, full = _test_execution_fields(profile, projection)
    _validate_candidate_custody(workspace_path, projection, profile)
    routes = _load_routes(
        projection,
        projection_path=projection_path,
        profile_path=profile_path,
    )
    generation = profile["generation"]
    feature_id = str(generation["feature_id"])
    public = projection["public_contract"]
    return AdmittedPacketContext(
        projection=projection,
        execution_profile=profile,
        projection_path=projection_path,
        execution_profile_path=profile_path,
        projection_sha256=projection_sha,
        execution_profile_sha256=hashlib.sha256(profile_raw).hexdigest(),
        source_routes=routes,
        feature_id=feature_id,
        writer_test_namespace=str(public["writer_test_namespace"]),
        writer_test_path=test_path,
        writer_node_ids=nodes,
        production_target_paths=tuple(profile["target_paths"]),
        red_test_command=red,
        green_test_command=green,
        full_suite_command=full,
    )


def assert_feature_matches_packet(
    context: AdmittedPacketContext,
    *,
    feature_id: str,
    acceptance_criteria: Sequence[str] | None = None,
) -> None:
    if feature_id != context.feature_id:
        raise AdmittedPacketError(
            "selected Bob feature is not the controller-admitted packet feature"
        )
    if acceptance_criteria is not None and tuple(acceptance_criteria) != context.acceptance_predicates:
        raise AdmittedPacketError(
            "Bob feature criteria are broader/different than the packet projection"
        )


def assert_packet_change_paths(
    context: AdmittedPacketContext,
    paths: Sequence[str],
    *,
    include_test: bool,
    label: str,
) -> None:
    expected = set(context.production_target_paths)
    if include_test:
        expected.add(context.writer_test_path)
    actual = {_relative_path(path, f"{label} path") for path in paths}
    if not actual.issubset(expected):
        raise AdmittedPacketError(
            f"{label} contains paths outside the admitted packet allowlist: "
            f"{sorted(actual - expected)}"
        )


def assert_exact_writer_result(
    context: AdmittedPacketContext,
    *,
    namespace: str,
    test_files: Sequence[str],
    collected_node_ids: Sequence[str],
    test_argv: Sequence[str],
) -> None:
    if namespace != context.writer_test_namespace:
        raise AdmittedPacketError("writer used a sibling or aliased test namespace")
    if tuple(test_files) != (context.writer_test_path,):
        raise AdmittedPacketError("writer did not create exactly the admitted test file")
    if tuple(collected_node_ids) != context.writer_node_ids:
        raise AdmittedPacketError("writer collected unexpected/missing packet test nodes")
    if tuple(test_argv) != context.red_test_command:
        raise AdmittedPacketError("writer used an unexpected red test command")


def packet_binding_payload(context: AdmittedPacketContext, *, role: str, session_id: str | None = None) -> dict[str, Any]:
    payload = dict(context.protected_evidence_bindings)
    payload.update(
        {
            "schema_version": "bob.admitted-packet-binding.v1",
            "role": _nonempty(role, "packet evidence role", max_chars=128),
            "provider_session_id": session_id,
            "writer_test_path": context.writer_test_path,
            "writer_node_ids": list(context.writer_node_ids),
            "production_target_paths": list(context.production_target_paths),
        }
    )
    return payload


__all__ = [
    "AUTHORITY",
    "EXECUTION_PROFILE_PATH_ENV",
    "EXECUTION_PROFILE_SCHEMA_VERSION",
    "EXECUTION_PROFILE_SHA256_ENV",
    "PROJECTION_PATH_ENV",
    "PROJECTION_SCHEMA_VERSION",
    "PROJECTION_SHA256_ENV",
    "REQUIRED_ENV",
    "AdmittedPacketContext",
    "AdmittedPacketError",
    "SourceRoute",
    "admitted_packet_required",
    "assert_exact_writer_result",
    "assert_feature_matches_packet",
    "assert_packet_change_paths",
    "canonical_json_bytes",
    "canonical_sha256",
    "load_admitted_packet_context",
    "packet_binding_payload",
]
