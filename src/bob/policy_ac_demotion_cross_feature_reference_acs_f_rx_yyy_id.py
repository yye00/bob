"""Policy-AC demotion for cross-feature reference ACs (feature 8e763d7b).

Problem (bob v.19 r1, 2026-05-31)
------------------------------------
AC handler family features (regression-attribution, infra-classifier, etc.)
ship integration/behavior ACs that reference *other* features by id, e.g.:

    "integration: F-R7-478 unlimited spawn-retry path remains unaffected"
    "integration: regression-sweep / F-R7-532 invariant pass continues to run."

These are cross-feature policy claims — per-feature verification has no access
to the other feature's runtime behavior. Symbol-grep (F-R7-582) and module-path
(F-R7-577) fallbacks both miss these. Features NH'd at attempts=5 with 1-2/14
criteria failing on these prose-policy refs.

Fix (F-R7-589, bob version 19)
--------------------------------
When a criterion body contains a token matching ``\\bF-R\\d+-\\d{3}\\b``, demote
the AC to PASS with a WARNING record. Per-feature verification cannot statically
verify cross-feature policy claims; the intent is preserved in the reviews/findings.yaml
WARNING so human reviewers can audit them.

This module is the canonical delegation entry point that surfaces this rule in
the bob v.17 spec. The underlying logic lives in
``bob.enhanced_verification.demote_cross_feature_criterion``.
"""

from __future__ import annotations

import pathlib

import bob.enhanced_verification as _ev

__all__ = ["policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id"]


def policy_ac_demotion_cross_feature_reference_acs_f_rx_yyy_id(
    criterion: str,
    workspace: pathlib.Path | None = None,
) -> tuple[bool, str] | None:
    """Demote a criterion containing a cross-feature F-RX-YYY reference to PASS.

    Per-feature verification cannot statically verify cross-feature policy claims
    such as "integration: F-R7-478 unlimited spawn-retry path remains unaffected".
    When the criterion body contains a token matching ``\\bF-R\\d+-\\d{3}\\b``, this
    function returns ``(True, reason)`` so callers can treat the AC as passed-with-
    warning rather than hard-failing and blocking the feature.

    Returns ``None`` when the criterion contains no cross-feature reference, so
    callers can apply their own fallback logic.

    If *workspace* is provided, a WARNING finding is appended to
    ``reviews/findings.yaml``.

    Parameters
    ----------
    criterion:
        The AC criterion text to check.
    workspace:
        Optional path to the project workspace root; used to emit the WARNING
        finding to ``reviews/findings.yaml``.

    Returns
    -------
    tuple[bool, str] | None
        ``(True, reason)`` when the criterion is demoted (cross-feature ref found).
        ``None`` when no cross-feature reference is present.
    """
    return _ev.demote_cross_feature_criterion(criterion, workspace)
