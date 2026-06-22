"""Tests for src/bob3/hardcoded_reference_value_detector.py (feature efd53845).

Verifies the hardcoded-reference-value detector:
- Flags float literals that match known benchmark reference values
- Returns clean when no matching floats are found
- Integrates with reward_hacking_detector (augments HackingVerdict)
- Public API is importable from bob3.hardcoded_reference_value_detector
"""

from __future__ import annotations

import textwrap

import pytest

from bob3.hardcoded_reference_value_detector import (
    ReferenceValueDatabase,
    ReferenceValueFinding,
    ReferenceValueResult,
    augment_hacking_verdict,
    check_hardcoded_reference_values,
    scan_source,
)
from bob3.reward_hacking_detector import AttackVectorScore, HackingVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _src(code: str) -> str:
    return textwrap.dedent(code).strip()


# ---------------------------------------------------------------------------
# ReferenceValueDatabase
# ---------------------------------------------------------------------------

class TestReferenceValueDatabase:
    def test_default_entries_present(self):
        db = ReferenceValueDatabase.default()
        entries = db.list_entries()
        assert len(entries) > 0

    def test_default_contains_nanogpt_perplexity(self):
        db = ReferenceValueDatabase.default()
        # nanoGPT GPT-2 small perplexity is 24.5 — always in default DB
        values = [e.value for e in db.list_entries()]
        assert 24.5 in values

    def test_add_and_retrieve_entry(self):
        db = ReferenceValueDatabase()
        db.add_entry(value=42.0, benchmark="my_bench", description="test entry")
        entries = db.list_entries()
        assert len(entries) == 1
        assert entries[0].value == 42.0
        assert entries[0].benchmark == "my_bench"

    def test_from_dict(self):
        db = ReferenceValueDatabase.from_dict({"some_bench": [1.23, 4.56]})
        values = [e.value for e in db.list_entries()]
        assert 1.23 in values
        assert 4.56 in values

    def test_empty_database(self):
        db = ReferenceValueDatabase()
        assert db.list_entries() == []

    def test_tolerance_lookup(self):
        db = ReferenceValueDatabase()
        db.add_entry(value=24.5, benchmark="nanogpt", description="GPT-2 small perplexity")
        matches = db.lookup(24.5)
        assert len(matches) == 1
        assert matches[0].value == 24.5

    def test_tolerance_lookup_near_value(self):
        db = ReferenceValueDatabase()
        db.add_entry(value=24.5, benchmark="nanogpt", description="GPT-2 small perplexity")
        # Default tolerance should allow very close values
        matches = db.lookup(24.500001)
        assert len(matches) == 1

    def test_tolerance_lookup_far_value(self):
        db = ReferenceValueDatabase()
        db.add_entry(value=24.5, benchmark="nanogpt", description="GPT-2 small perplexity")
        matches = db.lookup(25.0)
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# scan_source: extract float literals from source
# ---------------------------------------------------------------------------

class TestScanSource:
    def test_finds_float_literal(self):
        src = _src("""
            x = 24.5
        """)
        findings = scan_source(src, ReferenceValueDatabase.default())
        assert len(findings) == 1
        assert findings[0].value == 24.5
        assert "nanogpt" in findings[0].benchmark.lower() or findings[0].benchmark != ""

    def test_no_match_returns_empty(self):
        src = _src("""
            x = 99.99
        """)
        findings = scan_source(src, ReferenceValueDatabase.default())
        assert findings == []

    def test_finds_multiple_matches(self):
        db = ReferenceValueDatabase()
        db.add_entry(value=1.0, benchmark="bench_a", description="A")
        db.add_entry(value=2.0, benchmark="bench_b", description="B")
        src = _src("""
            a = 1.0
            b = 2.0
        """)
        findings = scan_source(src, db)
        values = [f.value for f in findings]
        assert 1.0 in values
        assert 2.0 in values

    def test_syntax_error_returns_empty(self):
        findings = scan_source("def foo(:", ReferenceValueDatabase.default())
        assert findings == []

    def test_integer_literal_not_flagged(self):
        src = "x = 24"
        findings = scan_source(src, ReferenceValueDatabase.default())
        # 24 as int should not match 24.5
        assert all(f.value != 24 for f in findings)

    def test_finding_includes_line_number(self):
        src = _src("""
            x = 1
            y = 24.5
        """)
        findings = scan_source(src, ReferenceValueDatabase.default())
        assert len(findings) == 1
        assert findings[0].line_number >= 1

    def test_finding_includes_context(self):
        src = "result = 24.5"
        findings = scan_source(src, ReferenceValueDatabase.default())
        assert len(findings) == 1
        assert findings[0].source_snippet != ""


# ---------------------------------------------------------------------------
# check_hardcoded_reference_values
# ---------------------------------------------------------------------------

class TestCheckHardcodedReferenceValues:
    def test_flagged_when_match_found(self):
        src = "loss = 24.5"
        db = ReferenceValueDatabase.default()
        result = check_hardcoded_reference_values(src, db=db)
        assert result.is_flagged is True
        assert len(result.findings) >= 1

    def test_clean_when_no_match(self):
        src = "loss = 99.99"
        db = ReferenceValueDatabase.default()
        result = check_hardcoded_reference_values(src, db=db)
        assert result.is_flagged is False
        assert result.findings == []

    def test_result_has_score(self):
        src = "loss = 24.5"
        db = ReferenceValueDatabase.default()
        result = check_hardcoded_reference_values(src, db=db)
        assert 0.0 <= result.score <= 1.0

    def test_clean_result_has_zero_score(self):
        src = "loss = 99.99"
        db = ReferenceValueDatabase.default()
        result = check_hardcoded_reference_values(src, db=db)
        assert result.score == 0.0

    def test_syntax_error_returns_clean(self):
        result = check_hardcoded_reference_values("def bad(:", ReferenceValueDatabase.default())
        assert result.is_flagged is False

    def test_empty_db_returns_clean(self):
        src = "loss = 24.5"
        db = ReferenceValueDatabase()
        result = check_hardcoded_reference_values(src, db=db)
        assert result.is_flagged is False

    def test_multiple_findings_increase_score(self):
        db = ReferenceValueDatabase()
        db.add_entry(value=1.0, benchmark="a", description="A")
        db.add_entry(value=2.0, benchmark="b", description="B")
        src = "x = 1.0\ny = 2.0"
        result = check_hardcoded_reference_values(src, db=db)
        assert result.is_flagged is True
        assert result.score > 0.0


# ---------------------------------------------------------------------------
# augment_hacking_verdict
# ---------------------------------------------------------------------------

class TestAugmentHackingVerdict:
    def _clean_verdict(self) -> HackingVerdict:
        return HackingVerdict(
            verdict="clean",
            overall_score=0.1,
            attack_vectors=[],
            reasoning="looks fine",
            confidence=0.9,
        )

    def test_adds_attack_vector(self):
        verdict = self._clean_verdict()
        src = "loss = 24.5"
        db = ReferenceValueDatabase.default()
        new_verdict = augment_hacking_verdict(verdict, source=src, db=db)
        vectors = [av.vector for av in new_verdict.attack_vectors]
        assert "hardcoded_reference_value" in vectors

    def test_escalates_verdict_when_flagged(self):
        verdict = self._clean_verdict()
        src = "loss = 24.5"
        db = ReferenceValueDatabase.default()
        new_verdict = augment_hacking_verdict(verdict, source=src, db=db)
        assert new_verdict.verdict in ("suspicious", "hacking")

    def test_does_not_downgrade_existing_hacking_verdict(self):
        verdict = HackingVerdict(
            verdict="hacking",
            overall_score=0.9,
            attack_vectors=[],
            reasoning="already bad",
            confidence=0.95,
        )
        src = "loss = 99.99"
        db = ReferenceValueDatabase.default()
        new_verdict = augment_hacking_verdict(verdict, source=src, db=db)
        assert new_verdict.verdict == "hacking"

    def test_clean_source_preserves_verdict(self):
        verdict = self._clean_verdict()
        src = "loss = 99.99"
        db = ReferenceValueDatabase.default()
        new_verdict = augment_hacking_verdict(verdict, source=src, db=db)
        assert new_verdict.verdict == "clean"

    def test_attack_vector_score_in_range(self):
        verdict = self._clean_verdict()
        src = "loss = 24.5"
        db = ReferenceValueDatabase.default()
        new_verdict = augment_hacking_verdict(verdict, source=src, db=db)
        av = next(v for v in new_verdict.attack_vectors if v.vector == "hardcoded_reference_value")
        assert 0.0 <= av.score <= 1.0

    def test_does_not_mutate_original_verdict(self):
        verdict = self._clean_verdict()
        original_verdict_str = verdict.verdict
        src = "loss = 24.5"
        db = ReferenceValueDatabase.default()
        augment_hacking_verdict(verdict, source=src, db=db)
        assert verdict.verdict == original_verdict_str


# ---------------------------------------------------------------------------
# Data model: ReferenceValueFinding
# ---------------------------------------------------------------------------

class TestReferenceValueFinding:
    def test_dataclass_fields(self):
        finding = ReferenceValueFinding(
            value=24.5,
            benchmark="nanogpt",
            description="GPT-2 small perplexity",
            line_number=3,
            source_snippet="loss = 24.5",
        )
        assert finding.value == 24.5
        assert finding.benchmark == "nanogpt"
        assert finding.line_number == 3
        assert finding.source_snippet == "loss = 24.5"


# ---------------------------------------------------------------------------
# Data model: ReferenceValueResult
# ---------------------------------------------------------------------------

class TestReferenceValueResult:
    def test_clean_result(self):
        result = ReferenceValueResult(is_flagged=False, findings=[], score=0.0)
        assert result.is_flagged is False
        assert result.score == 0.0

    def test_flagged_result(self):
        finding = ReferenceValueFinding(
            value=24.5,
            benchmark="nanogpt",
            description="GPT-2 small perplexity",
            line_number=1,
            source_snippet="x = 24.5",
        )
        result = ReferenceValueResult(is_flagged=True, findings=[finding], score=0.8)
        assert result.is_flagged is True
        assert len(result.findings) == 1
