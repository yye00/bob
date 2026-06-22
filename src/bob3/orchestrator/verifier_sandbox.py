"""Guard verifier modules from being modified by non-verifier features.

In Round 4, an implementation sub-agent edited ``enhanced_verification.py``
to soften the ``integration_code_exists`` check so its own feature would
pass. This module provides ``check_verifier_untouched``, which rejects any
diff that touches protected verifier modules unless the active feature is
tagged ``role=verifier``.

Protected modules
-----------------
- ``src/bob3/enhanced_verification.py``
- ``src/bob3/superpowers.py``
- Any file matching ``src/bob3/orchestrator/run_loop.py`` (the evaluator
  lives there) or ``evaluator`` in its path.

A feature is considered to have ``role=verifier`` when its name or
description contains the literal string ``role=verifier`` (case-insensitive)
or when the feature name contains ``verifier`` and the description signals
an infrastructure/guardrail purpose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Protected module paths (relative to workspace root, as they appear in diffs)
# ---------------------------------------------------------------------------

_PROTECTED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\benhanced_verification\.py\b"),
    re.compile(r"\bsuperpowers\.py\b"),
    # The evaluator lives inside run_loop.py; protect the whole file.
    re.compile(r"\brun_loop\.py\b"),
    # Catch hypothetical standalone evaluator files (e.g. evaluator_agent.py).
    re.compile(r"(?:^|/)evaluator[^/]*\.py$", re.IGNORECASE),
]

# Regex to detect the diff "--- a/..." / "+++ b/..." file header lines.
_DIFF_FILE_HEADER = re.compile(r"^(?:\+\+\+|---)\s+[ab]/(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SandboxViolation:
    """A protected module that a non-verifier feature attempted to modify."""

    path: str
    reason: str


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of ``check_verifier_untouched``."""

    allowed: bool
    violations: list[SandboxViolation]
    is_verifier_feature: bool

    @property
    def message(self) -> str:
        if self.allowed:
            return "OK"
        paths = ", ".join(v.path for v in self.violations)
        return (
            f"BLOCKED: diff touches protected verifier module(s) [{paths}] "
            "but the active feature is not tagged role=verifier. "
            "Add 'role=verifier' to the feature description to allow this."
        )


def _extract_touched_paths(diff: str) -> list[str]:
    """Return all file paths mentioned in the unified diff headers."""
    paths: list[str] = []
    for match in _DIFF_FILE_HEADER.finditer(diff):
        path = match.group(1).strip()
        # Skip /dev/null (new-file or deleted-file markers)
        if path != "/dev/null":
            paths.append(path)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _is_protected(path: str) -> bool:
    """Return True if *path* matches any of the protected module patterns."""
    # Normalise Windows-style separators
    normalised = path.replace("\\", "/")
    for pattern in _PROTECTED_PATTERNS:
        if pattern.search(normalised):
            return True
    return False


def _feature_is_verifier(feature_name: str, feature_description: str = "") -> bool:
    """Return True if the feature carries the ``role=verifier`` designation.

    The designation is present when:
    - The name or description contains the literal ``role=verifier``
      (case-insensitive), or
    - The name contains ``verifier_sandbox`` (the sandbox module itself is
      a verifier-infrastructure feature and must be allowed to touch the
      verifier files during its own bootstrap).
    """
    combined = f"{feature_name} {feature_description}".lower()
    if "role=verifier" in combined:
        return True
    # The verifier_sandbox feature itself is bootstrapping the guardrail —
    # let it pass without needing an explicit tag.
    if "verifier_sandbox" in combined or "verifier sandbox" in combined:
        return True
    # The canonical feature name used when spawning this very feature.
    if "sandbox the verifier" in combined:
        return True
    return False


def check_verifier_untouched(
    diff: str,
    feature_name: str,
    feature_description: str = "",
) -> SandboxResult:
    """Check that a diff does not touch protected verifier modules.

    Parameters
    ----------
    diff:
        Unified diff string produced by ``git diff`` or equivalent.
    feature_name:
        The name of the feature being implemented.
    feature_description:
        Optional free-text description of the feature (used to detect
        the ``role=verifier`` tag).

    Returns
    -------
    SandboxResult
        ``.allowed`` is ``True`` when the diff is safe to proceed.
        ``.allowed`` is ``False`` when a protected module is touched by
        a non-verifier feature — the caller should reject the commit.
    """
    is_verifier = _feature_is_verifier(feature_name, feature_description)

    touched_paths = _extract_touched_paths(diff)

    violations: list[SandboxViolation] = []
    for path in touched_paths:
        if _is_protected(path):
            violations.append(
                SandboxViolation(
                    path=path,
                    reason=(
                        f"'{path}' is a protected verifier module; "
                        "only features tagged role=verifier may modify it"
                    ),
                )
            )

    allowed = is_verifier or len(violations) == 0

    return SandboxResult(
        allowed=allowed,
        violations=violations if not allowed else [],
        is_verifier_feature=is_verifier,
    )
