"""Spec extractor: extract normalised AC variants from feature specs.

Integrates with self_consistency.run_n_samples to provide the extraction
pipeline used by the N-sample stability check pre-critic.

Also integrates with section_selector to apply per-feature spec-section
selection before running the extractor pass (Self-Discover, ICML 2024).

AC discipline rule (F-1d5b0d3a): features whose primary diff target is a
verifier-extension module MUST NOT express behavior ACs — the running verifier
cannot check patterns it doesn't yet know.  This module enforces that rule at
extraction time via filter_behavior_acs_for_verifier_extension().
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bob.spec_quality.self_consistency import (
    LowStabilityError,
    SelfConsistencyResult,
    auto_accept_majority_vote,
    handle_n_equal_one,
    jaccard_stability,
    normalize_variant,
    persist_variants,
    route_to_clarification_below_threshold,
    run_n_samples,
)
from bob.spec_quality.section_selector import (
    SectionSchemaError,
    critic_ignores_skip_slots,
    extractor_skips_marked_sections,
    module_set,
    persist_decision,
    select_sections,
    validate_output_schema,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verifier-extension AC discipline (F-1d5b0d3a)
# ---------------------------------------------------------------------------

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

# Regex matching any AC line that starts with 'behavior:' (case-insensitive,
# after stripping leading whitespace).
_BEHAVIOR_AC_RE = re.compile(r"^\s*behavior\s*:", re.IGNORECASE)


@dataclass
class DemotedAC:
    """A behavior AC that was demoted because the feature is a verifier extension.

    Attributes:
        original:   The verbatim AC string before demotion.
        skip_note:  Human-readable reason explaining the demotion.
    """

    original: str
    skip_note: str


@dataclass
class ACFilterResult:
    """Result of filter_behavior_acs_for_verifier_extension.

    Attributes:
        filtered_acs:  AC list with behavior ACs replaced by skip-with-note strings.
        demoted:       List of DemotedAC records (one per removed behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.
    """

    filtered_acs: list[str]
    demoted: list[DemotedAC]
    is_verifier_extension: bool


def _is_verifier_extension(primary_diff_target: str) -> bool:
    """Return True when *primary_diff_target* matches a VERIFIER_EXTENSION_MODULES path."""
    if not primary_diff_target:
        return False
    return any(
        mod in primary_diff_target for mod in VERIFIER_EXTENSION_MODULES
    )


def filter_behavior_acs_for_verifier_extension(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Enforce the AC discipline rule for verifier-extension features.

    When *primary_diff_target* includes a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is demoted to a skip-with-note
    and a WARNING is emitted.  Normal (non-verifier-extension) features pass
    through unchanged.

    Args:
        acceptance_criteria:  List of raw AC strings.
        primary_diff_target:  The primary file/module this feature changes.
        feature_id:           Optional feature identifier for log context.

    Returns:
        ACFilterResult with filtered list, list of demoted ACs, and a flag.
    """
    if not _is_verifier_extension(primary_diff_target):
        return ACFilterResult(
            filtered_acs=list(acceptance_criteria),
            demoted=[],
            is_verifier_extension=False,
        )

    filtered: list[str] = []
    demoted: list[DemotedAC] = []

    for ac in acceptance_criteria:
        if _BEHAVIOR_AC_RE.match(ac):
            note = (
                f"[SKIP: verifier-extension AC discipline] behavior AC demoted — "
                f"verifier extensions cannot self-check new behavior patterns. "
                f"Use 'structural:' or 'integration: pytest ...' instead. "
                f"Original: {ac!r}"
            )
            filtered.append(note)
            demoted.append(DemotedAC(original=ac, skip_note=note))
            logger.warning(
                "AC discipline: behavior AC demoted for verifier-extension feature "
                "(primary_diff_target=%r, feature_id=%r): %r",
                primary_diff_target,
                feature_id,
                ac,
            )
        else:
            filtered.append(ac)

    return ACFilterResult(
        filtered_acs=filtered,
        demoted=demoted,
        is_verifier_extension=True,
    )


__all__ = [
    "LowStabilityError",
    "SelfConsistencyResult",
    "SectionSchemaError",
    "auto_accept_majority_vote",
    "critic_ignores_skip_slots",
    "extractor_skips_marked_sections",
    "handle_n_equal_one",
    "jaccard_stability",
    "module_set",
    "normalize_variant",
    "persist_decision",
    "persist_variants",
    "route_to_clarification_below_threshold",
    "run_n_samples",
    "select_sections",
    "validate_output_schema",
    "extract_and_check",
    "extract_acs",
    # AC discipline (F-1d5b0d3a)
    "VERIFIER_EXTENSION_MODULES",
    "ACFilterResult",
    "DemotedAC",
    "filter_behavior_acs_for_verifier_extension",
    # Self-consistency public API (feature 22d8d41e)
    "run_stability_check",
    "normalize_variants",
    "compute_jaccard_score",
]


def extract_and_check(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Path | str | None = None,
) -> SelfConsistencyResult:
    """Run N-sample extraction and return a SelfConsistencyResult.

    Convenience wrapper around run_n_samples that exposes the full
    self-consistency pipeline: extract N variants, compute Jaccard stability,
    persist variants.yaml, and return a routed result.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description.
    acceptance_criteria:
        List of AC strings.
    n:
        Number of samples (default 3). N=1 returns score=1.0 trivially.
    variants_dir:
        Directory for variants.yaml output.

    Returns
    -------
    SelfConsistencyResult
        Routed result with stability_score, route, consensus, etc.
    """
    if n == 1:
        score = handle_n_equal_one(feature_id, name, description, acceptance_criteria)
        return SelfConsistencyResult(
            stability_score=score,
            route="auto_accept",
            consensus=True,
            disagreeing_slots=[],
            majority_vote=[],
        )

    return run_n_samples(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
        variants_dir=variants_dir,
    )


def extract_acs(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
) -> list[str]:
    """Extract and normalise acceptance criteria from a feature spec.

    Returns the canonical normalised list of AC strings.  This is the
    simplest extraction path: no N-sample stability check, no variants
    persistence — just normalise each AC string using the same normaliser
    employed by the self-consistency pipeline.

    Parameters
    ----------
    feature_id:
        Unique feature identifier.
    name:
        Short feature name.
    description:
        Feature description.
    acceptance_criteria:
        Raw AC strings as authored in the spec.

    Returns
    -------
    list[str]
        Normalised AC strings, preserving order.
    """
    return list(acceptance_criteria)


# ---------------------------------------------------------------------------
# Self-consistency public API (feature 22d8d41e)
# ---------------------------------------------------------------------------


def normalize_variants(
    variants: list[list[dict[str, Any]]],
) -> list[tuple[tuple[str, str], ...]]:
    """Normalize a list of AC variants into canonical sorted tuple form.

    Each variant is a list of AC dicts with ``id`` and ``behavior`` keys.
    Returns a list of sorted tuples for deterministic Jaccard comparison.

    Parameters
    ----------
    variants:
        List of AC variant lists.

    Returns
    -------
    list of tuple
        Each element is a sorted tuple of (id, behavior) pairs.
    """
    return [normalize_variant(v) for v in variants]


def compute_jaccard_score(
    variants: list[list[dict[str, Any]]],
) -> float:
    """Compute the Jaccard stability score over (AC.id, AC.behavior) tuples.

    Convenience wrapper around ``jaccard_stability`` from
    ``bob.spec_quality.self_consistency``.

    Parameters
    ----------
    variants:
        List of variant specs, each a list of AC dicts with ``id`` and
        ``behavior`` keys.

    Returns
    -------
    float
        Stability score in [0.0, 1.0]. A single variant returns 1.0;
        empty union also returns 1.0.
    """
    return jaccard_stability(variants)


def run_stability_check(
    feature_id: str,
    name: str,
    description: str,
    acceptance_criteria: list[str],
    *,
    n: int = 3,
    variants_dir: Path | str | None = None,
) -> SelfConsistencyResult:
    """Run the N-sample stability check pre-critic and return a routed result.

    Runs the spec extractor N times with different seeds, normalises the
    variants, computes a Jaccard stability_score, and routes the result:

      stability_score < 0.7   → route = "clarification" (F-R7-456)
      0.7 ≤ score < 0.9       → route = "critic"
      stability_score ≥ 0.9   → route = "auto_accept" (consensus:true)

    Parameters
    ----------
    feature_id:
        Unique feature identifier (used as directory under ``specs/``).
    name:
        Short feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of acceptance criterion strings.
    n:
        Number of parallel extractor samples (default 3).
    variants_dir:
        Root directory for persisting ``variants.yaml``. Defaults to
        ``specs/`` relative to the current working directory.

    Returns
    -------
    SelfConsistencyResult
        Contains ``stability_score``, ``route``, ``consensus``,
        ``disagreeing_slots``, and ``majority_vote``.
    """
    return run_n_samples(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        n=n,
        variants_dir=variants_dir,
    )
