"""Tests for spec_quality_behavior_ac_parser_must_accept_canonical_clause.

AC: spec_quality behavior-AC parser MUST accept canonical clause forms beyond
strict "subject verb object when condition" — overly-tight regex blocks 70%+
of well-formed behavior ACs.

Verifies:
  - File exists: src/bob3/spec_quality_behavior_ac_parser_must_accept_canonical_clause.py
  - Function defined: bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause.spec_quality_behavior_ac_parser_must_accept_canonical_clause
  - The function accepts 'when' canonical form
  - The function accepts 'on <event>' synonym form (F-R7-556 trigger case)
  - The function accepts compound predicates with 'and'
  - The function rejects malformed ACs
"""

import pytest


# ---------------------------------------------------------------------------
# File / module existence
# ---------------------------------------------------------------------------

def test_module_importable():
    """Module must be importable from its AC-mandated path."""
    import bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause as m
    assert m is not None


def test_function_defined():
    """Function spec_quality_behavior_ac_parser_must_accept_canonical_clause must exist."""
    import bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause as m
    assert hasattr(m, "spec_quality_behavior_ac_parser_must_accept_canonical_clause")
    assert callable(m.spec_quality_behavior_ac_parser_must_accept_canonical_clause)


# This is the canonical test that the AC references:
def test_spec_quality_behavior_ac_parser_must_accept_canonical_clause():
    """Canonical entry-point: function accepts well-formed 'when' and 'on' forms."""
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause,
    )

    # Accepts canonical 'when' form
    result_when = spec_quality_behavior_ac_parser_must_accept_canonical_clause(
        "behavior: system logs error when disk is full"
    )
    assert result_when is not None
    assert result_when.get("accepted") is True
    assert result_when.get("conditional_keyword") == "when"

    # Accepts 'on' synonym — the exact F-R7-556 trigger case
    ac_on = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves "
        "the offending file to <path>.corrupt.<unix_ts> and returns an "
        "empty findings dict so boot proceeds"
    )
    result_on = spec_quality_behavior_ac_parser_must_accept_canonical_clause(ac_on)
    assert result_on is not None
    assert result_on.get("accepted") is True
    assert result_on.get("conditional_keyword") == "on"

    # Rejects a malformed AC (no conditional clause)
    result_bad = spec_quality_behavior_ac_parser_must_accept_canonical_clause(
        "behavior: system does something somewhere"
    )
    assert result_bad is not None
    assert result_bad.get("accepted") is False
    assert "error" in result_bad or "reason" in result_bad


# ---------------------------------------------------------------------------
# Canonical 'when' form
# ---------------------------------------------------------------------------

def test_when_form_accepted():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: runner emits DONE event when task completes")
    assert result["accepted"] is True
    assert result["conditional_keyword"] == "when"


def test_when_form_condition_populated():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: scheduler enqueues job when trigger fires")
    assert result["accepted"] is True
    assert "trigger fires" in result.get("condition", "")


# ---------------------------------------------------------------------------
# 'on <event>' synonym — F-R7-556 trigger case
# ---------------------------------------------------------------------------

def test_on_synonym_verbatim_f_r7_556():
    """The exact AC from F-R7-556 must be accepted."""
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError moves "
        "the offending file to <path>.corrupt.<unix_ts> and returns an "
        "empty findings dict so boot proceeds"
    )
    result = fn(ac)
    assert result["accepted"] is True
    assert result["conditional_keyword"] == "on"
    assert "yaml.scanner.ScannerError" in result.get("condition", "")


def test_on_synonym_dotted_exception():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: cache invalidated on redis.TimeoutError")
    assert result["accepted"] is True
    assert result["conditional_keyword"] == "on"


def test_on_synonym_single_word():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: loader on ValueError returns None")
    assert result["accepted"] is True
    assert result["conditional_keyword"] == "on"


def test_on_synonym_sigterm():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: handler on SIGTERM flushes buffer and exits")
    assert result["accepted"] is True
    assert result["conditional_keyword"] == "on"
    assert "SIGTERM" in result.get("condition", "")


# ---------------------------------------------------------------------------
# Compound predicates
# ---------------------------------------------------------------------------

def test_compound_predicate_when():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: loader reads config and sets defaults when startup begins")
    assert result["accepted"] is True
    assert result["conditional_keyword"] == "when"


def test_compound_predicate_on():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    ac = (
        "behavior: quarantine_corrupt_findings on yaml.scanner.ScannerError "
        "moves the offending file and returns an empty dict"
    )
    result = fn(ac)
    assert result["accepted"] is True
    assert result["conditional_keyword"] == "on"


# ---------------------------------------------------------------------------
# Rejection / error cases
# ---------------------------------------------------------------------------

def test_empty_string_rejected():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("")
    assert result["accepted"] is False


def test_missing_behavior_prefix_rejected():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("system logs error when disk is full")
    assert result["accepted"] is False


def test_no_conditional_clause_rejected():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: system logs error to disk")
    assert result["accepted"] is False


def test_rejected_result_has_error_or_reason():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    result = fn("behavior: system does something")
    assert result["accepted"] is False
    assert "error" in result or "reason" in result


# ---------------------------------------------------------------------------
# Raw string preservation
# ---------------------------------------------------------------------------

def test_raw_preserved_in_result():
    from bob3.spec_quality_behavior_ac_parser_must_accept_canonical_clause import (
        spec_quality_behavior_ac_parser_must_accept_canonical_clause as fn,
    )
    ac = "behavior: system retries the request when network error occurs"
    result = fn(ac)
    assert result["accepted"] is True
    assert result.get("raw") == ac
