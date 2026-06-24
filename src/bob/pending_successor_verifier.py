"""Broadened pending_successor_verify detection via target-file scan (F-R7-596).

F-R7-595 deferred verifier-self-extension features by pattern-matching AC body
text for 'enhanced_verification', '_check_', '_demote_'. This worked for most
cases but missed feature d34c40f0 ("AC artifact-existence verifier"), whose AC
bodies said 'refuse to pass' / 'AC artifact' without naming enhanced_verification.

F-R7-596 broadens detection three ways:

1. **AC body scan** — scan each structural/integration AC body for path-tokens:
   - 'src/bob/enhanced_verification.py'
   - 'enhanced_verification' (anywhere)
   - any path ending in '_verification.py' or '_verifier.py'

2. **Target-file scan** — for each AC referencing a concrete file path, resolve
   the file relative to the workspace (if provided) and scan file contents for
   the same path-tokens. Catches cases where the AC body says
   'File exists: src/bob/some_handler.py' but the file itself imports
   enhanced_verification.

3. **Title-fallback** — if the feature title contains 'verifier' AND at least
   one behavior: AC references verification/AC/criterion semantics, defer.

Safety: detector only adds defers; it cannot un-defer or close anything.
False-positives push a feature one gen forward (no regression vs current
behavior). False-negatives reduce to the v.28 ceiling.

Public API
----------
detect_pending_successor_verify(feature_name, acceptance_criteria, workspace=None)
    Return True when the feature should be deferred as a verifier-extension.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Path-tokens that signal a feature targets the verifier subsystem.
_VERIFIER_PATH_TOKENS: tuple[str, ...] = (
    "src/bob/enhanced_verification.py",
    "enhanced_verification",
)

# Regex matching any file path ending in _verification.py or _verifier.py
_VERIFIER_PATH_SUFFIX_RE = re.compile(r"_(?:verification|verifier)\.py\b")

# Regex matching behavior: AC prefix
_BEHAVIOR_AC_RE = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)

# Keywords in a behavior: AC body indicating verification/AC/criterion semantics
_VERIFICATION_SEMANTICS_KEYWORDS: tuple[str, ...] = (
    "verif",
    "criterion",
    "accept",
    " ac ",
    "artifact",
    "refuse to pass",
    "missing",
)

# Regex to extract file path from "File exists: <path>" ACs
_FILE_EXISTS_RE = re.compile(r"^\s*file\s+exists\s*:\s*(.+)", re.IGNORECASE)


def _parse_ac_list(acceptance_criteria) -> list[str] | None:
    """Parse acceptance_criteria into a list of strings.

    Raises ValueError for unsupported types (not list/str/None).
    Returns [] for None.
    Returns None on JSON parse failure for non-list JSON.
    """
    if acceptance_criteria is None:
        return []
    if isinstance(acceptance_criteria, list):
        return [str(item) for item in acceptance_criteria]
    if isinstance(acceptance_criteria, str):
        if not acceptance_criteria.strip():
            return []
        try:
            parsed = json.loads(acceptance_criteria)
            if not isinstance(parsed, list):
                return None
            return [str(item) for item in parsed]
        except (ValueError, TypeError):
            return []
    raise ValueError(
        f"detect_pending_successor_verify: acceptance_criteria must be a list, "
        f"str, or None; got {type(acceptance_criteria).__name__!r}"
    )


def _ac_body_has_verifier_token(body: str) -> bool:
    """Return True when body contains a verifier path-token."""
    for token in _VERIFIER_PATH_TOKENS:
        if token in body:
            return True
    if _VERIFIER_PATH_SUFFIX_RE.search(body):
        return True
    return False


def _scan_target_file(file_path: str | os.PathLike[str]) -> bool:
    """Return True when the file at file_path contains a verifier path-token.

    Returns False on any I/O error so the caller can proceed safely.
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        logger.debug(
            "pending_successor_verifier: could not read target file %s",
            file_path,
            exc_info=True,
        )
        return False
    return _ac_body_has_verifier_token(content)


def _extract_file_paths(ac_list: list[str]) -> list[str]:
    """Return file paths referenced by 'File exists:' ACs."""
    paths = []
    for ac in ac_list:
        m = _FILE_EXISTS_RE.match(ac)
        if m:
            paths.append(m.group(1).strip())
    return paths


def detect_pending_successor_verify(
    feature_name: str = "",
    acceptance_criteria=None,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when a feature should be deferred as a verifier-extension (F-R7-596).

    Implements the broadened pre-dispatch detection:

    1. Parse acceptance_criteria into a list of AC strings.
    2. **AC body scan**: if ANY AC body contains a verifier path-token, return True.
    3. **Target-file scan**: for each 'File exists:' AC, resolve the referenced
       file relative to workspace (if provided) and scan its content for
       verifier path-tokens. Return True if any target file matches.
    4. **Title-fallback**: if feature_name contains 'verifier' (case-insensitive)
       AND at least one behavior: AC references verification/AC/criterion
       semantics, return True.
    5. Otherwise return False.

    Args:
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.
                              Any other type raises ValueError.
        workspace:            Optional root directory for resolving 'File exists:'
                              paths. When None, step 3 is skipped.

    Returns:
        True when the feature should be deferred to the successor generation.
        False otherwise (including on parse failures or I/O errors).

    Raises:
        ValueError: When acceptance_criteria is not a list, str, or None.
    """
    ac_list = _parse_ac_list(acceptance_criteria)
    if ac_list is None:
        return False

    # Step 2: AC body scan across all ACs.
    for ac in ac_list:
        if _ac_body_has_verifier_token(ac):
            logger.debug(
                "pending_successor_verifier: path-token match in AC body %r",
                ac[:120],
            )
            return True

    # Step 3: Target-file scan — resolve 'File exists:' paths relative to workspace.
    if workspace is not None:
        ws = Path(workspace)
        for file_path in _extract_file_paths(ac_list):
            candidate = Path(file_path)
            if not candidate.is_absolute():
                candidate = ws / file_path
            if _scan_target_file(candidate):
                logger.debug(
                    "pending_successor_verifier: verifier token found in target file %s",
                    candidate,
                )
                return True

    # Step 4: Title-fallback.
    if "verifier" not in feature_name.lower():
        return False

    for ac in ac_list:
        if not _BEHAVIOR_AC_RE.match(ac):
            continue
        body = _BEHAVIOR_AC_RE.sub("", ac, count=1).lower()
        if any(kw in body for kw in _VERIFICATION_SEMANTICS_KEYWORDS):
            logger.debug(
                "pending_successor_verifier: title-fallback triggered for %r; AC: %r",
                feature_name[:80],
                ac[:80],
            )
            return True

    return False


def mark_pending_successor_verify(
    feature_id: str,
    feature_name: str = "",
    acceptance_criteria=None,
    workspace: str | os.PathLike[str] | None = None,
) -> bool:
    """Pre-dispatch gate: defer a feature to successor-gen if it targets the verifier (F-R7-596).

    Uses the broadened detector (AC body scan + target-file scan + title-fallback)
    to decide whether the feature modifies the verifier subsystem, then marks it
    'pending_successor_verify' in the DB so the current gen's verifier never runs
    against code it cannot yet check.

    Args:
        feature_id:           UUID of the feature to potentially defer.
        feature_name:         The feature's name/title string.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.
        workspace:            Optional root directory for resolving 'File exists:' paths.

    Returns:
        True when the feature was marked 'pending_successor_verify' (subagent dispatch
        should be skipped for this feature).
        False when the feature does not target the verifier subsystem, or on DB error.
    """
    if not detect_pending_successor_verify(feature_name, acceptance_criteria, workspace):
        return False

    from bob import db

    try:
        db.update_feature(feature_id, status="pending_successor_verify")
        logger.info(
            "mark_pending_successor_verify: feature %s deferred to successor gen "
            "(verifier-extension detected via broadened AC/title scan)",
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


__all__ = [
    "detect_pending_successor_verify",
    "mark_pending_successor_verify",
]
