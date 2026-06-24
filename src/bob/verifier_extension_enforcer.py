"""Verifier-extension AC discipline enforcer.

Enforces the rule that features whose primary diff target is a verifier-extension
module MUST NOT carry behavior ACs. This module exposes the canonical function
names required by the AC discipline rule feature (ee12ff06-c0a1-4faa-9fd9-5637f93e010c).

The running verifier cannot check patterns it doesn't yet know, so all ACs for
verifier-extension features MUST be either:
  - structural ("file X contains regex/literal Y")
  - integration pytest ("pytest tests/test_X.py::test_Y passes")
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Canonical list of module paths that, when listed as a feature's primary diff
# target, mark that feature as extending the verifier itself.
VERIFIER_EXTENSION_MODULES: tuple[str, ...] = (
    "src/bob/enhanced_verification.py",
    "src/bob/verification/verifier.py",
    "src/bob/verification/prose_ac_demotion.py",
    "src/bob/verification/integration_ac_resolver.py",
    "src/bob/verification/ac_artifact_check.py",
    "src/bob/verification/class_defined_ac_check.py",
    "src/bob/verification/mutation_gate.py",
    "src/bob/verification/per_feature_test_scope.py",
    "src/bob/verification/regression_attribution.py",
)

_BEHAVIOR_AC_RE = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)


def is_verifier_extension_module(primary_diff_target: str) -> bool:
    """Return True when primary_diff_target matches a VERIFIER_EXTENSION_MODULES path.

    Parameters
    ----------
    primary_diff_target:
        The primary file/module a feature changes.

    Returns
    -------
    bool
        True if the target is a known verifier-extension module path.
    """
    if not primary_diff_target:
        return False
    return any(mod in primary_diff_target for mod in VERIFIER_EXTENSION_MODULES)


def reject_behavior_ac(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> dict[str, object]:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    When primary_diff_target resolves to a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier used in log messages for context.

    Returns
    -------
    dict with keys:
        filtered_acs: list[str] — AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list[dict] — one record per rejected behavior AC.
        is_verifier_extension: bool — True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If acceptance_criteria is not a list (invalid input type).
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    if not is_verifier_extension_module(primary_diff_target):
        return {
            "filtered_acs": list(acceptance_criteria),
            "demoted": [],
            "is_verifier_extension": False,
        }

    filtered: list[str] = []
    demoted: list[dict[str, str]] = []

    for ac in acceptance_criteria:
        if _BEHAVIOR_AC_RE.match(ac):
            note = (
                f"[SKIP: verifier-extension AC discipline] behavior AC rejected — "
                f"verifier extensions cannot self-check new behavior patterns. "
                f"Use 'structural:' or 'integration: pytest ...' instead. "
                f"Original: {ac!r}"
            )
            filtered.append(note)
            demoted.append({"original": ac, "skip_note": note})
            logger.warning(
                "AC discipline: behavior AC rejected for verifier-extension feature "
                "(primary_diff_target=%r, feature_id=%r): %r",
                primary_diff_target,
                feature_id,
                ac,
            )
        else:
            filtered.append(ac)

    return {
        "filtered_acs": filtered,
        "demoted": demoted,
        "is_verifier_extension": True,
    }


__all__ = [
    "is_verifier_extension_module",
    "reject_behavior_ac",
    "VERIFIER_EXTENSION_MODULES",
]
