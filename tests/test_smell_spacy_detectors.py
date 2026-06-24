"""Tests for spaCy-dependent smell detectors.

The 7 spaCy detectors (S01, S02, S05, S06, S07, S08, S18) all fall back
to regex heuristics when spaCy is unavailable. These tests verify that the
regex fallback produces correct findings in both environments.

All tests MUST pass without spaCy installed (the CI environment
does not have spaCy). When spaCy IS present, the same patterns must
still be detected.
"""

from __future__ import annotations

import pytest

from bob.spec_quality.smell_catalog import SPACY_SMELLS
from bob.spec_quality.smell_detectors import SmellFinding, detect_all, severity_of


# ---------------------------------------------------------------------------
# S01 – subjective adjectives
# ---------------------------------------------------------------------------

class TestS01SubjectiveAdjective:
    def test_fast_detected(self):
        findings = detect_all("The system shall provide a fast response.")
        assert any(f.smell_id == "S01" for f in findings)

    def test_simple_detected(self):
        findings = detect_all("The interface shall be simple and intuitive.")
        assert any(f.smell_id == "S01" for f in findings)

    def test_reliable_detected(self):
        findings = detect_all("The service shall be reliable.")
        assert any(f.smell_id == "S01" for f in findings)

    def test_s01_finding_has_adjective_in_detail(self):
        findings = detect_all("The system shall be clean.")
        s01 = [f for f in findings if f.smell_id == "S01"]
        assert len(s01) > 0
        assert "clean" in s01[0].detail.lower()

    def test_s01_is_error_severity(self):
        assert severity_of("S01") == "E"

    def test_no_s01_in_clear_criterion(self):
        # No subjective adjectives in this criterion
        findings = detect_all("The login endpoint shall return HTTP 200 within 200ms.")
        assert not any(f.smell_id == "S01" for f in findings)

    def test_multiple_adjectives_create_findings(self):
        findings = detect_all("The system shall be fast, clean, and nice.")
        s01_findings = [f for f in findings if f.smell_id == "S01"]
        assert len(s01_findings) >= 2  # at least 'fast', 'clean', 'nice'


# ---------------------------------------------------------------------------
# S02 – ambiguous adverbs
# ---------------------------------------------------------------------------

class TestS02AmbiguousAdverb:
    def test_quickly_detected(self):
        findings = detect_all("The system shall process requests quickly.")
        assert any(f.smell_id == "S02" for f in findings)

    def test_efficiently_detected(self):
        findings = detect_all("The system shall handle requests efficiently.")
        assert any(f.smell_id == "S02" for f in findings)

    def test_appropriately_detected(self):
        findings = detect_all("The system shall respond appropriately.")
        assert any(f.smell_id == "S02" for f in findings)

    def test_s02_is_warning_severity(self):
        assert severity_of("S02") == "W"

    def test_no_s02_in_precise_criterion(self):
        findings = detect_all("The system shall respond within 500ms.")
        assert not any(f.smell_id == "S02" for f in findings)


# ---------------------------------------------------------------------------
# S05 – unbounded superlatives
# ---------------------------------------------------------------------------

class TestS05UnboundedSuperlative:
    def test_best_detected(self):
        findings = detect_all("The system shall provide the best user experience.")
        assert any(f.smell_id == "S05" for f in findings)

    def test_optimal_detected(self):
        findings = detect_all("The algorithm shall produce optimal results.")
        assert any(f.smell_id == "S05" for f in findings)

    def test_fastest_detected(self):
        findings = detect_all("The system shall use the fastest algorithm.")
        assert any(f.smell_id == "S05" for f in findings)

    def test_s05_is_error_severity(self):
        assert severity_of("S05") == "E"

    def test_superlative_with_number_no_finding(self):
        # "highest" followed by a number is allowed
        findings = detect_all("Cache hit rate shall be highest at 95% threshold.")
        # The number context exempts it — no S05 finding expected
        s05 = [f for f in findings if f.smell_id == "S05"]
        assert len(s05) == 0


# ---------------------------------------------------------------------------
# S06 – comparatives without baseline
# ---------------------------------------------------------------------------

class TestS06ComparativeWithoutBaseline:
    def test_better_detected(self):
        findings = detect_all("The new algorithm shall produce better results.")
        assert any(f.smell_id == "S06" for f in findings)

    def test_more_reliable_detected(self):
        findings = detect_all("The service shall be more reliable than before.")
        s06 = [f for f in findings if f.smell_id == "S06"]
        # "before" is not a number context — should flag
        assert len(s06) > 0

    def test_s06_is_warning_severity(self):
        assert severity_of("S06") == "S06" or severity_of("S06") == "W"

    def test_comparative_with_number_no_finding(self):
        # "more than 100" has a number → no S06
        findings = detect_all("The queue shall handle more than 1000 messages per second.")
        s06 = [f for f in findings if f.smell_id == "S06"]
        assert len(s06) == 0


# ---------------------------------------------------------------------------
# S07 – vague pronouns
# ---------------------------------------------------------------------------

class TestS07VaguePronoun:
    def test_it_at_clause_start_detected(self):
        findings = detect_all("The file shall be saved. It shall be readable.")
        assert any(f.smell_id == "S07" for f in findings)

    def test_they_at_clause_start_detected(self):
        findings = detect_all("Users log in. They shall see the dashboard.")
        s07 = [f for f in findings if f.smell_id == "S07"]
        assert len(s07) > 0

    def test_s07_is_warning_severity(self):
        assert severity_of("S07") == "W"

    def test_pronoun_mid_sentence_not_necessarily_flagged(self):
        # Pronoun in middle of a clause not at start — may not trigger
        # Just ensure no crash
        findings = detect_all("The system shall validate it before saving.")
        assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# S08 – passive without agent
# ---------------------------------------------------------------------------

class TestS08PassiveWithoutAgent:
    def test_shall_be_verified_detected(self):
        findings = detect_all("The data shall be verified before storage.")
        assert any(f.smell_id == "S08" for f in findings)

    def test_will_be_processed_detected(self):
        findings = detect_all("The request will be processed within 1 second.")
        s08 = [f for f in findings if f.smell_id == "S08"]
        assert len(s08) > 0

    def test_passive_with_by_agent_not_flagged(self):
        findings = detect_all("The report shall be generated by the scheduler.")
        # "by the scheduler" specifies the agent → no S08
        assert not any(f.smell_id == "S08" for f in findings)

    def test_s08_is_warning_severity(self):
        assert severity_of("S08") == "W"


# ---------------------------------------------------------------------------
# S18 – untestable adjectives
# ---------------------------------------------------------------------------

class TestS18UntestableAdjective:
    def test_complete_detected(self):
        findings = detect_all("The documentation shall be complete.")
        assert any(f.smell_id == "S18" for f in findings)

    def test_comprehensive_detected(self):
        findings = detect_all("The test suite shall be comprehensive.")
        assert any(f.smell_id == "S18" for f in findings)

    def test_adequate_detected(self):
        findings = detect_all("The coverage shall be adequate.")
        assert any(f.smell_id == "S18" for f in findings)

    def test_s18_is_error_severity(self):
        assert severity_of("S18") == "E"

    def test_no_s18_in_precise_criterion(self):
        findings = detect_all("The test suite shall achieve 80% branch coverage.")
        assert not any(f.smell_id == "S18" for f in findings)


# ---------------------------------------------------------------------------
# spaCy smell set membership
# ---------------------------------------------------------------------------

class TestSpacySmellMembership:
    def test_s01_s02_s05_s06_s07_s08_s18_in_spacy_set(self):
        expected = {"S01", "S02", "S05", "S06", "S07", "S08", "S18"}
        assert expected == SPACY_SMELLS

    def test_spacy_smells_all_return_findings_for_known_inputs(self):
        """Each spaCy smell should detect at least one known trigger."""
        triggers = {
            "S01": "The system shall be fast.",
            "S02": "The system shall respond quickly.",
            "S05": "The system shall use the best algorithm.",
            "S06": "The system shall perform better than before.",
            "S07": "Data is logged. It shall be encrypted.",
            "S08": "The form shall be validated before submission.",
            "S18": "The documentation shall be complete.",
        }
        for sid, text in triggers.items():
            findings = detect_all(text)
            ids = {f.smell_id for f in findings}
            assert sid in ids, f"Expected {sid} for text: {text!r}, got: {ids}"


# ---------------------------------------------------------------------------
# Regression: no crash when spaCy unavailable
# ---------------------------------------------------------------------------

class TestSpacyFallbackNoCrash:
    """Verify that regex fallback functions produce valid output without spaCy."""

    def test_detect_all_no_crash_on_complex_text(self):
        text = (
            "The system shall be fast, simple, and intuitive. "
            "Results will be displayed efficiently and appropriately. "
            "It shall handle all cases, including the best and optimal scenarios."
        )
        findings = detect_all(text)
        assert isinstance(findings, list)
        assert all(isinstance(f, SmellFinding) for f in findings)

    def test_spacy_detectors_return_correct_finding_type(self):
        findings = detect_all("The response shall be fast and comprehensive.")
        for f in findings:
            assert hasattr(f, "smell_id")
            assert hasattr(f, "smell_name")
            assert hasattr(f, "severity")
            assert hasattr(f, "detail")
            assert hasattr(f, "blocks_plan")

    def test_all_22_detectors_run_without_error(self):
        # A text that might trigger many smells
        text = (
            "The system should be simple and fast. "
            "It will be processed appropriately if possible. "
            "All cases shall be handled, including etc. "
            "The best performance is required within 500 ms. "
            "See F-R7-999 for reference."
        )
        findings = detect_all(
            text,
            peer_criteria=["File exists: src/foo.py"],
            known_feature_ids=frozenset(["F-R7-410"]),
        )
        assert isinstance(findings, list)
        # Should have multiple findings from various detectors
        assert len(findings) > 3
