"""Boundary tests for validate_coverage at exactly 0.90 minimum coverage."""

import pytest

from bob3.spec_quality.provenance import (
    ProvenanceRecord,
    Span,
    validate_coverage,
    _load_bearing_tokens,
)


def _make_intent_and_record_at_coverage(target_ratio: float) -> tuple[str, list[ProvenanceRecord]]:
    """Build an intent string and a ProvenanceRecord covering exactly *target_ratio* of its tokens.

    Returns (intent, records).

    Strategy: use a 10-token intent (all load-bearing, no stop words). Cover
    exactly round(10 * target_ratio) tokens by anchoring spans to those token
    offsets.
    """
    # 10 distinct load-bearing tokens separated by spaces
    words = ["alpha", "bravo", "charlie", "delta", "echo",
             "foxtrot", "golf", "hotel", "india", "juliet"]
    intent = " ".join(words)

    # Find token offsets
    offsets = sorted(_load_bearing_tokens(intent))
    n_total = len(offsets)
    n_covered = round(n_total * target_ratio)

    # Build spans covering the first n_covered tokens
    spans = []
    for off in offsets[:n_covered]:
        # Find the end of this word
        end = intent.index(" ", off) if " " in intent[off:] else len(intent)
        spans.append(Span(start=off, end=end))

    records = [ProvenanceRecord(ac="alpha bravo", spans=spans)]
    return intent, records


def test_validate_coverage_exactly_90_percent_passes():
    """validate_coverage returns True at exactly 0.90 boundary."""
    intent, records = _make_intent_and_record_at_coverage(0.90)
    passed, coverage, bad = validate_coverage(records, intent, min_coverage=0.90)
    # Verify coverage is at or above 0.90
    assert coverage >= 0.90, f"coverage {coverage:.4f} below expected 0.90"
    assert passed, f"Expected passed=True at coverage={coverage:.4f}, bad_indices={bad}"


def test_validate_coverage_just_below_90_fails():
    """Coverage strictly below 0.90 should fail (8/10 = 0.80)."""
    intent, records = _make_intent_and_record_at_coverage(0.80)
    passed, coverage, _ = validate_coverage(records, intent, min_coverage=0.90)
    assert coverage < 0.90, f"Expected coverage < 0.90, got {coverage:.4f}"
    assert not passed


def test_validate_coverage_100_percent_passes():
    """Full coverage always passes."""
    intent, records = _make_intent_and_record_at_coverage(1.0)
    passed, coverage, _ = validate_coverage(records, intent, min_coverage=0.90)
    assert passed
    assert coverage == 1.0


def test_validate_coverage_zero_percent_fails():
    """Zero coverage fails (no spans at all)."""
    words = ["alpha", "bravo", "charlie", "delta", "echo"]
    intent = " ".join(words)
    records = [ProvenanceRecord(ac="alpha bravo", spans=[])]
    passed, coverage, bad = validate_coverage(records, intent, min_coverage=0.90)
    assert not passed
    assert bad == [0]


def test_validate_coverage_custom_threshold_50_percent():
    """Custom min_coverage=0.50 accepts 50% coverage."""
    intent, records = _make_intent_and_record_at_coverage(0.50)
    passed, coverage, _ = validate_coverage(records, intent, min_coverage=0.50)
    assert coverage >= 0.50
    assert passed


def test_validate_coverage_default_threshold_is_90():
    """Default min_coverage is 0.90; 89% coverage should fail."""
    intent, records = _make_intent_and_record_at_coverage(0.80)
    passed, _, _ = validate_coverage(records, intent)
    assert not passed


def test_validate_coverage_exactly_90_single_sentence():
    """Sentence-level single-record test at the 0.90 boundary."""
    # 10 load-bearing tokens; 9 covered (90%)
    words = ["alpha", "bravo", "charlie", "delta", "echo",
             "foxtrot", "golf", "hotel", "india", "juliet"]
    intent = " ".join(words)
    offsets = sorted(_load_bearing_tokens(intent))
    # Cover first 9 of 10
    n_covered = 9
    spans = []
    for off in offsets[:n_covered]:
        end = intent.index(" ", off) if " " in intent[off:] else len(intent)
        spans.append(Span(start=off, end=end))
    records = [ProvenanceRecord(ac="alpha bravo", spans=spans)]
    passed, coverage, _ = validate_coverage(records, intent, min_coverage=0.90)
    assert coverage >= 0.90
    assert passed
