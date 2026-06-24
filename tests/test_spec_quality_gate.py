"""Tests for bob73.spec_quality_gate.is_permanent_forward_carry."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob73.spec_quality_gate import is_permanent_forward_carry, load_allowlist_patterns


def _make_feature(
    name: str = "Test Feature",
    spec_slot: str | None = None,
    permanent_forward_carry: bool = False,
) -> MagicMock:
    feature = MagicMock()
    feature.name = name
    feature.spec_slot = spec_slot
    feature.permanent_forward_carry = permanent_forward_carry
    return feature


def test_is_permanent_forward_carry_returns_true_for_f_r7_478():
    """F-R7-478 features must be exempt from the quality gate."""
    feature = _make_feature(name="unlimited spawn retry", spec_slot="F-R7-478")
    assert is_permanent_forward_carry(feature) is True


def test_is_permanent_forward_carry_returns_true_for_f_r7_479():
    """F-R7-479 features must be exempt from the quality gate."""
    feature = _make_feature(name="RCA-layer NH auto-reset", spec_slot="F-R7-479")
    assert is_permanent_forward_carry(feature) is True


def test_is_permanent_forward_carry_returns_true_for_f_r7_481():
    """F-R7-481 features must be exempt from the quality gate."""
    feature = _make_feature(name="slopsquatting local-module exclusion", spec_slot="F-R7-481")
    assert is_permanent_forward_carry(feature) is True


def test_is_permanent_forward_carry_returns_false_for_regular_feature():
    """A brand-new synthesized feature must NOT be exempt."""
    feature = _make_feature(
        name="Some brand new feature",
        spec_slot=None,
        permanent_forward_carry=False,
    )
    assert is_permanent_forward_carry(feature) is False


def test_is_permanent_forward_carry_returns_true_for_permanent_forward_carry_flag():
    """A feature with permanent_forward_carry=True is always exempt, regardless of slot."""
    feature = _make_feature(
        name="Any feature",
        spec_slot=None,
        permanent_forward_carry=True,
    )
    assert is_permanent_forward_carry(feature) is True


def test_is_permanent_forward_carry_slot_contains_pattern():
    """Feature is exempt when spec_slot contains an allowlisted pattern as substring."""
    feature = _make_feature(spec_slot="F-R7-478-unlimited-spawn-retry")
    assert is_permanent_forward_carry(feature) is True


def test_is_permanent_forward_carry_name_contains_pattern():
    """Feature is exempt when name contains an allowlisted pattern as substring."""
    feature = _make_feature(name="Implements F-R7-481 slopsquatting exclusion")
    assert is_permanent_forward_carry(feature) is True


def test_is_permanent_forward_carry_no_match_returns_false():
    """Feature with unrelated name and no flag must return False."""
    feature = _make_feature(
        name="Totally unrelated feature F-R7-999",
        spec_slot="F-R7-999",
        permanent_forward_carry=False,
    )
    assert is_permanent_forward_carry(feature) is False


def test_is_permanent_forward_carry_none_spec_slot_no_name_match():
    """Feature with None spec_slot and non-matching name returns False."""
    feature = _make_feature(name="unrelated feature", spec_slot=None)
    assert is_permanent_forward_carry(feature) is False


def test_is_permanent_forward_carry_returns_bool():
    """Return type must be bool, not truthy/falsy object."""
    feature = _make_feature(spec_slot="F-R7-478")
    result = is_permanent_forward_carry(feature)
    assert isinstance(result, bool)

    feature2 = _make_feature(spec_slot=None)
    result2 = is_permanent_forward_carry(feature2)
    assert isinstance(result2, bool)


def test_load_allowlist_patterns_returns_defaults():
    """Default patterns include the three canonical infra slots."""
    import os
    env_backup = os.environ.pop("BOB_ALLOWLIST_PATTERNS", None)
    try:
        patterns = load_allowlist_patterns()
        assert "F-R7-478" in patterns
        assert "F-R7-479" in patterns
        assert "F-R7-481" in patterns
    finally:
        if env_backup is not None:
            os.environ["BOB_ALLOWLIST_PATTERNS"] = env_backup


def test_load_allowlist_patterns_env_override(monkeypatch):
    """BOB_ALLOWLIST_PATTERNS env var overrides defaults."""
    monkeypatch.setenv("BOB_ALLOWLIST_PATTERNS", "F-R7-999,F-R7-888")
    patterns = load_allowlist_patterns()
    assert patterns == ["F-R7-999", "F-R7-888"]


def test_integration_bob_spec_synthesizer_importable():
    """bob.spec_synthesizer must be importable alongside bob73.spec_quality_gate."""
    import bob.spec_synthesizer  # noqa: F401
    assert callable(is_permanent_forward_carry)


def test_research_generated_acs_pass_validation():
    """ACs produced by the research_strategies generator must pass the spec_quality gate.

    This test closes the loop: research_strategies.emit_canonical_acs() produces
    ACs, and those ACs must individually pass validate_ac_canonical_form() and
    collectively pass validate_against_spec_quality_gate().  Without this test,
    a regression in the emitter could produce prose ACs that silently fail the
    gate at feature creation time.
    """
    from bob.research_strategies import (
        emit_canonical_acs,
        generate_with_ac_validation,
        validate_ac_canonical_form,
        validate_against_spec_quality_gate,
    )

    topic = "path_finding_retry_research_strategies"
    acs = emit_canonical_acs(topic)

    # Every individual AC must pass canonical-form validation
    for ac in acs:
        result = validate_ac_canonical_form(ac)
        assert result["passed"], (
            f"AC emitted by research_strategies failed canonical-form check: {ac!r}\n"
            f"Reason: {result['reason']}"
        )

    # The full AC list must pass the composite gate
    gate_result = validate_against_spec_quality_gate(acs)
    assert gate_result["passed"], (
        f"ACs from research_strategies failed composite gate: {gate_result['non_canonical']}"
    )

    # generate_with_ac_validation must also succeed end-to-end
    gen_result = generate_with_ac_validation(topic)
    assert gen_result["status"] == "ok", (
        f"generate_with_ac_validation blocked: {gen_result['non_canonical']}"
    )
    assert len(gen_result["acceptance_criteria"]) > 0
    assert gen_result["non_canonical"] == []


# Tests for check_quality_gate_with_allowlist (feature 0eca77ce)

from bob.spec_quality_gate import check_quality_gate_with_allowlist


def test_check_quality_gate_with_allowlist_regular_feature_above_threshold():
    """Regular feature with score >= threshold passes the gate."""
    feature = _make_feature(name="some new feature", permanent_forward_carry=False)
    assert check_quality_gate_with_allowlist(feature, quality_score=0.90) is True


def test_check_quality_gate_with_allowlist_regular_feature_below_threshold():
    """Regular feature with score < threshold fails the gate."""
    feature = _make_feature(name="some new feature", permanent_forward_carry=False)
    assert check_quality_gate_with_allowlist(feature, quality_score=0.70) is False


def test_check_quality_gate_with_allowlist_permanent_carry_bypasses_gate():
    """Permanent-carry feature bypasses the gate regardless of quality score."""
    feature = _make_feature(name="F-R7-478 retry infra", spec_slot="F-R7-478", permanent_forward_carry=False)
    assert check_quality_gate_with_allowlist(feature, quality_score=0.60) is True


def test_check_quality_gate_with_allowlist_flag_bypasses_gate():
    """Feature with permanent_forward_carry=True bypasses gate even with low score."""
    feature = _make_feature(name="any infra feature", permanent_forward_carry=True)
    assert check_quality_gate_with_allowlist(feature, quality_score=0.50) is True


def test_check_quality_gate_with_allowlist_none_raises():
    """None feature must raise ValueError."""
    with pytest.raises(ValueError, match="feature"):
        check_quality_gate_with_allowlist(None, quality_score=0.90)  # type: ignore[arg-type]


def test_check_quality_gate_with_allowlist_invalid_score_raises():
    """Score outside [0.0, 1.0] must raise ValueError."""
    feature = _make_feature()
    with pytest.raises(ValueError, match="quality_score"):
        check_quality_gate_with_allowlist(feature, quality_score=1.5)


def test_check_quality_gate_with_allowlist_at_threshold_passes():
    """Score exactly at threshold is accepted."""
    feature = _make_feature(permanent_forward_carry=False)
    assert check_quality_gate_with_allowlist(feature, quality_score=0.85) is True


def test_check_quality_gate_with_allowlist_custom_threshold():
    """Custom threshold is honored correctly."""
    feature = _make_feature(permanent_forward_carry=False)
    assert check_quality_gate_with_allowlist(feature, quality_score=0.70, threshold=0.65) is True
    assert check_quality_gate_with_allowlist(feature, quality_score=0.60, threshold=0.65) is False
