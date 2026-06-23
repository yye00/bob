"""Tests that the spec-critic revise loop is bounded (at most 1 revise pass).

The spec feature specifies: on non-empty critic output, the extractor runs one
revise pass; second-round defects escalate.  These tests verify that:
1. critique_feature is deterministic (same input → same defects)
2. A revised (fixed) spec returns fewer or zero defects
3. A spec that still has defects after revision does not recurse (the caller
   owns loop termination; the critic itself is stateless and bounded)
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.spec_critic import SpecDefect, critique_feature


def _run_revise_loop(
    feature_id: str,
    name: str,
    description: str,
    initial_acs: list[str],
    revised_acs: list[str],
    max_passes: int = 2,
) -> tuple[list[SpecDefect], list[SpecDefect], int]:
    """Simulate the bounded revise loop used by the orchestrator.

    Returns (first_round_defects, final_defects, passes_taken).
    """
    first_defects = critique_feature(
        feature_id=feature_id, name=name, description=description,
        acceptance_criteria=initial_acs,
    )
    if not first_defects or max_passes <= 1:
        return first_defects, first_defects, 1

    # One revise pass with revised ACs
    second_defects = critique_feature(
        feature_id=feature_id, name=name, description=description,
        acceptance_criteria=revised_acs,
    )
    return first_defects, second_defects, 2


class TestReviseLoopBounded:
    def test_clean_spec_needs_no_revise(self):
        """A spec with zero defects requires zero revise passes."""
        defects, _, passes = _run_revise_loop(
            feature_id="rl-001",
            name="Clean",
            description="d",
            initial_acs=[
                "File exists: src/clean.py",
                "pytest: tests/test_clean_error.py",
            ],
            revised_acs=[],  # never used
        )
        assert defects == []
        assert passes == 1

    def test_defective_spec_triggers_exactly_one_revise(self):
        """A spec with defects triggers exactly one revise pass."""
        initial_acs = ["The module works correctly"]
        revised_acs = [
            "File exists: src/module.py",
            "pytest: tests/test_module_error.py",
        ]
        first, final, passes = _run_revise_loop(
            feature_id="rl-002",
            name="Defective",
            description="d",
            initial_acs=initial_acs,
            revised_acs=revised_acs,
        )
        assert len(first) > 0
        assert passes == 2  # one revise pass triggered

    def test_revise_reduces_defects(self):
        """A revised spec has fewer defects than the original."""
        initial_acs = ["The module works correctly"]
        revised_acs = [
            "File exists: src/module.py",
            "pytest: tests/test_module_error.py",
        ]
        first, final, _ = _run_revise_loop(
            feature_id="rl-003",
            name="Revise reduces",
            description="d",
            initial_acs=initial_acs,
            revised_acs=revised_acs,
        )
        assert len(final) < len(first)

    def test_revise_can_clear_all_defects(self):
        """A well-revised spec returns zero defects in the second pass."""
        initial_acs = ["The module works correctly", "should handle edge cases"]
        revised_acs = [
            "File exists: src/module.py",
            "pytest: tests/test_module_invalid.py",
        ]
        _, final, _ = _run_revise_loop(
            feature_id="rl-004",
            name="Fully revised",
            description="d",
            initial_acs=initial_acs,
            revised_acs=revised_acs,
        )
        assert final == []

    def test_critic_is_stateless_and_deterministic(self):
        """Same input always produces the same output (critic is pure)."""
        acs = ["The module works correctly"]
        defects_a = critique_feature(
            feature_id="rl-005", name="N", description="d", acceptance_criteria=acs
        )
        defects_b = critique_feature(
            feature_id="rl-005", name="N", description="d", acceptance_criteria=acs
        )
        assert [d.to_dict() for d in defects_a] == [d.to_dict() for d in defects_b]

    def test_second_round_defects_still_present_when_revision_insufficient(self):
        """When the revise pass doesn't fix everything, second-round defects remain."""
        initial_acs = ["The module works correctly", "should handle edge cases"]
        partial_acs = [
            "File exists: src/module.py",
            "should handle edge cases",  # still vague
        ]
        first, final, passes = _run_revise_loop(
            feature_id="rl-006",
            name="Partial revise",
            description="d",
            initial_acs=initial_acs,
            revised_acs=partial_acs,
        )
        assert len(first) >= 2
        assert len(final) >= 1  # some defects remain (these would escalate)
        assert passes == 2

    def test_loop_terminates_after_max_passes(self):
        """The loop always terminates; even a permanently defective spec exits after 2 passes."""
        always_bad = ["The module works correctly"]
        first, final, passes = _run_revise_loop(
            feature_id="rl-007",
            name="Permanent defect",
            description="d",
            initial_acs=always_bad,
            revised_acs=always_bad,  # same bad spec
            max_passes=2,
        )
        assert passes == 2  # stopped at max
        assert len(final) > 0  # second-round defects would escalate

    def test_max_passes_one_skips_revise(self):
        """When max_passes=1 the loop never runs the revise pass."""
        initial_acs = ["The module works correctly"]
        _, final, passes = _run_revise_loop(
            feature_id="rl-008",
            name="Single pass",
            description="d",
            initial_acs=initial_acs,
            revised_acs=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
            max_passes=1,
        )
        assert passes == 1
        assert len(final) > 0  # no revise happened
