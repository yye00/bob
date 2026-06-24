"""Regression attribution — charge the feature that caused a test to break.

Feature 15f5b3b8-a57f-4fb7-91e7-859767805eca (original AC-level attribution)
Feature aaa5a7f7-74e2-4edc-b61c-ac822dfced4f (ownership-evidenced regression detection)

Problem solved
--------------
When feature B's ``tests_pass`` check fails because feature A's tests are
broken, *both* A and B currently get demoted (rfn decremented).  This module
introduces a two-step attribution layer:

1. ``attribute_failures`` — for each failing test node-id, walk every
   feature's ``acceptance_criteria`` list and find the feature whose
   ``pytest:`` AC claims that test path.  A feature "owns" a failing test
   when the test node-id starts with the path declared in its
   ``pytest:`` criterion.

2. ``charge_owners`` — given the attribution map produced by step 1, call
   the supplied ``increment_fn`` exactly once per *unique* owning feature-id.
   Features that appear in the verification run but own no failing test are
   completely untouched.

Integration
-----------
``bob3.orchestrator.run_loop`` can call these two helpers after
``run_verification_checklist`` reports failures, replacing the current
unconditional ``increment_refinement_attempts(feature.id)`` with a targeted
charge.

The helpers are deliberately stateless (no DB access) so they are trivially
testable and easy to unit-test without a live database.  All DB side-effects
are performed by the caller (typically the orchestration loop) via the
``increment_fn`` callback.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Prefix that marks a test-path acceptance criterion
_PYTEST_PREFIX = "pytest:"


def _parse_ac_list(acceptance_criteria: Any) -> list[str]:
    """Return the acceptance-criteria as a flat list of strings.

    Handles three storage formats found in the wild:
    - JSON array string: ``'["pytest: tests/test_foo.py"]'``
    - Plain text / comma-separated string: ``"pytest: tests/test_foo.py"``
    - Already a Python list: ``["pytest: tests/test_foo.py"]``
    """
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return [str(c) for c in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        raw = acceptance_criteria.strip()
        if not raw:
            return []
        # Attempt JSON first (the canonical DB format is a JSON array)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(c) for c in parsed]
            # Scalar JSON — treat the whole string as a single criterion
            return [str(parsed)]
        except (json.JSONDecodeError, ValueError):
            pass
        # Fall back to treating the string as a single AC entry (single
        # plain text criterion without commas / newlines).
        return [raw]
    # Any other type — coerce to string and treat as a single criterion
    return [str(acceptance_criteria)]


def _extract_pytest_paths(ac_list: list[str]) -> list[str]:
    """Return the test-path arguments from 'pytest:' prefixed ACs.

    ``"pytest: tests/test_foo.py::test_bar"`` → ``["tests/test_foo.py::test_bar"]``
    ``"File exists: src/foo.py"`` → (skipped)
    """
    paths: list[str] = []
    for criterion in ac_list:
        stripped = criterion.strip()
        lower = stripped.lower()
        if lower.startswith(_PYTEST_PREFIX):
            path = stripped[len(_PYTEST_PREFIX):].strip()
            if path:
                paths.append(path)
    return paths


def _test_matches_pytest_path(test_nodeid: str, pytest_path: str) -> bool:
    """Return True when *test_nodeid* is claimed by *pytest_path*.

    A criterion like ``tests/test_foo.py::test_bar`` matches only the exact
    node-id ``tests/test_foo.py::test_bar``.

    A criterion like ``tests/test_foo.py`` (file only, no ``::`` separator)
    matches any node-id whose prefix is ``tests/test_foo.py::`` — i.e., any
    test inside that file.

    Path comparison is byte-exact (no normalisation) to keep the logic simple
    and auditable.
    """
    if "::" not in pytest_path:
        # File-level claim: match any test inside the file
        return test_nodeid.startswith(pytest_path + "::")
    # Exact node-id claim
    return test_nodeid == pytest_path


def attribute_failures(
    *,
    failing_tests: list[str],
    all_features: list[Any],
) -> dict[str, str | None]:
    """Map each failing test node-id to the feature-id that owns it.

    Args:
        failing_tests: List of pytest node-ids that are currently failing,
            e.g. ``["tests/test_foo.py::test_bar"]``.
        all_features: Sequence of feature objects or dicts.  Each entry must
            expose either ``.id`` / ``.acceptance_criteria`` attributes or
            the equivalent ``dict`` keys.

    Returns:
        A ``dict[test_nodeid, feature_id | None]`` covering every entry in
        *failing_tests*.  A ``None`` value means no feature's ``pytest:`` AC
        claims that test.
    """
    if not failing_tests:
        return {}

    # Pre-build a lookup: feature_id → [claimed pytest paths]
    # Only features with at least one pytest: AC participate.
    feature_pytest_paths: list[tuple[str, list[str]]] = []
    for feature in all_features:
        # Support both dict-style and object-style access
        if isinstance(feature, dict):
            fid = feature.get("id", "")
            ac_raw = feature.get("acceptance_criteria")
        else:
            fid = getattr(feature, "id", "")
            ac_raw = getattr(feature, "acceptance_criteria", None)
        if not fid:
            continue
        ac_list = _parse_ac_list(ac_raw)
        paths = _extract_pytest_paths(ac_list)
        if paths:
            feature_pytest_paths.append((fid, paths))

    result: dict[str, str | None] = {}
    for test_nodeid in failing_tests:
        owner: str | None = None
        for fid, paths in feature_pytest_paths:
            for path in paths:
                if _test_matches_pytest_path(test_nodeid, path):
                    owner = fid
                    break
            if owner is not None:
                break
        result[test_nodeid] = owner
        if owner is None:
            logger.debug(
                "Failing test %r has no owning feature in the AC table",
                test_nodeid,
            )
        else:
            logger.debug(
                "Failing test %r attributed to feature %s",
                test_nodeid,
                owner,
            )

    return result


def charge_owners(
    *,
    attribution: dict[str, str | None],
    increment_fn: Callable[[str], Any],
) -> set[str]:
    """Call *increment_fn* exactly once per unique owning feature-id.

    Args:
        attribution: Mapping produced by :func:`attribute_failures`.  Keys
            are test node-ids; values are feature-ids or ``None`` (unowned).
        increment_fn: Callable that accepts a ``feature_id: str`` and records
            one refinement-attempt charge against that feature.  Typically
            ``db.increment_refinement_attempts``.

    Returns:
        The set of feature-ids that were charged (for caller logging /
        auditing).  Features that own no failing test are never passed to
        *increment_fn*.
    """
    owners: set[str] = set()
    for test_nodeid, owner in attribution.items():
        if owner is not None:
            owners.add(owner)

    for feature_id in owners:
        logger.info(
            "Charging refinement attempt to feature %s (regression attribution)",
            feature_id,
        )
        increment_fn(feature_id)

    return owners


# ---------------------------------------------------------------------------
# Feature aaa5a7f7: Ownership-evidenced regression detection
# ---------------------------------------------------------------------------

# The file path of this module — any feature owning this file cannot be its
# own scapegoat (F-15f5b3b8 guard).
_REGRESSION_ATTRIBUTION_MODULE_PATH = "src/bob3/orchestrator/regression_attribution.py"

# Minimum confidence required to demote a feature to 'regression'.
_CONFIDENCE_THRESHOLD = 0.60

# Maximum transitive import depth to follow when resolving attribution.
_MAX_TRANSITIVE_DEPTH = 3


def build_ownership_map(
    *,
    features: list[dict],
    recent_commits: list[dict],
) -> dict[str, set[str]]:
    """Return a mapping from feature_id to the set of file paths that feature owns.

    Ownership is derived by walking each feature's ``commit_ids`` list and
    collecting all ``files_touched`` from matching commits.

    Args:
        features: List of feature dicts, each with ``id`` and ``commit_ids``.
        recent_commits: List of commit dicts, each with ``commit_id`` and
            ``files_touched`` (list of file-path strings).

    Returns:
        ``dict[feature_id, set[file_path]]``  — every feature in *features*
        appears as a key; features with no matching commits map to an empty set.
    """
    # Build a fast lookup from commit_id → files_touched
    commit_files: dict[str, set[str]] = {}
    for commit in recent_commits:
        cid = commit.get("commit_id", "")
        files = commit.get("files_touched", [])
        if cid:
            commit_files[cid] = set(files)

    result: dict[str, set[str]] = {}
    for feature in features:
        fid = feature.get("id", "")
        if not fid:
            continue
        commit_ids = feature.get("commit_ids", []) or []
        owned_files: set[str] = set()
        for cid in commit_ids:
            owned_files.update(commit_files.get(cid, set()))
        result[fid] = owned_files

    return result


def _collect_breaking_files(recent_commits: list[dict]) -> set[str]:
    """Return the union of all files touched by the recent breaking commits."""
    breaking: set[str] = set()
    for commit in recent_commits:
        breaking.update(commit.get("files_touched", []))
    return breaking


def _transitive_reachable(
    start_files: set[str],
    transitive_deps: dict[str, set[str]],
    max_depth: int,
) -> set[str]:
    """Return all files reachable from *start_files* via *transitive_deps* within *max_depth* hops."""
    reachable = set(start_files)
    frontier = set(start_files)
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for f in frontier:
            next_frontier.update(transitive_deps.get(f, set()))
        new = next_frontier - reachable
        if not new:
            break
        reachable.update(new)
        frontier = new
    return reachable


def _stem_from_path(file_path: str) -> str:
    """Return the basename stem (no directory, no extension) of a file path."""
    basename = file_path.rsplit("/", 1)[-1]
    if "." in basename:
        basename = basename.rsplit(".", 1)[0]
    return basename


def _find_anchor_feature(
    failing_test_id: str,
    ownership_map: dict[str, set[str]],
) -> str | None:
    """Return the feature_id that 'owns' the failing test by stem-prefix matching.

    Extracts the test module stem (e.g. ``test_a.py`` → ``a``), then finds the
    first feature whose owned files contain a source file whose stem starts with
    that test stem.  Falls back to None when no match is found.
    """
    # Extract test file path from node-id (before the ``::`` separator)
    test_file = failing_test_id.split("::")[0]
    test_stem = _stem_from_path(test_file)
    # Strip conventional ``test_`` prefix
    if test_stem.startswith("test_"):
        test_stem = test_stem[len("test_"):]
    if not test_stem:
        return None

    for feature_id, owned_files in ownership_map.items():
        for f in owned_files:
            src_stem = _stem_from_path(f)
            if src_stem.startswith(test_stem):
                return feature_id
    return None


def _build_reverse_ownership(
    ownership_map: dict[str, set[str]],
) -> dict[str, str]:
    """Return a mapping from file_path → feature_id for the feature that owns each file."""
    reverse: dict[str, str] = {}
    for feature_id, owned_files in ownership_map.items():
        for f in owned_files:
            reverse[f] = feature_id
    return reverse


def attribute_breakage(
    *,
    failing_test_id: str,
    recent_commits: list[dict],
    ownership_map: dict[str, set[str]],
    transitive_deps: dict[str, set[str]] | None = None,
) -> dict:
    """Attribute a failing test to the feature most likely responsible.

    Attribution is anchor-based:

    1. Find the **anchor feature** — the feature that owns the failing test
       (matched by stripping the ``test_`` prefix from the test filename and
       finding a feature whose source file stems share that prefix).
    2. If the anchor's owned files have **direct overlap** with the breaking
       commit's touched files → attribute to the anchor itself.
    3. If the anchor's files **transitively import** files owned by another
       feature that was directly touched (up to depth 3) → attribute to that
       other feature (the actual cause).
    4. If no anchor is found, fall back to the feature with the highest direct
       overlap confidence.
    5. **Self-blame guard**: if the attributed feature owns
       ``regression_attribution.py``, mark as ``false_positive_self_blame``
       and skip demotion.

    Args:
        failing_test_id: The pytest node-id of the test that is now failing.
        recent_commits: List of commit dicts (``commit_id``, ``files_touched``).
        ownership_map: Mapping from feature_id to the set of files it owns
            (as returned by :func:`build_ownership_map`).
        transitive_deps: Optional ``{file_path: set[imported_file_paths]}``.
            When provided, attribution can follow import edges up to depth 3.

    Returns:
        A dict with keys:
        - ``attributed_feature``: feature_id or None
        - ``evidence``: list of human-readable strings
        - ``confidence``: float in [0, 1]
        - ``false_positive_self_blame``: bool (True when the guard fired)
    """
    if transitive_deps is None:
        transitive_deps = {}

    breaking_files = _collect_breaking_files(recent_commits)

    result: dict = {
        "attributed_feature": None,
        "evidence": [],
        "confidence": 0.0,
        "false_positive_self_blame": False,
    }

    if not breaking_files:
        return result

    # Reverse map: file_path → feature_id (who owns each file)
    file_to_feature = _build_reverse_ownership(ownership_map)

    # Find the anchor feature — the one whose test is failing
    anchor_id = _find_anchor_feature(failing_test_id, ownership_map)

    if anchor_id is not None:
        anchor_files = ownership_map.get(anchor_id, set())

        # Step 1: direct overlap — the anchor's own code was changed
        direct_overlap = anchor_files & breaking_files
        if direct_overlap:
            confidence = len(direct_overlap) / len(anchor_files) if anchor_files else 0.0
            evidence = [f"file {f!r} touched by a breaking commit" for f in sorted(direct_overlap)]
            is_self_blame = _REGRESSION_ATTRIBUTION_MODULE_PATH in anchor_files
            if is_self_blame:
                result["false_positive_self_blame"] = True
                result["evidence"] = evidence
                return result
            result["attributed_feature"] = anchor_id
            result["evidence"] = evidence
            result["confidence"] = confidence
            return result

        # Step 2: transitive — anchor's imports lead to a touched file owned by another feature
        if transitive_deps:
            reachable = _transitive_reachable(anchor_files, transitive_deps, _MAX_TRANSITIVE_DEPTH)
            # Find touched files reachable from anchor (excluding anchor's own files)
            transitive_touched = (reachable - anchor_files) & breaking_files
            if transitive_touched:
                # Find the feature that owns the transitively-touched file
                cause_feature: str | None = None
                cause_files: set[str] = set()
                for f in transitive_touched:
                    owner = file_to_feature.get(f)
                    if owner is not None and owner != anchor_id:
                        cause_feature = owner
                        cause_files.add(f)
                        break  # Take the first match

                if cause_feature is not None:
                    cause_owned = ownership_map.get(cause_feature, set())
                    confidence = len(cause_files) / len(cause_owned) if cause_owned else 0.0
                    evidence = [f"(transitive) file {f!r} touched by a breaking commit" for f in sorted(cause_files)]
                    is_self_blame = _REGRESSION_ATTRIBUTION_MODULE_PATH in cause_owned
                    if is_self_blame:
                        result["false_positive_self_blame"] = True
                        result["evidence"] = evidence
                        return result
                    result["attributed_feature"] = cause_feature
                    result["evidence"] = evidence
                    result["confidence"] = confidence
                    return result

        # Anchor found but no chain to breaking commit
        return result

    # Fallback: no anchor — find the feature with the best direct overlap
    best_feature: str | None = None
    best_confidence: float = 0.0
    best_evidence: list[str] = []
    best_is_self_blame: bool = False

    for feature_id, owned_files in ownership_map.items():
        if not owned_files:
            continue
        direct_overlap = owned_files & breaking_files
        if not direct_overlap:
            continue
        confidence = len(direct_overlap) / len(owned_files)
        evidence = [f"file {f!r} touched by a breaking commit" for f in sorted(direct_overlap)]
        is_self_blame = _REGRESSION_ATTRIBUTION_MODULE_PATH in owned_files
        if confidence > best_confidence:
            best_feature = feature_id
            best_confidence = confidence
            best_evidence = evidence
            best_is_self_blame = is_self_blame

    if best_is_self_blame:
        result["false_positive_self_blame"] = True
        result["evidence"] = best_evidence
        result["confidence"] = 0.0
        result["attributed_feature"] = None
        return result

    result["attributed_feature"] = best_feature
    result["evidence"] = best_evidence
    result["confidence"] = best_confidence
    return result


def demote_with_evidence(
    *,
    feature_id: str | None,
    evidence: list[str],
    confidence: float,
    failing_test_id: str,
    recent_commits: list[dict],
    false_positive_self_blame: bool = False,
    _update_feature_fn=None,
    _emit_event_fn=None,
) -> None:
    """Atomically demote a feature to 'regression' only when evidence warrants it.

    Demotion conditions (ALL must be true):
    1. ``feature_id`` is not None
    2. ``evidence`` is non-empty
    3. ``confidence >= 0.60``
    4. ``false_positive_self_blame`` is False

    When any condition fails:
    - If ``false_positive_self_blame`` is True: emit a ``false_positive_self_blame`` event.
    - Otherwise (no evidence / low confidence / no feature): emit a
      ``regression_unattributed`` event containing ``failing_test_id`` and
      ``recent_commits``.

    Args:
        feature_id: The feature to demote (or None for unattributed cases).
        evidence: List of evidence strings supporting attribution.
        confidence: Attribution confidence in [0, 1].
        failing_test_id: The pytest node-id of the failing test.
        recent_commits: The recent commits list (included in unattributed events).
        false_positive_self_blame: When True, the attribution heuristic pointed
            back to the regression_attribution feature itself — skip and emit event.
        _update_feature_fn: Callable ``(feature_id: str, status: str) -> None``.
            Defaults to ``bob3.db.update_feature``.
        _emit_event_fn: Callable ``(event_type: str, **kwargs) -> None``.
            Defaults to a logger-based emitter.
    """
    if _update_feature_fn is None:
        from bob3 import db as _db
        _update_feature_fn = _db.update_feature

    if _emit_event_fn is None:
        def _emit_event_fn(event_type: str, **kwargs):
            logger.info("regression_attribution event %s: %s", event_type, kwargs)

    # Self-blame guard
    if false_positive_self_blame:
        logger.warning(
            "Self-blame guard fired for feature %s on test %s — skipping demotion",
            feature_id,
            failing_test_id,
        )
        _emit_event_fn(
            "false_positive_self_blame",
            feature_id=feature_id,
            failing_test_id=failing_test_id,
        )
        return

    # Check all demotion conditions
    can_demote = (
        feature_id is not None
        and len(evidence) > 0
        and confidence >= _CONFIDENCE_THRESHOLD
    )

    if can_demote:
        logger.info(
            "Demoting feature %s to 'regression' (confidence=%.2f, evidence=%s)",
            feature_id,
            confidence,
            evidence,
        )
        _update_feature_fn(feature_id, "regression")
    else:
        logger.info(
            "Regression unattributed for test %s (feature=%s, confidence=%.2f, evidence=%s)",
            failing_test_id,
            feature_id,
            confidence,
            evidence,
        )
        _emit_event_fn(
            "regression_unattributed",
            failing_test_id=failing_test_id,
            recent_commits=recent_commits,
            feature_id=feature_id,
            confidence=confidence,
        )
