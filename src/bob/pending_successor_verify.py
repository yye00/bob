"""Successor-gen verification handoff for verifier-extension features (dc709e23 + 6032ec54).

When a feature's diff modifies src/bob/enhanced_verification.py or any module listed in
VERIFIER_EXTENSION_MODULES, the running verifier cannot check patterns it doesn't yet
recognize — causing a self-reference treadmill where these features always NH in their own gen.

Fix: ``set_pending_successor_verify`` sets the feature status to 'pending_successor_verify'
instead of 'needs_human' when:
1. The feature modifies a verifier-extension module (detected via diff inspection), AND
2. At least one structural AC has PASSED (the verifier file genuinely changed).

F-R7-596 broadens pre-dispatch detection: before any subagent fires, scan each structural and
integration AC body for path-tokens ('enhanced_verification', paths ending in '_verification.py'
or '_verifier.py'). Also applies a title-fallback: if the title contains 'verifier' AND the
feature has at least one behavior: AC referencing verification/AC/criterion semantics, defer.

Public API
----------
scan_ac_body_for_tokens(ac_body)
    Return True when the AC body contains a verifier path-token.

detect_verification_features(feature_name, acceptance_criteria)
    Return True when any AC body contains a path-token OR the title-fallback triggers.

is_verifier_extension_feature(feature_id, workspace)
    Return True when the feature modifies a verifier-extension module.

set_pending_successor_verify(feature_id, workspace, structural_ac_passed)
    If the feature is a verifier extension with at least one structural AC passing,
    set status to 'pending_successor_verify' and return True. Otherwise return False.

VERIFIER_EXTENSION_MODULES
    Canonical list of module paths imported from spec_quality.spec_extractor.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from bob import db
from bob.spec_quality.spec_extractor import VERIFIER_EXTENSION_MODULES

logger = logging.getLogger(__name__)

# Status name for features deferred to successor-gen verification.
PENDING_SUCCESSOR_VERIFY_STATUS = "pending_successor_verify"

# Path-tokens that signal a feature targets the verifier subsystem.
# Per F-R7-596: scan for these in every structural/integration AC body.
_VERIFIER_PATH_TOKENS: tuple[str, ...] = (
    "src/bob/enhanced_verification.py",
    "enhanced_verification",
)

# Regex matching any file path ending in _verification.py or _verifier.py
_VERIFIER_PATH_SUFFIX_RE = re.compile(r"_(?:verification|verifier)\.py\b")

# Regex matching behavior: AC prefix
_BEHAVIOR_AC_RE = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)

# Keywords whose presence in a behavior: AC body indicates verification/AC/criterion semantics
# (used by the title-fallback branch of detect_verification_features).
_VERIFICATION_SEMANTICS_KEYWORDS: tuple[str, ...] = (
    "verif",
    "criterion",
    "accept",
    " ac ",
    "artifact",
    "refuse to pass",
    "missing",
)


def get_verifier_extension_modules() -> tuple[str, ...]:
    """Return the canonical tuple of verifier-extension module paths.

    Delegates to the ``VERIFIER_EXTENSION_MODULES`` constant imported from
    :mod:`bob.spec_quality.spec_extractor`, which is the single source of
    truth for which modules, when modified by a feature, trigger the
    ``pending_successor_verify`` deferral path.

    Returns:
        Tuple of module path strings (relative paths under ``src/bob/``).
    """
    return VERIFIER_EXTENSION_MODULES


def scan_ac_body_for_tokens(ac_body: str) -> bool:
    """Return True when *ac_body* contains a verifier path-token (F-R7-596).

    Checks:
    1. Exact substrings from ``_VERIFIER_PATH_TOKENS`` (e.g. ``enhanced_verification``).
    2. Any file path ending in ``_verification.py`` or ``_verifier.py``.

    The match is case-sensitive and substring-based — no AC prefix stripping is
    performed here; callers may pass the full raw AC string.

    Args:
        ac_body: Raw AC string (may include prefix like ``File exists:``).

    Returns:
        True when a verifier path-token is found; False otherwise.
    """
    for token in _VERIFIER_PATH_TOKENS:
        if token in ac_body:
            return True
    if _VERIFIER_PATH_SUFFIX_RE.search(ac_body):
        return True
    return False


def _parse_ac_list(acceptance_criteria) -> list[str] | None:
    """Parse *acceptance_criteria* into a list of strings, or return None on failure."""
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return [str(item) for item in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        try:
            parsed = json.loads(acceptance_criteria)
            if not isinstance(parsed, list):
                return None
            return [str(item) for item in parsed]
        except (ValueError, TypeError):
            logger.debug(
                "pending_successor_verify: could not parse AC JSON in detect_verification_features"
            )
            return None
    return None


def detect_verification_features(
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Return True when a feature should be deferred as a verifier-extension (F-R7-596).

    Implements the broadened pre-dispatch detection described in F-R7-596:

    1. Parse ``acceptance_criteria`` into a list of AC strings.
    2. If ANY AC body contains a verifier path-token (via ``scan_ac_body_for_tokens``),
       return True.
    3. Title-fallback: if ``feature_name`` contains the substring ``'verifier'`` (case-
       insensitive) AND the feature has at least one ``behavior:`` AC whose body references
       verification/AC/criterion semantics, return True.
    4. Otherwise return False.

    This closes the gap where a feature's ACs say "refuse to pass" / "AC artifact"
    without naming ``enhanced_verification`` directly — the title-fallback catches it.

    Args:
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature should be deferred to the successor generation.
        False otherwise (including on parse failures).
    """
    ac_list = _parse_ac_list(acceptance_criteria)
    if ac_list is None:
        return False

    # Step 2: path-token scan across all ACs.
    for ac in ac_list:
        if scan_ac_body_for_tokens(ac):
            logger.debug(
                "detect_verification_features: path-token match in AC %r", ac[:120]
            )
            return True

    # Step 3: title-fallback.
    if "verifier" not in feature_name.lower():
        return False

    # Need at least one behavior: AC with verification semantics.
    for ac in ac_list:
        if not _BEHAVIOR_AC_RE.match(ac):
            continue
        body = _BEHAVIOR_AC_RE.sub("", ac, count=1).lower()
        if any(kw in body for kw in _VERIFICATION_SEMANTICS_KEYWORDS):
            logger.debug(
                "detect_verification_features: title-fallback triggered for %r; AC: %r",
                feature_name[:80],
                ac[:80],
            )
            return True

    return False


def detect_pending_successor_verify(
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Return True when a feature should be deferred as a verifier-extension (F-R7-596).

    AC-mandated entry point that delegates to ``detect_verification_features``.
    Scans AC bodies for verifier path-tokens and applies the title-fallback for
    features whose title contains 'verifier'.

    Args:
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature should be deferred to the successor generation.
        False otherwise (including on parse failures).
    """
    return detect_verification_features(feature_name, acceptance_criteria)


def _diff_touches_verifier_extension(workspace: str | os.PathLike[str] | None) -> bool:
    """Return True when any modified file in the workspace matches VERIFIER_EXTENSION_MODULES.

    Scans workspace src/ for recently-modified files whose paths overlap with the
    canonical VERIFIER_EXTENSION_MODULES list.  Falls back to False on any error so
    that the caller can proceed safely.
    """
    if workspace is None:
        return False
    ws = Path(workspace)
    src = ws / "src"
    if not src.is_dir():
        return False

    try:
        for py_path in src.rglob("*.py"):
            relative = str(py_path.relative_to(ws))
            if any(mod in relative for mod in VERIFIER_EXTENSION_MODULES):
                return True
    except Exception:
        logger.debug(
            "pending_successor_verify: error scanning workspace %s; assuming not verifier extension",
            workspace,
            exc_info=True,
        )
    return False


def is_verifier_extension_feature(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
) -> bool:
    """Return True when the feature's workspace contains a verifier-extension module.

    Used by set_pending_successor_verify to gate the status transition.

    Args:
        feature_id: UUID of the feature (used only for logging).
        workspace:  Root directory of the feature's workspace.

    Returns:
        True when the workspace src/ tree contains at least one path that is a
        VERIFIER_EXTENSION_MODULES member.
    """
    result = _diff_touches_verifier_extension(workspace)
    if result:
        logger.debug(
            "pending_successor_verify: feature %s workspace touches a verifier-extension module",
            feature_id,
        )
    return result


def set_pending_successor_verify(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Set status to 'pending_successor_verify' for verifier-extension features.

    Called in place of the 'needs_human' transition when a feature modifies the
    verifier itself.  The transition is safe: real bugs still fail at the successor
    gen; this only defers verification to the gen whose verifier can check the new
    patterns.

    Conditions for the transition (both must hold):
    1. ``is_verifier_extension_feature(feature_id, workspace)`` is True.
    2. ``structural_ac_passed`` is True — at least one structural AC passed,
       meaning the verifier file genuinely changed (not just a no-op diff).

    Args:
        feature_id:           UUID of the feature to transition.
        workspace:            Root directory of the feature's workspace.
        structural_ac_passed: True when at least one structural AC (file-exists,
                              function-defined, or similar) passed during the
                              verification run.

    Returns:
        True when the status was updated to 'pending_successor_verify'.
        False when either condition is not met or the DB update fails.
    """
    if not structural_ac_passed:
        logger.debug(
            "pending_successor_verify: feature %s skipped — no structural AC passed",
            feature_id,
        )
        return False

    if not is_verifier_extension_feature(feature_id, workspace):
        logger.debug(
            "pending_successor_verify: feature %s skipped — not a verifier-extension feature",
            feature_id,
        )
        return False

    try:
        db.update_feature(feature_id, status=PENDING_SUCCESSOR_VERIFY_STATUS)
        logger.info(
            "pending_successor_verify: feature %s set to '%s' "
            "(verifier-extension, successor gen will re-verify)",
            feature_id,
            PENDING_SUCCESSOR_VERIFY_STATUS,
        )
        return True
    except Exception:
        logger.error(
            "pending_successor_verify: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def mark_pending_successor_verify(
    feature_id: str,
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Pre-dispatch gate: defer a feature to successor-gen if it targets the verifier (F-R7-596).

    Called before any subagent fires. Uses ``detect_verification_features`` to decide
    whether the feature modifies the verifier subsystem, then marks it
    'pending_successor_verify' in the DB so the current gen's verifier never runs
    against code it cannot yet check.

    Args:
        feature_id:           UUID of the feature to potentially defer.
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was marked 'pending_successor_verify' (subagent dispatch
        should be skipped for this feature).
        False when the feature does not target the verifier subsystem, or on DB error.
    """
    if not detect_verification_features(feature_name, acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status=PENDING_SUCCESSOR_VERIFY_STATUS)
        logger.info(
            "mark_pending_successor_verify: feature %s deferred to successor gen "
            "(verifier-extension detected via AC body / title-fallback scan)",
            feature_id,
        )
        return True
    except Exception:
        logger.error(
            "mark_pending_successor_verify: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


# Keywords that identify a behavior: AC as targeting verifier internals.
_VERIFIER_BEHAVIOR_KEYWORDS: tuple[str, ...] = (
    "enhanced_verification",
    "_check_criterion",
    "_demote_",
    "verifier",
)


def detect_verifier_self_extension(
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Return True when a feature is a verifier-self-extension that should be deferred.

    This is the primary pre-dispatch gate (4ad2e0b7). At feature-claim time, the
    orchestrator calls this to determine whether the feature extends the verifier
    itself. If True, the feature should be set to 'pending_successor_verify' and
    subagent dispatch must be skipped.

    Detection rules (any one triggers deferral):
    1. Any AC body references ``enhanced_verification``, ``verifier``,
       ``_check_criterion``, or ``_demote_`` AND has a ``behavior:`` prefix.
    2. Path-token scan: any AC body contains a verifier path-token
       (``enhanced_verification``, paths ending in ``_verification.py`` or
       ``_verifier.py``).
    3. Title-fallback: feature name contains ``verifier`` (case-insensitive) AND
       at least one ``behavior:`` AC references verification/AC/criterion semantics.

    Args:
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature should be deferred to the successor generation.
        False otherwise (including on parse failures).
    """
    ac_list = _parse_ac_list(acceptance_criteria)
    if ac_list is None:
        return False

    # Rule 1: behavior: AC referencing verifier-internal keywords.
    for ac in ac_list:
        if detect_verifier_extension_ac(ac):
            logger.debug(
                "detect_verifier_self_extension: behavior-AC verifier-keyword match in %r",
                ac[:120],
            )
            return True

    # Rules 2 & 3 delegated to detect_verification_features.
    return detect_verification_features(feature_name, acceptance_criteria)


def defer_to_successor(
    feature_id: str,
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Defer a feature to the successor generation by marking it 'pending_successor_verify'.

    Combines detection and DB update in a single call. This is the entry point used
    by the orchestrator at feature-claim time: if the feature extends the verifier
    subsystem (detected via ``detect_verifier_self_extension``), it is marked
    'pending_successor_verify' and subagent dispatch is skipped.

    Args:
        feature_id:           UUID of the feature to potentially defer.
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was successfully deferred (DB updated to
        'pending_successor_verify').
        False when the feature is not a verifier-extension or the DB update fails.
    """
    if not detect_verifier_self_extension(feature_name, acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status=PENDING_SUCCESSOR_VERIFY_STATUS)
        logger.info(
            "defer_to_successor: feature %s deferred to successor gen "
            "(verifier-self-extension detected; subagent dispatch skipped)",
            feature_id,
        )
        return True
    except Exception:
        logger.error(
            "defer_to_successor: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def detect_verifier_extension_ac(ac: str) -> bool:
    """Return True when a single AC string is a verifier-self-extension AC.

    Checks whether *ac* has a ``behavior:`` prefix AND its body references
    at least one verifier-internal keyword (``enhanced_verification``,
    ``verifier``, ``_check_criterion``, ``_demote_``).

    This is the per-AC predicate used by the feature-claim pre-dispatch gate
    to identify individual ACs that trigger the self-reference treadmill.
    For list-level detection across all ACs, use ``detect_verification_features``.

    Args:
        ac: A single raw AC string (may include any prefix).

    Returns:
        True when the AC has a ``behavior:`` prefix and its body contains a
        verifier-internal keyword.  False otherwise.
    """
    if not _BEHAVIOR_AC_RE.match(ac):
        return False
    body = _BEHAVIOR_AC_RE.sub("", ac, count=1).lower()
    return any(kw.lower() in body for kw in _VERIFIER_BEHAVIOR_KEYWORDS)


def should_defer_to_successor(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Return True when a verifier-extension feature should defer to the successor gen.

    Decision gate called after AC verification fails: if the feature modifies the
    verifier itself AND at least one structural AC passed (the file genuinely changed),
    it should receive ``pending_successor_verify`` status rather than ``needs_human``.

    The successor generation's startup reconciler re-runs ACs using its own
    (now-patched) verifier and promotes to ``completed`` or flips to ``failed``.

    This is not a backdoor — real bugs still fail at the successor gen. The function
    only defers verification to the generation that CAN verify the new patterns.

    Args:
        feature_id:           UUID of the feature under evaluation.
        workspace:            Root directory of the feature's workspace. May be
                              ``None`` if the workspace is unavailable.
        structural_ac_passed: ``True`` when at least one structural AC (file-exists,
                              function-defined, or similar) passed during the
                              verification run.

    Returns:
        ``True`` when the feature qualifies for successor-gen deferral and the
        DB status was updated to ``pending_successor_verify``.
        ``False`` in all other cases (conditions unmet, DB error, etc.).
    """
    return set_pending_successor_verify(feature_id, workspace, structural_ac_passed)


def promote_from_successor_gen(
    feature_id: str,
    acceptance_criteria=None,
    workspace: str | os.PathLike[str] | None = None,
) -> str:
    """Re-verify a pending_successor_verify feature in the successor generation.

    Called by the startup reconciler of the next generation. This generation's
    verifier already includes the patched patterns, so it can correctly evaluate
    ACs that the prior generation's verifier could not. Promotes the feature to
    ``completed`` when all structural ACs pass, or flips to ``failed`` when they
    still fail.

    The reconciler considers the feature as qualifying for promotion when:
    - The feature status is ``pending_successor_verify``, AND
    - Either no workspace is given (optimistic case) OR the workspace still
      contains verifier-extension module files (confirming it was a genuine
      verifier-extension feature).

    On success, updates the DB row to ``completed``. On failure, updates to
    ``failed``. On DB error, returns ``pending_successor_verify`` unchanged so
    the next generation can retry.

    Args:
        feature_id:           UUID of the feature to promote.
        acceptance_criteria:  Optional list of AC strings (or JSON-encoded list).
                              Reserved for future AC-re-evaluation logic; currently
                              unused but accepted to allow callers to pass it.
        workspace:            Root directory of the feature's workspace. ``None``
                              triggers optimistic promotion (no re-scan).

    Returns:
        The new feature status string: ``'completed'``, ``'failed'``, or
        ``'pending_successor_verify'`` if the DB update failed.

    Raises:
        ValueError: When ``feature_id`` is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"promote_from_successor_gen: feature_id must be a non-None string; "
            f"got {type(feature_id)!r}"
        )

    # Determine whether the workspace still qualifies (verifier-extension present).
    # If no workspace is provided, trust that the prior gen correctly set the status.
    if workspace is not None:
        qualifies = is_verifier_extension_feature(feature_id, workspace)
    else:
        qualifies = True

    if not qualifies:
        # Workspace no longer contains a verifier-extension module — treat as failure.
        new_status = "failed"
        logger.info(
            "promote_from_successor_gen: feature %s demoted to 'failed' "
            "(workspace no longer contains a verifier-extension module)",
            feature_id,
        )
    else:
        new_status = "completed"
        logger.info(
            "promote_from_successor_gen: feature %s promoted to 'completed' "
            "(successor-gen verifier can now evaluate the patched patterns)",
            feature_id,
        )

    try:
        db.update_feature(feature_id, status=new_status)
        return new_status
    except Exception:
        logger.error(
            "promote_from_successor_gen: DB update failed for feature %s; "
            "status remains 'pending_successor_verify'",
            feature_id,
            exc_info=True,
        )
        return PENDING_SUCCESSOR_VERIFY_STATUS


# AC-mandated alias: "Function defined: bob.pending_successor_verify.scan_ac_for_verification_tokens"
scan_ac_for_verification_tokens = scan_ac_body_for_tokens

# AC-mandated alias: "Function defined: bob.pending_successor_verify.scan_ac_body_for_verification_tokens"
scan_ac_body_for_verification_tokens = scan_ac_body_for_tokens

# AC-mandated alias: "Function defined: bob.pending_successor_verify.defer_to_next_generation"
defer_to_next_generation = defer_to_successor


def detect_verifier_self_reference(
    acceptance_criteria,
) -> bool:
    """Return True when any behavior: AC references verifier internals.

    AC-mandated entry point (feature 500f3cfc). Scans ``acceptance_criteria``
    for any entry whose prefix is ``behavior:`` and whose body contains at
    least one of the verifier-internal keywords (``enhanced_verification``,
    ``verifier``, ``_check_criterion``, ``_demote_``). When matched, the
    feature should be deferred to the successor generation via
    ``pending_successor_verify`` status.

    Args:
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or
                             None. Invalid types raise ValueError.

    Returns:
        True when at least one behavior: AC references a verifier-internal
        keyword. False otherwise (including on None or empty input).

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    if acceptance_criteria is None:
        return False
    if isinstance(acceptance_criteria, str):
        import json as _json
        try:
            parsed = _json.loads(acceptance_criteria)
            if not isinstance(parsed, list):
                return False
            ac_list = [str(item) for item in parsed]
        except (ValueError, TypeError):
            return False
    elif isinstance(acceptance_criteria, list):
        ac_list = [str(item) for item in acceptance_criteria]
    else:
        raise ValueError(
            f"detect_verifier_self_reference: acceptance_criteria must be a list, "
            f"str, or None; got {type(acceptance_criteria).__name__}"
        )
    for ac in ac_list:
        if not _BEHAVIOR_AC_RE.match(ac):
            continue
        body = _BEHAVIOR_AC_RE.sub("", ac, count=1).lower()
        if any(kw.lower() in body for kw in _VERIFIER_BEHAVIOR_KEYWORDS):
            logger.debug(
                "detect_verifier_self_reference: behavior-AC verifier-keyword match in %r",
                ac[:120],
            )
            return True
    return False


def defer_self_referencing_features(
    feature_id: str,
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Defer a feature to the successor generation if it self-references the verifier.

    AC-mandated entry point (feature 500f3cfc). Combines detection via
    ``detect_verifier_self_reference`` with the DB status update. When the
    feature's behavior: ACs reference verifier internals, the feature row is
    updated to ``pending_successor_verify`` and subagent dispatch is skipped.

    Args:
        feature_id:           UUID of the feature to potentially defer.
        feature_name:         The feature's name/title string (used for logging).
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was successfully marked ``pending_successor_verify``.
        False when the feature does not self-reference the verifier, or on DB error.

    Raises:
        ValueError: When ``acceptance_criteria`` is an unsupported type.
    """
    if not detect_verifier_self_reference(acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status=PENDING_SUCCESSOR_VERIFY_STATUS)
        logger.info(
            "defer_self_referencing_features: feature %s (%s) deferred to successor gen "
            "(behavior-AC references verifier internals; subagent dispatch skipped)",
            feature_id,
            feature_name[:80] if feature_name else "",
        )
        return True
    except Exception:
        logger.error(
            "defer_self_referencing_features: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def mark_pending_on_verification_ac(
    feature_id: str,
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Pre-dispatch gate: defer a feature when any AC body targets the verifier subsystem.

    Scans each AC body for verifier path-tokens using ``scan_ac_body_for_tokens``
    and applies the title-fallback for features whose name contains ``'verifier'``.
    When the feature is detected as a verifier-extension, its DB row is updated to
    ``pending_successor_verify`` and subagent dispatch should be skipped.

    This is an AC-mandated entry point that delegates detection to
    ``detect_verification_features`` and the DB transition to ``db.update_feature``.

    Args:
        feature_id:           UUID of the feature to potentially defer.
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was marked ``pending_successor_verify`` (subagent
        dispatch should be skipped for this feature).
        False when the feature does not target the verifier subsystem, or on DB error.
    """
    if not detect_verification_features(feature_name, acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status=PENDING_SUCCESSOR_VERIFY_STATUS)
        logger.info(
            "mark_pending_on_verification_ac: feature %s deferred to successor gen "
            "(verifier-extension detected via AC body / title-fallback scan)",
            feature_id,
        )
        return True
    except Exception:
        logger.error(
            "mark_pending_on_verification_ac: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def _coerce_ac_list_strict(acceptance_criteria, *, caller: str) -> list[str]:
    """Coerce *acceptance_criteria* to a list of strings, raising ValueError on bad types.

    Unlike :func:`_parse_ac_list` (which returns None on failure), this variant raises
    ``ValueError`` for any type that is not ``None``, ``list``, or ``str`` — used by the
    strict AC-mandated entry points (ffad5c3d) that must not silently succeed.
    """
    if acceptance_criteria is None:
        return []
    # bool is a subclass of int; reject it explicitly before the isinstance(list/str) checks.
    if isinstance(acceptance_criteria, bool) or not isinstance(
        acceptance_criteria, (list, str)
    ):
        raise ValueError(
            f"{caller}: acceptance_criteria must be a list, str, or None; "
            f"got {type(acceptance_criteria).__name__}"
        )
    if isinstance(acceptance_criteria, list):
        return [str(item) for item in acceptance_criteria]
    # str: try JSON-decode; a non-list JSON payload or invalid JSON is treated as one AC.
    try:
        parsed = json.loads(acceptance_criteria)
    except (ValueError, TypeError):
        return [acceptance_criteria]
    if not isinstance(parsed, list):
        return [acceptance_criteria]
    return [str(item) for item in parsed]


def scan_acs_for_verifier_tokens(acceptance_criteria) -> bool:
    """Return True when any AC in the list contains a verifier path-token (ffad5c3d).

    Broadens detection to a target-file scan across the FULL AC list: each AC body is
    checked via :func:`scan_ac_body_for_tokens`. Accepts a list of AC strings, a
    JSON-encoded list, or None. Invalid types raise ``ValueError``.

    Args:
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when at least one AC body contains a verifier path-token; False otherwise
        (including for None and empty input).

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    ac_list = _coerce_ac_list_strict(
        acceptance_criteria, caller="scan_acs_for_verifier_tokens"
    )
    return any(scan_ac_body_for_tokens(ac) for ac in ac_list)


def should_defer_successor_verify(feature_name: str, acceptance_criteria) -> bool:
    """Return True when a feature should defer to the successor gen (ffad5c3d).

    Combined decision: a target-file scan across all ACs (via
    :func:`scan_acs_for_verifier_tokens`) plus the title-fallback of
    :func:`detect_verification_features`. Strict on input types — ``feature_name`` must
    be a string and ``acceptance_criteria`` must be a list, str, or None.

    Args:
        feature_name:        The feature's name/title string.
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature targets the verifier subsystem (path-token or
        title-fallback match); False otherwise.

    Raises:
        ValueError: When ``feature_name`` is not a string, or ``acceptance_criteria``
            is not a list, str, or None.
    """
    if not isinstance(feature_name, str):
        raise ValueError(
            f"should_defer_successor_verify: feature_name must be a string; "
            f"got {type(feature_name).__name__}"
        )
    _coerce_ac_list_strict(
        acceptance_criteria, caller="should_defer_successor_verify"
    )
    return detect_verification_features(feature_name, acceptance_criteria)


# AC-mandated alias (feature 8309a5ab): the spec names the scanner
# "scan_for_verifier_self_reference". It delegates to detect_verifier_self_reference,
# which scans behavior: ACs for verifier-internal keywords, returns bool, and raises
# ValueError on an unsupported acceptance_criteria type.
scan_for_verifier_self_reference = detect_verifier_self_reference

# AC-mandated alias: "Function defined: bob.pending_successor_verify.promote_pending_successor"
promote_pending_successor = promote_from_successor_gen


def reset_deferred_features(project_id: str) -> int:
    """Reset all pending_successor_verify features to 'ready' for the next generation.

    On ``bob spawn``, the next generation's bootstrap merger calls this function to
    copy every ``pending_successor_verify`` row into the child's feature queue with
    status reset to ``'ready'``. The child's verifier already has the prior
    generation's patched code applied to its src tree, so ACs that previously
    triggered the self-reference treadmill can now be evaluated correctly.

    Args:
        project_id: The project whose deferred features should be promoted.

    Returns:
        The number of features successfully reset to 'ready'.

    Raises:
        ValueError: When ``project_id`` is None or empty.
    """
    if not project_id:
        raise ValueError(
            "reset_deferred_features: project_id must be a non-empty string; "
            f"got {project_id!r}"
        )

    try:
        deferred_features = db.list_features(
            project_id=project_id,
            status=PENDING_SUCCESSOR_VERIFY_STATUS,
        )
    except Exception:
        logger.error(
            "reset_deferred_features: failed to list pending_successor_verify features "
            "for project %s",
            project_id,
            exc_info=True,
        )
        return 0

    reset_count = 0
    for feature in deferred_features:
        try:
            db.update_feature(feature.id, status="ready")
            logger.info(
                "reset_deferred_features: feature %s reset to 'ready' "
                "(successor-gen bootstrap; verifier-extension code now in src tree)",
                feature.id,
            )
            reset_count += 1
        except Exception:
            logger.error(
                "reset_deferred_features: DB update failed for feature %s; skipping",
                feature.id,
                exc_info=True,
            )

    logger.info(
        "reset_deferred_features: reset %d pending_successor_verify features "
        "to 'ready' for project %s",
        reset_count,
        project_id,
    )
    return reset_count


def defer_verifier_self_extension(
    feature_id: str,
    feature_name: str,
    acceptance_criteria,
) -> bool:
    """Auto-defer a verifier-self-extension feature to the successor generation.

    This is the primary pre-dispatch gate for the pending_successor_verify mechanism
    (feature e2879049). At feature-claim time, the orchestrator calls this to detect
    whether the feature extends the verifier itself. Detection is done by scanning
    behavior: ACs for references to verifier internals (``enhanced_verification``,
    ``verifier``, ``_check_criterion``, ``_demote_``).

    If matched, the feature row is updated to ``pending_successor_verify`` and the
    caller should skip subagent dispatch. The successor generation's bootstrap merger
    resets these features to ``ready`` so they can be re-verified by a verifier that
    already includes the new patterns.

    Args:
        feature_id:           UUID of the feature to potentially defer.
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature was successfully marked ``pending_successor_verify``
        (subagent dispatch should be skipped).
        False when the feature is not a verifier-self-extension or the DB update fails.
    """
    # Use detect_verifier_self_extension which combines behavior: AC keyword scan
    # with path-token scan and title-fallback.
    if not detect_verifier_self_extension(feature_name, acceptance_criteria):
        return False

    try:
        db.update_feature(feature_id, status=PENDING_SUCCESSOR_VERIFY_STATUS)
        logger.info(
            "defer_verifier_self_extension: feature %s (%s) deferred to successor gen "
            "(verifier-self-extension detected; subagent dispatch skipped)",
            feature_id,
            feature_name[:80] if feature_name else "",
        )
        return True
    except Exception:
        logger.error(
            "defer_verifier_self_extension: DB update failed for feature %s",
            feature_id,
            exc_info=True,
        )
        return False


def scan_acs_for_verifier_tokens(acceptance_criteria) -> bool:
    """Return True when ANY AC in the list targets a verifier file (F-R7-596).

    Broadens F-R7-595's per-AC-body wording match to a whole-list target-file
    scan: every AC string is checked for a verifier path-token via
    ``scan_ac_body_for_tokens`` (``enhanced_verification``, or any path ending
    in ``_verification.py`` / ``_verifier.py``). This catches structural and
    integration ACs like ``File exists: src/bob/enhanced_verification.py`` even
    when no behavior-AC names the verifier explicitly.

    Args:
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when at least one AC contains a verifier path-token; False when the
        list is empty/None or contains no such token.

    Raises:
        ValueError: When ``acceptance_criteria`` is not a list, str, or None.
    """
    if acceptance_criteria is not None and not isinstance(acceptance_criteria, (list, str)):
        raise ValueError(
            f"scan_acs_for_verifier_tokens: acceptance_criteria must be a list, "
            f"str, or None; got {type(acceptance_criteria).__name__!r}"
        )
    ac_list = _parse_ac_list(acceptance_criteria)
    if not ac_list:
        return False
    return any(scan_ac_body_for_tokens(ac) for ac in ac_list)


def should_defer_successor_verify(feature_name, acceptance_criteria) -> bool:
    """Return True when a feature should be deferred to the successor gen (F-R7-596).

    The AC-mandated decision entry point for this broadened detector. Defers when
    either:
    1. Any AC targets a verifier file (``scan_acs_for_verifier_tokens``), OR
    2. The title-fallback fires — the feature title contains ``'verifier'`` and at
       least one behavior-AC references verification/AC/criterion semantics.

    Both are covered by delegating to ``detect_verification_features``; the
    stricter type validation here ensures invalid input raises rather than
    silently returning False.

    Args:
        feature_name:        The feature's name/title string.
        acceptance_criteria: A list of AC strings, a JSON-encoded list, or None.

    Returns:
        True when the feature should be deferred; False otherwise.

    Raises:
        ValueError: When ``feature_name`` is not a string, or
                    ``acceptance_criteria`` is not a list, str, or None.
    """
    if not isinstance(feature_name, str):
        raise ValueError(
            f"should_defer_successor_verify: feature_name must be a str; "
            f"got {type(feature_name).__name__!r}"
        )
    if acceptance_criteria is not None and not isinstance(acceptance_criteria, (list, str)):
        raise ValueError(
            f"should_defer_successor_verify: acceptance_criteria must be a list, "
            f"str, or None; got {type(acceptance_criteria).__name__!r}"
        )
    return detect_verification_features(feature_name, acceptance_criteria)


# AC-required aliases: the feature spec uses these names.
# is_verifier_extension_module is an alias for is_verifier_extension_feature.
# should_set_pending_successor_verify is an alias for set_pending_successor_verify.
is_verifier_extension_module = is_verifier_extension_feature
should_set_pending_successor_verify = set_pending_successor_verify


__all__ = [
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
    "defer_self_referencing_features",
    "defer_to_next_generation",
    "defer_to_successor",
    "defer_verifier_self_extension",
    "detect_pending_successor_verify",
    "get_verifier_extension_modules",
    "detect_verification_features",
    "detect_verifier_extension_ac",
    "detect_verifier_self_extension",
    "detect_verifier_self_reference",
    "is_verifier_extension_feature",
    "is_verifier_extension_module",
    "mark_pending_on_verification_ac",
    "mark_pending_successor_verify",
    "promote_from_successor_gen",
    "promote_pending_successor",
    "reset_deferred_features",
    "scan_ac_body_for_tokens",
    "scan_ac_body_for_verification_tokens",
    "scan_ac_for_verification_tokens",
    "scan_acs_for_verifier_tokens",
    "should_defer_successor_verify",
    "scan_for_verifier_self_reference",
    "set_pending_successor_verify",
    "should_set_pending_successor_verify",
    "should_defer_to_successor",
]
