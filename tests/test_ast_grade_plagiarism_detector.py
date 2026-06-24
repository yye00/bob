"""Tests for src/bob/ast_grade_plagiarism_detector.py (feature 7bb3af48).

Verifies the canonical ``ast_grade_plagiarism_detector`` module exposes the
full public API and behaves correctly end-to-end.  Core algorithm tests live
in ``test_plagiarism_detector.py``; this file focuses on:
- The module is importable from ``bob.ast_grade_plagiarism_detector``
- All public symbols are available
- End-to-end behaviour via the canonical import path
"""

from __future__ import annotations

import textwrap

import pytest

from bob.ast_grade_plagiarism_detector import (
    ASTFingerprint,
    PlagiarismResult,
    ReferenceRegistry,
    augment_hacking_verdict,
    check_plagiarism,
    compute_similarity,
    fingerprint_source,
)
from bob.reward_hacking_detector import AttackVectorScore, HackingVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _src(code: str) -> str:
    return textwrap.dedent(code).strip()


BUBBLE_SORT = _src("""
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
""")

BUBBLE_SORT_COPY = _src("""
def sort_bubbles(lst):
    \"\"\"Near-verbatim copy with renamed vars and a docstring.\"\"\"
    n = len(lst)
    for i in range(n):
        for j in range(n - i - 1):
            if lst[j] > lst[j + 1]:
                lst[j], lst[j + 1] = lst[j + 1], lst[j]
    return lst
""")

MERGE_SORT = _src("""
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    result, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i]); i += 1
        else:
            result.append(right[j]); j += 1
    result.extend(left[i:]); result.extend(right[j:])
    return result
""")


# ===========================================================================
# Module-level: public API is importable
# ===========================================================================

class TestPublicAPIImportable:
    def test_fingerprint_source_callable(self):
        assert callable(fingerprint_source)

    def test_compute_similarity_callable(self):
        assert callable(compute_similarity)

    def test_check_plagiarism_callable(self):
        assert callable(check_plagiarism)

    def test_augment_hacking_verdict_callable(self):
        assert callable(augment_hacking_verdict)

    def test_reference_registry_instantiable(self):
        reg = ReferenceRegistry()
        assert reg is not None

    def test_ast_fingerprint_dataclass(self):
        fp = fingerprint_source(BUBBLE_SORT)
        assert isinstance(fp, ASTFingerprint)

    def test_plagiarism_result_dataclass(self):
        reg = ReferenceRegistry()
        result = check_plagiarism(BUBBLE_SORT, registry=reg)
        assert isinstance(result, PlagiarismResult)


# ===========================================================================
# End-to-end: fingerprint → similarity → check
# ===========================================================================

class TestEndToEnd:
    def test_identical_fingerprint_similarity_is_one(self):
        fp = fingerprint_source(BUBBLE_SORT)
        assert compute_similarity(fp, fp) == pytest.approx(1.0)

    def test_near_copy_detected(self):
        reg = ReferenceRegistry.from_sources({"bubble_sort": BUBBLE_SORT})
        result = check_plagiarism(BUBBLE_SORT_COPY, registry=reg, threshold=0.7)
        assert result.is_flagged
        assert result.closest_reference == "bubble_sort"
        assert result.max_similarity >= 0.7

    def test_distinct_algorithm_not_flagged(self):
        reg = ReferenceRegistry.from_sources({"bubble_sort": BUBBLE_SORT})
        result = check_plagiarism(MERGE_SORT, registry=reg, threshold=0.7)
        assert not result.is_flagged

    def test_syntax_error_returns_clean_result(self):
        reg = ReferenceRegistry.from_sources({"bubble_sort": BUBBLE_SORT})
        result = check_plagiarism("def bad(: pass", registry=reg, threshold=0.7)
        assert isinstance(result, PlagiarismResult)
        assert not result.is_flagged

    def test_empty_registry_returns_clean(self):
        reg = ReferenceRegistry()
        result = check_plagiarism(BUBBLE_SORT, registry=reg, threshold=0.5)
        assert not result.is_flagged
        assert result.max_similarity == 0.0


# ===========================================================================
# Reward-hacking integration
# ===========================================================================

class TestVerdictIntegration:
    def _verdict(self, v: str = "clean", score: float = 0.1) -> HackingVerdict:
        return HackingVerdict(
            verdict=v,
            overall_score=score,
            attack_vectors=[
                AttackVectorScore(vector=av, score=0.1, reasoning="ok")
                for av in [
                    "test_hardcoding",
                    "delegation_to_library",
                    "spec_gaming",
                    "metric_overfitting",
                    "implementation_elision",
                ]
            ],
            reasoning="baseline",
            confidence=0.9,
        )

    def test_plagiarism_vector_added(self):
        reg = ReferenceRegistry.from_sources({"bubble_sort": BUBBLE_SORT})
        verdict = self._verdict()
        augmented = augment_hacking_verdict(
            verdict, source=BUBBLE_SORT_COPY, registry=reg, threshold=0.7
        )
        names = [av.vector for av in augmented.attack_vectors]
        assert "plagiarism" in names

    def test_exact_copy_escalates_to_hacking(self):
        reg = ReferenceRegistry.from_sources({"bubble_sort": BUBBLE_SORT})
        verdict = self._verdict()
        augmented = augment_hacking_verdict(
            verdict, source=BUBBLE_SORT, registry=reg, threshold=0.5
        )
        assert augmented.verdict == "hacking"

    def test_clean_source_preserves_clean_verdict(self):
        reg = ReferenceRegistry.from_sources({"bubble_sort": BUBBLE_SORT})
        verdict = self._verdict()
        augmented = augment_hacking_verdict(
            verdict, source=MERGE_SORT, registry=reg, threshold=0.7
        )
        assert augmented.verdict == "clean"

    def test_hacking_verdict_never_downgraded(self):
        reg = ReferenceRegistry()
        verdict = self._verdict(v="hacking", score=0.95)
        augmented = augment_hacking_verdict(
            verdict, source="def foo(): pass", registry=reg, threshold=0.7
        )
        assert augmented.verdict == "hacking"
        assert augmented.overall_score >= 0.95
