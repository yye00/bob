"""Broadened pending_successor_verify detection (F-R7-596).

Exposes ``detect_pending_successor_verify`` — a standalone detector that
combines the original F-R7-595 AC-body scan with F-R7-596's target-file scan
and title-fallback.

Public API
----------
detect_pending_successor_verify(feature_name, acceptance_criteria, workspace=None)
    Return True when the feature should be deferred to the successor generation.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# Keywords that appear in behavior: ACs of verifier-self-extension features.
_VERIFIER_KEYWORDS: tuple[str, ...] = (
    "enhanced_verification",
    "_check_",
    "_demote_",
    "verifier",
    "_verification",
)

# Path-tokens that signal a feature targets the verifier subsystem.
_VERIFIER_PATH_TOKENS: tuple[str, ...] = (
    "src/bob3/enhanced_verification.py",
    "enhanced_verification",
)

# Matches any path ending in _verification.py or _verifier.py
_VERIFIER_PATH_SUFFIX_RE = re.compile(r"_(?:verification|verifier)\.py\b")

# Matches behavior: AC prefix
_BEHAVIOR_AC_RE = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)

# Keywords in behavior: ACs indicating verification/AC/criterion semantics
_VERIFICATION_SEMANTICS_KEYWORDS: tuple[str, ...] = (
    "verif",
    "criterion",
    "accept",
    " ac ",
    "artifact",
    "refuse to pass",
    "missing",
)

# Extracts file path from "File exists: <path>"
_FILE_EXISTS_RE = re.compile(r"^\s*file\s+exists\s*:\s*(.+)", re.IGNORECASE)


def _parse_ac_list(acceptance_criteria) -> list[str] | None:
    """Parse acceptance_criteria into a list of strings.

    Raises ValueError for unsupported types. Returns [] for None.
    Returns None on JSON parse failure for str inputs.
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


def _ac_body_has_verifier_token(ac_body: str) -> bool:
    """Return True when ac_body contains a verifier path-token or keyword."""
    for token in _VERIFIER_PATH_TOKENS:
        if token in ac_body:
            return True
    if _VERIFIER_PATH_SUFFIX_RE.search(ac_body):
        return True
    return False


def _scan_target_file(file_path: Union[str, Path]) -> bool:
    """Return True when the file at file_path contains a verifier path-token."""
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return _ac_body_has_verifier_token(content)


def _extract_file_paths(ac_list: list[str]) -> list[str]:
    """Return file paths from 'File exists:' ACs."""
    paths = []
    for ac in ac_list:
        m = _FILE_EXISTS_RE.match(ac)
        if m:
            paths.append(m.group(1).strip())
    return paths


def detect_pending_successor_verify(
    feature_name: str = "",
    acceptance_criteria=None,
    workspace: Union[str, Path, None] = None,
) -> bool:
    """Return True when the feature should be deferred as a verifier-extension.

    Implements F-R7-596 broadened detection:

    1. Parse acceptance_criteria into a list of AC strings.
    2. AC body scan: if any AC body contains a verifier path-token, return True.
    3. Target-file scan: for each 'File exists:' AC, if workspace is given,
       resolve the path and scan the file contents for verifier path-tokens.
    4. Title-fallback: if feature_name contains 'verifier' (case-insensitive)
       AND any behavior: AC references verification/AC/criterion semantics,
       return True.

    Args:
        feature_name:         The feature title. Used for the title-fallback.
        acceptance_criteria:  A list of AC strings, a JSON-encoded list, or None.
                              Any other type raises ValueError.
        workspace:            Optional root directory for resolving 'File exists:'
                              paths during target-file scan. Skipped when None.

    Returns:
        True when the feature should be deferred. False otherwise.

    Raises:
        ValueError: When acceptance_criteria is not a list, str, or None.
    """
    ac_list = _parse_ac_list(acceptance_criteria)
    if ac_list is None:
        return False

    # Step 2: AC body scan
    for ac in ac_list:
        if _ac_body_has_verifier_token(ac):
            logger.debug(
                "pending_successor_verify_detector: path-token match in AC body %r",
                ac[:120],
            )
            return True

    # Step 3: Target-file scan
    if workspace is not None:
        ws = Path(workspace)
        for file_path in _extract_file_paths(ac_list):
            candidate = Path(file_path)
            if not candidate.is_absolute():
                candidate = ws / file_path
            if _scan_target_file(candidate):
                logger.debug(
                    "pending_successor_verify_detector: verifier token in target file %s",
                    candidate,
                )
                return True

    # Step 4: Title-fallback
    if "verifier" not in feature_name.lower():
        return False

    for ac in ac_list:
        if not _BEHAVIOR_AC_RE.match(ac):
            continue
        body = _BEHAVIOR_AC_RE.sub("", ac, count=1).lower()
        if any(kw in body for kw in _VERIFICATION_SEMANTICS_KEYWORDS):
            logger.debug(
                "pending_successor_verify_detector: title-fallback for %r; AC: %r",
                feature_name[:80],
                ac[:80],
            )
            return True

    return False


__all__ = ["detect_pending_successor_verify"]
