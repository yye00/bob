"""bob3.explain_gate_block — operator-visibility subcommand for spec_quality_gate.

Surfaces why a feature failed the spec_quality_gate by re-running the scorer
and printing a sub-dimension breakdown with cheapest-fix remediation hints.

The canonical implementation of :func:`explain_gate_block` and
:func:`score_feature` lives in ``bob3.enhanced_verification``. This module
re-exports those functions under the ``bob3.explain_gate_block`` namespace so
that ACs of the form ``Function defined: bob3.explain_gate_block.<symbol>``
resolve correctly, and adds ``score_and_analyze_feature`` as an alias that
surfaces the same data.

CLI integration::

    bob3 explain-gate-block <feature_id_prefix>
    bob3 explain-gate-block --json <feature_id_prefix>

"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

from bob3.enhanced_verification import explain_gate_block, score_feature  # noqa: F401

__all__ = [
    "compute_cheapest_fixes",
    "compute_dimension_breakdown",
    "explain_feature_block",
    "explain_gate_block",
    "score_and_analyze_feature",
    "score_and_breakdown",
    "score_feature",
    "suggest_cheapest_fixes",
]

# Thresholds for each raw-count dimension (mirroring spec description)
_THRESHOLD_STRUCTURAL = 8
_THRESHOLD_EARS = 4
_THRESHOLD_INTEGRATION_KINDS = 3

_STRUCTURAL_PREFIXES = (
    "file exists:",
    "function defined:",
    "class defined:",
    "module exists:",
    "pytest:",
    "integration:",
    "behavior:",
    "log line:",
)

_INTEGRATION_PREFIXES = (
    "integration:",
    "pytest:",
)

# Pattern: own feature id token in AC body (e.g. F-R7-NNN or F-RX-NNN)
_OWN_ID_PATTERN = re.compile(r"\bF-R\w+-\d+\b", re.IGNORECASE)


def _parse_criteria(acceptance_criteria: list[str] | str) -> list[str]:
    if isinstance(acceptance_criteria, list):
        return [str(c) for c in acceptance_criteria]
    stripped = acceptance_criteria.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(c) for c in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
    return [line.strip() for line in stripped.splitlines() if line.strip()]


def compute_dimension_breakdown(
    feature_id: str,
    acceptance_criteria: list[str] | str,
) -> dict[str, Any]:
    """Compute raw-count sub-dimension breakdown for a feature's ACs.

    Analyses the acceptance criteria at a raw-count level (how many structural
    markers, EARS-form behaviours, integration target kinds, and whether the
    feature's own id token appears in its ACs).

    Parameters
    ----------
    feature_id:
        Feature UUID; used to detect own-id tokens in AC bodies.
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.

    Returns
    -------
    dict
        Keys:
        - ``structural_marker_count`` (int): number of ACs with a structural prefix
        - ``structural_marker_needed`` (int): threshold (8)
        - ``ears_behavior_count`` (int): number of EARS-form behaviour ACs
        - ``ears_behavior_needed`` (int): threshold (4)
        - ``integration_target_kinds`` (int): number of distinct integration target kinds
        - ``integration_target_kinds_needed`` (int): threshold (3)
        - ``own_id_token_absent`` (bool): True when no AC body contains the own id token
    """
    criteria = _parse_criteria(acceptance_criteria)

    structural_count = sum(
        1 for ac in criteria
        if ac.lower().startswith(_STRUCTURAL_PREFIXES)
    )

    # EARS-form: subject–verb–object–when pattern (heuristic: "when" or "shall" present)
    ears_count = sum(
        1 for ac in criteria
        if re.search(r"\bwhen\b|\bshall\b|\bif\b", ac, re.IGNORECASE)
        and not ac.lower().startswith(_STRUCTURAL_PREFIXES)
    )

    # Integration kinds: distinct prefixes among integration/pytest ACs
    integration_kinds: set[str] = set()
    for ac in criteria:
        lower = ac.lower()
        for prefix in _INTEGRATION_PREFIXES:
            if lower.startswith(prefix):
                integration_kinds.add(prefix.rstrip(":"))
        # Also count file-exists and function-defined as distinct kinds
        if lower.startswith("file exists:"):
            integration_kinds.add("file_exists")
        if lower.startswith("function defined:"):
            integration_kinds.add("function_defined")
        if lower.startswith("class defined:"):
            integration_kinds.add("class_defined")

    # Own-id token: feature_id prefix segment (e.g. "f23ffe3f" in "F-R?-???" is not
    # the token style; the spec description means literal "F-RX-NNN" tokens in AC text)
    own_id_found = any(_OWN_ID_PATTERN.search(ac) for ac in criteria)

    return {
        "structural_marker_count": structural_count,
        "structural_marker_needed": _THRESHOLD_STRUCTURAL,
        "ears_behavior_count": ears_count,
        "ears_behavior_needed": _THRESHOLD_EARS,
        "integration_target_kinds": len(integration_kinds),
        "integration_target_kinds_needed": _THRESHOLD_INTEGRATION_KINDS,
        "own_id_token_absent": not own_id_found,
    }


def suggest_cheapest_fixes(
    breakdown: dict[str, Any],
) -> list[str]:
    """Suggest the cheapest AC additions/removals to clear the spec_quality_gate.

    Takes the dict returned by :func:`compute_dimension_breakdown` and produces
    an ordered list of actionable fix suggestions, cheapest first.

    Parameters
    ----------
    breakdown:
        Dict as returned by :func:`compute_dimension_breakdown`.

    Returns
    -------
    list[str]
        Each entry is a short imperative suggestion string prefixed with ``+``
        (add) or ``-`` (remove).
    """
    suggestions: list[str] = []

    structural_gap = (
        breakdown.get("structural_marker_needed", _THRESHOLD_STRUCTURAL)
        - breakdown.get("structural_marker_count", 0)
    )
    if structural_gap > 0:
        suggestions.append(
            f"+ Add {structural_gap} structural ACs of form"
            " 'Function defined: <module.symbol>'"
        )

    ears_gap = (
        breakdown.get("ears_behavior_needed", _THRESHOLD_EARS)
        - breakdown.get("ears_behavior_count", 0)
    )
    if ears_gap > 0:
        suggestions.append(
            f"+ Add {ears_gap} EARS-form behavior ACs"
            " '<subj> <verb> <obj> when <cond>'"
        )

    kinds_gap = (
        breakdown.get("integration_target_kinds_needed", _THRESHOLD_INTEGRATION_KINDS)
        - breakdown.get("integration_target_kinds", 0)
    )
    if kinds_gap > 0:
        suggestions.append(
            f"+ Add {kinds_gap} integration ACs naming pytest test functions"
        )

    if not breakdown.get("own_id_token_absent", True):
        suggestions.append(
            "- Remove own-id token from existing structural ACs"
            " (cross-ref demotion will hollow these)"
        )

    return suggestions


def compute_cheapest_fixes(
    breakdown: dict[str, Any],
) -> list[str]:
    """Compute the cheapest AC additions/removals to clear the spec_quality_gate.

    Alias for :func:`suggest_cheapest_fixes` exposed under the name
    ``compute_cheapest_fixes`` so that the AC
    ``Function defined: bob3.explain_gate_block.compute_cheapest_fixes`` resolves.

    Parameters
    ----------
    breakdown:
        Dict as returned by :func:`compute_dimension_breakdown`.

    Returns
    -------
    list[str]
        Each entry is a short imperative suggestion string prefixed with ``+``
        (add) or ``-`` (remove).
    """
    return suggest_cheapest_fixes(breakdown)


def score_and_breakdown(
    feature_id: str,
    feature_name: str,
    description: str | None,
    acceptance_criteria: list[str] | str,
    workspace: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    """Re-run spec quality scoring and return a structured breakdown dict.

    Thin alias for :func:`explain_gate_block` exposed under the name
    ``score_and_breakdown`` so that the AC
    ``Function defined: bob3.explain_gate_block.score_and_breakdown`` resolves.

    Parameters
    ----------
    feature_id:
        Full or abbreviated feature UUID (passed through to the result).
    feature_name:
        Human-readable feature name.
    description:
        Feature description text (used for AC-coverage scoring).
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root for reachability checks. Defaults to ``Path.cwd()``.

    Returns
    -------
    dict
        Keys: ``feature_id``, ``feature_name``, ``score``, ``threshold``,
        ``components`` (dict of four sub-scores), ``remediation_hints`` (list).
    """
    return explain_gate_block(
        feature_id=feature_id,
        feature_name=feature_name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


def score_and_analyze_feature(
    feature_id: str,
    feature_name: str,
    description: str | None,
    acceptance_criteria: list[str] | str,
    workspace: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    """Re-run spec quality scoring and return a structured analysis dict.

    Equivalent to :func:`explain_gate_block` but named to reflect the
    analysis role more clearly.  Both functions produce identical output and
    can be used interchangeably.

    Parameters
    ----------
    feature_id:
        Full or abbreviated feature UUID (passed through to the result).
    feature_name:
        Human-readable feature name.
    description:
        Feature description text (used for AC-coverage scoring).
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root for reachability checks. Defaults to ``Path.cwd()``.

    Returns
    -------
    dict
        Keys: ``feature_id``, ``feature_name``, ``score``, ``threshold``,
        ``components`` (dict of four sub-scores), ``remediation_hints`` (list).
    """
    return explain_gate_block(
        feature_id=feature_id,
        feature_name=feature_name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )


def explain_feature_block(
    feature_id: str,
    feature_name: str,
    description: str | None,
    acceptance_criteria: list[str] | str,
    workspace: pathlib.Path | str | None = None,
) -> dict[str, Any]:
    """Re-run spec quality scoring and return a structured breakdown dict.

    Primary entry point for the ``bob3 explain-gate-block`` CLI subcommand.
    Equivalent to :func:`explain_gate_block`; exposed under this name so that
    the AC ``Function defined: bob3.explain_gate_block.explain_feature_block``
    resolves correctly.

    Parameters
    ----------
    feature_id:
        Full or abbreviated feature UUID.
    feature_name:
        Human-readable feature name.
    description:
        Feature description text (used for AC-coverage scoring).
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root for reachability checks. Defaults to ``Path.cwd()``.

    Returns
    -------
    dict
        Keys: ``feature_id``, ``feature_name``, ``score``, ``threshold``,
        ``components`` (dict of four sub-scores), ``remediation_hints`` (list).
    """
    return explain_gate_block(
        feature_id=feature_id,
        feature_name=feature_name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
