"""Tests for bob3.spec_ambiguity_linter_reject_vague_acceptance_criteria.

Verifies the main entry-point function
spec_ambiguity_linter_reject_vague_acceptance_criteria that acts as a
pre-plan gate: scanning every acceptance_criteria entry and rejecting
ambiguous patterns, emitting a structured report.
"""

from __future__ import annotations

import pytest

from bob3.spec_ambiguity_linter_reject_vague_acceptance_criteria import (
    spec_ambiguity_linter_reject_vague_acceptance_criteria,
)


def test_spec_ambiguity_linter_reject_vague_acceptance_criteria():
    """Core acceptance test for the spec ambiguity linter entry point.

    Verifies:
    - Structured ACs pass (no rejection)
    - Vague ACs are rejected with a structured report
    - Report names the offending feature and AC index
    - Linter passes the plan when all ACs are structured
    - Linter fails the plan when any AC is ambiguous
    """
    # --- PASS: all features have structured ACs ---
    clean_features = [
        {
            "name": "Clean Feature",
            "acceptance_criteria": [
                "File exists: src/bob3/clean.py",
                "pytest: tests/test_clean.py",
                "Function defined: bob3.clean.my_func",
            ],
        },
        {
            "name": "Another Feature",
            "acceptance_criteria": [
                "integration: bob3.cli.plan",
                "Class defined: bob3.module.MyClass",
            ],
        },
    ]
    result = spec_ambiguity_linter_reject_vague_acceptance_criteria(clean_features)
    assert result["passed"] is True
    assert result["failed_features"] == []
    assert "PASSED" in result["report"]

    # --- FAIL: one feature has a vague AC ---
    vague_features = [
        {
            "name": "Vague Feature",
            "acceptance_criteria": [
                "File exists: src/bob3/vague.py",
                "The module works correctly",  # vague
            ],
        },
    ]
    result = spec_ambiguity_linter_reject_vague_acceptance_criteria(vague_features)
    assert result["passed"] is False
    assert len(result["failed_features"]) == 1
    assert result["failed_features"][0]["feature_name"] == "Vague Feature"
    assert "FAILED" in result["report"]
    assert "AC[1]" in result["report"]

    # --- FAIL: bare verb pattern rejected ---
    bare_verb_features = [
        {
            "name": "Bare Verb Feature",
            "acceptance_criteria": ["handles all cases correctly"],
        },
    ]
    result = spec_ambiguity_linter_reject_vague_acceptance_criteria(bare_verb_features)
    assert result["passed"] is False
    assert len(result["failed_features"]) == 1

    # --- PASS: empty spec has no failures ---
    result = spec_ambiguity_linter_reject_vague_acceptance_criteria([])
    assert result["passed"] is True
    assert result["failed_features"] == []

    # --- FAIL: multiple vague ACs all appear in report ---
    multi_vague_features = [
        {
            "name": "Multi Vague",
            "acceptance_criteria": [
                "works for any input",
                "supports everything",
                "pytest: tests/test_ok.py",  # valid AC in the middle
                "handles all cases",
            ],
        },
    ]
    result = spec_ambiguity_linter_reject_vague_acceptance_criteria(multi_vague_features)
    assert result["passed"] is False
    # Should have 3 issues (indices 0, 1, 3)
    feature_result = result["failed_features"][0]
    assert len(feature_result["issues"]) == 3
    ac_indices = [issue["ac_index"] for issue in feature_result["issues"]]
    assert 0 in ac_indices
    assert 1 in ac_indices
    assert 3 in ac_indices

    # --- Report includes AC indices for each failing AC ---
    assert "AC[0]" in result["report"]
    assert "AC[1]" in result["report"]
    assert "AC[3]" in result["report"]
