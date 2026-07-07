"""Tests for bob.skip_ratio_gate (4d296524).

A coverage / pass-count / pass-rate gate is gameable: an attempt-pressured
builder mass-marks the HARD tests skip/xfail so the pass COUNT never regresses
while real coverage stalls. The skip-ratio gate closes that hole by:

  * emitting a companion skip-ratio-bound AC whenever a synthesized AC gates on
    a suite pass-count / pass-rate / coverage fraction, and
  * classifying every skip/xfail reason against a fixed taxonomy so that
    untagged skips fail the gate and deliberately-deferred OUT_OF_SCOPE tests
    do not count against the implementable-skip ratio.
"""
from __future__ import annotations

import pytest

from bob.skip_ratio_gate import (
    classify_skip_reason,
    counts_against_implementable_ratio,
    emit_skip_ratio_bound,
    gates_on_suite_metric,
    is_skip_ratio_bound_ac,
)


# ----------------------------- classify_skip_reason -----------------------------

def test_classify_not_yet_implemented():
    assert classify_skip_reason("NOT_YET_IMPLEMENTED") == "NOT_YET_IMPLEMENTED"


def test_classify_case_insensitive_and_freeform():
    assert classify_skip_reason("not yet implemented") == "NOT_YET_IMPLEMENTED"
    assert classify_skip_reason("test is flaky on CI") == "FLAKY"
    assert classify_skip_reason("out of scope for this milestone") == "OUT_OF_SCOPE"


def test_classify_untagged_for_blank_reason():
    """A blank reason is a well-defined UNTAGGED classification (not an exception)."""
    assert classify_skip_reason("") == "UNTAGGED"
    assert classify_skip_reason("   ") == "UNTAGGED"


def test_classify_untagged_for_unrecognized_reason():
    assert classify_skip_reason("because I said so") == "UNTAGGED"


def test_classify_out_of_scope_does_not_count_against_ratio():
    tag = classify_skip_reason("OUT_OF_SCOPE")
    assert counts_against_implementable_ratio(tag) is False


def test_classify_not_yet_implemented_counts_against_ratio():
    tag = classify_skip_reason("NOT_YET_IMPLEMENTED")
    assert counts_against_implementable_ratio(tag) is True


def test_untagged_counts_against_ratio_and_fails_gate():
    """An untagged skip must count against the ratio (it fails the gate)."""
    assert counts_against_implementable_ratio("UNTAGGED") is True


# ----------------------------- gates_on_suite_metric ----------------------------

def test_gates_on_suite_metric_true_for_pass_count():
    assert gates_on_suite_metric(
        "upstream test-suite pass count ratchets upward with no regressions"
    ) is True


def test_gates_on_suite_metric_true_for_coverage_fraction():
    assert gates_on_suite_metric("code coverage must be at least 90%") is True


def test_gates_on_suite_metric_true_for_pass_rate():
    assert gates_on_suite_metric("the suite pass rate must not decrease") is True


def test_gates_on_suite_metric_false_for_plain_ac():
    assert gates_on_suite_metric("File exists: src/bob/foo.py") is False


# ----------------------------- emit_skip_ratio_bound ----------------------------

def test_emit_appends_companion_when_gate_present():
    criteria = ["The upstream test-suite pass count must ratchet upward"]
    out = emit_skip_ratio_bound(criteria, title="GPU clone")
    assert len(out) == len(criteria) + 1
    assert any(is_skip_ratio_bound_ac(c) for c in out)


def test_emit_is_idempotent_when_bound_already_present():
    criteria = ["The suite pass rate must not regress"]
    once = emit_skip_ratio_bound(criteria, title="x")
    twice = emit_skip_ratio_bound(once, title="x")
    assert twice == once
    assert sum(1 for c in twice if is_skip_ratio_bound_ac(c)) == 1


def test_emit_no_change_when_no_gate():
    criteria = ["File exists: src/bob/foo.py", "Function defined: bob.foo.bar"]
    out = emit_skip_ratio_bound(criteria, title="foo")
    assert out == criteria


def test_emitted_bound_mentions_ratio_and_taxonomy():
    out = emit_skip_ratio_bound(["coverage must reach 80%"], title="foo")
    bound = next(c for c in out if is_skip_ratio_bound_ac(c))
    low = bound.lower()
    assert "skip" in low
    assert "ratio" in low


def test_emit_returns_new_list_not_mutating_input():
    criteria = ["the pass count must ratchet upward"]
    original = list(criteria)
    emit_skip_ratio_bound(criteria, title="foo")
    assert criteria == original
