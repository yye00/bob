"""Bidirectional Requirements Traceability Matrix (RTM) artifact.

Forward (AC -> test -> code-region) and backward (code-region -> AC)
traceability as a first-class artifact. tools/spec_coverage.py emits
rtm.json and rtm.html. spec_coverage_pct halt-gate at 0.80. New functions
in a commit without an AC link are flagged untraced_implementation.
"""

from __future__ import annotations

import re
from typing import Any

_HALT_THRESHOLD = 0.80


def _test_references_ac(test_content: str, ac: dict[str, str]) -> bool:
    ac_id = ac.get("id", "")
    ac_text = ac.get("text", "")

    if ac_id and re.search(re.escape(ac_id), test_content):
        return True

    keyword_match = re.search(r"[\w.]+\.(\w+)|`(\w+)`|\b(\w{4,})\b", ac_text)
    if keyword_match:
        keyword = next(g for g in keyword_match.groups() if g)
        if re.search(re.escape(keyword), test_content, re.IGNORECASE):
            return True

    return False


def _function_is_traced(
    fn: dict[str, str],
    acs: list[dict[str, str]],
    test_contents: dict[str, str],
) -> bool:
    name = fn["function"]

    for ac in acs:
        if re.search(r"\b" + re.escape(name) + r"\b", ac.get("text", "")):
            return True

    for content in test_contents.values():
        if re.search(r"\b" + re.escape(name) + r"\b", content):
            return True

    return False


def bidirectional_requirements_traceability_matrix_rtm_artifact(
    *,
    workspace: str,
    feature_id: str,
    acs: list[dict[str, str]],
    test_contents: dict[str, str],
    src_functions: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a bidirectional RTM for a feature.

    Forward pass: for each AC, find test files that reference it.
    Backward pass: for each src function, check if any AC or test references it.

    Args:
        workspace: Project root (informational; not used for file I/O here).
        feature_id: Feature identifier string.
        acs: List of {id, text} dicts from spec.yaml acceptance_criteria.
        test_contents: Mapping of test file path -> file text content.
        src_functions: List of {function, file} dicts for public functions in src/.

    Returns:
        RTM dict with keys: feature_id, acs, spec_coverage_pct, untraced_implementations.
    """
    # Forward pass: AC -> tests
    forward: dict[str, dict[str, Any]] = {}
    for ac in acs:
        ac_id = ac.get("id") or ac.get("text", "")[:40]
        matched_tests: list[str] = []
        for tf_path, content in test_contents.items():
            if _test_references_ac(content, ac):
                matched_tests.append(tf_path)

        forward[ac_id] = {
            "text": ac.get("text", ""),
            "matched_tests": matched_tests,
            "exercised_files": list(set(matched_tests)),
            "orphan": len(matched_tests) == 0,
        }

    # Compute coverage
    total = len(acs)
    if total == 0:
        spec_coverage_pct = 0.0
    else:
        covered = sum(1 for info in forward.values() if not info["orphan"])
        spec_coverage_pct = covered / total

    # Backward pass: src function -> AC / test
    untraced = [
        fn for fn in src_functions
        if not _function_is_traced(fn, acs, test_contents)
    ]

    return {
        "feature_id": feature_id,
        "acs": forward,
        "spec_coverage_pct": spec_coverage_pct,
        "untraced_implementations": untraced,
    }


def check_halt_gate(rtm: dict[str, Any]) -> tuple[bool, str]:
    """Return (passed, reason). Fails when spec_coverage_pct < 0.80."""
    pct = rtm.get("spec_coverage_pct", 0.0)
    if pct >= _HALT_THRESHOLD:
        return True, ""
    reason = (
        f"spec_coverage_pct={pct:.2f} is below the halt-gate threshold of 0.80. "
        f"Cover more ACs with tests to proceed."
    )
    return False, reason
