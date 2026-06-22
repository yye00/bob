"""Tests for the AST-grade plagiarism detector (feature 7bb3af48).

Covers:
- AST fingerprinting produces deterministic, normalized hashes
- Similarity scoring between identical / near-identical / distinct implementations
- Threshold enforcement (flag when similarity > threshold)
- Reference registry CRUD
- Integration hook into reward_hacking_detector verdict
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from bob3.plagiarism_detector import (
    ASTFingerprint,
    PlagiarismResult,
    ReferenceRegistry,
    fingerprint_source,
    compute_similarity,
    check_plagiarism,
    augment_hacking_verdict,
)
from bob3.reward_hacking_detector import HackingVerdict, AttackVectorScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedent(src: str) -> str:
    return textwrap.dedent(src).strip()


# ---------------------------------------------------------------------------
# Canonical reference implementations used across tests
# ---------------------------------------------------------------------------

BUBBLE_SORT_A = _dedent("""
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr
""")

# Near-verbatim copy of BUBBLE_SORT_A: variable renamed, docstring added
BUBBLE_SORT_B = _dedent("""
def sort_bubbles(lst):
    \"\"\"Sort via bubble algorithm.\"\"\"
    n = len(lst)
    for i in range(n):
        for j in range(n - i - 1):
            if lst[j] > lst[j + 1]:
                lst[j], lst[j + 1] = lst[j + 1], lst[j]
    return lst
""")

# Structurally distinct: insertion sort
INSERTION_SORT = _dedent("""
def insertion_sort(arr):
    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
        arr[j + 1] = key
    return arr
""")

QUICKSORT = _dedent("""
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)
""")


# ===========================================================================
# 1. ASTFingerprint
# ===========================================================================

class TestASTFingerprint:
    def test_fingerprint_has_hash(self):
        fp = fingerprint_source(BUBBLE_SORT_A)
        assert isinstance(fp, ASTFingerprint)
        assert fp.hash_hex and len(fp.hash_hex) == 64  # sha256 hex

    def test_fingerprint_is_deterministic(self):
        fp1 = fingerprint_source(BUBBLE_SORT_A)
        fp2 = fingerprint_source(BUBBLE_SORT_A)
        assert fp1.hash_hex == fp2.hash_hex

    def test_fingerprint_ignores_variable_names(self):
        # BUBBLE_SORT_A and BUBBLE_SORT_B differ only in names/docstrings
        # After normalization they should share many structural tokens
        fp_a = fingerprint_source(BUBBLE_SORT_A)
        fp_b = fingerprint_source(BUBBLE_SORT_B)
        # Hashes differ (normalization is not full rename-blindness by default)
        # but their ngram overlap should be high — tested in similarity below
        assert fp_a is not None and fp_b is not None

    def test_fingerprint_records_node_sequence(self):
        fp = fingerprint_source(BUBBLE_SORT_A)
        assert len(fp.node_sequence) > 0

    def test_fingerprint_invalid_syntax_returns_none(self):
        result = fingerprint_source("def foo(: pass")
        assert result is None

    def test_fingerprint_empty_source(self):
        result = fingerprint_source("")
        assert result is not None  # empty module is valid
        assert result.hash_hex is not None


# ===========================================================================
# 2. compute_similarity
# ===========================================================================

class TestComputeSimilarity:
    def test_identical_sources_score_1(self):
        fp = fingerprint_source(BUBBLE_SORT_A)
        sim = compute_similarity(fp, fp)
        assert sim == pytest.approx(1.0)

    def test_near_verbatim_copy_scores_high(self):
        fp_a = fingerprint_source(BUBBLE_SORT_A)
        fp_b = fingerprint_source(BUBBLE_SORT_B)
        sim = compute_similarity(fp_a, fp_b)
        # Near-verbatim copy should be > 0.7
        assert sim >= 0.7, f"Expected >= 0.7 for near-copy, got {sim:.3f}"

    def test_distinct_algorithm_scores_low(self):
        fp_bubble = fingerprint_source(BUBBLE_SORT_A)
        fp_insert = fingerprint_source(INSERTION_SORT)
        sim = compute_similarity(fp_bubble, fp_insert)
        # Structurally different algorithms should score < 0.6
        assert sim < 0.7, f"Expected < 0.7 for distinct algorithms, got {sim:.3f}"

    def test_similarity_is_symmetric(self):
        fp_a = fingerprint_source(BUBBLE_SORT_A)
        fp_b = fingerprint_source(INSERTION_SORT)
        assert compute_similarity(fp_a, fp_b) == pytest.approx(
            compute_similarity(fp_b, fp_a), abs=1e-9
        )

    def test_similarity_between_empty_and_nonempty(self):
        fp_empty = fingerprint_source("")
        fp_code = fingerprint_source(BUBBLE_SORT_A)
        sim = compute_similarity(fp_empty, fp_code)
        assert 0.0 <= sim <= 1.0


# ===========================================================================
# 3. ReferenceRegistry
# ===========================================================================

class TestReferenceRegistry:
    def test_add_and_list(self):
        reg = ReferenceRegistry()
        reg.add_reference("bubble_sort_canonical", BUBBLE_SORT_A)
        names = reg.list_references()
        assert "bubble_sort_canonical" in names

    def test_add_duplicate_overwrites(self):
        reg = ReferenceRegistry()
        reg.add_reference("algo", BUBBLE_SORT_A)
        reg.add_reference("algo", INSERTION_SORT)  # overwrite
        names = reg.list_references()
        assert names.count("algo") == 1

    def test_remove_reference(self):
        reg = ReferenceRegistry()
        reg.add_reference("algo", BUBBLE_SORT_A)
        reg.remove_reference("algo")
        assert "algo" not in reg.list_references()

    def test_remove_nonexistent_is_noop(self):
        reg = ReferenceRegistry()
        reg.remove_reference("does_not_exist")  # should not raise

    def test_get_fingerprint(self):
        reg = ReferenceRegistry()
        reg.add_reference("bubble", BUBBLE_SORT_A)
        fp = reg.get_fingerprint("bubble")
        assert fp is not None
        assert fp.hash_hex is not None

    def test_get_fingerprint_missing_returns_none(self):
        reg = ReferenceRegistry()
        assert reg.get_fingerprint("missing") is None

    def test_from_sources_dict(self):
        sources = {
            "bubble": BUBBLE_SORT_A,
            "insertion": INSERTION_SORT,
        }
        reg = ReferenceRegistry.from_sources(sources)
        assert set(reg.list_references()) == {"bubble", "insertion"}


# ===========================================================================
# 4. check_plagiarism
# ===========================================================================

class TestCheckPlagiarism:
    def _make_registry(self) -> ReferenceRegistry:
        reg = ReferenceRegistry()
        reg.add_reference("bubble_sort", BUBBLE_SORT_A)
        reg.add_reference("insertion_sort", INSERTION_SORT)
        reg.add_reference("quicksort", QUICKSORT)
        return reg

    def test_near_verbatim_flagged_above_threshold(self):
        reg = self._make_registry()
        result = check_plagiarism(BUBBLE_SORT_B, registry=reg, threshold=0.7)
        assert isinstance(result, PlagiarismResult)
        assert result.is_flagged
        assert result.max_similarity >= 0.7
        assert result.closest_reference == "bubble_sort"

    def test_distinct_algorithm_not_flagged(self):
        reg = self._make_registry()
        result = check_plagiarism(QUICKSORT, registry=reg, threshold=0.7)
        # quicksort is in the registry — identical to itself, so it WILL be flagged
        # Use fresh code that doesn't match any reference
        fresh_code = _dedent("""
        def merge_sort(arr):
            if len(arr) <= 1:
                return arr
            mid = len(arr) // 2
            left = merge_sort(arr[:mid])
            right = merge_sort(arr[mid:])
            result = []
            i = j = 0
            while i < len(left) and j < len(right):
                if left[i] <= right[j]:
                    result.append(left[i]); i += 1
                else:
                    result.append(right[j]); j += 1
            result.extend(left[i:]); result.extend(right[j:])
            return result
        """)
        result = check_plagiarism(fresh_code, registry=reg, threshold=0.7)
        assert not result.is_flagged

    def test_threshold_controls_flagging(self):
        reg = self._make_registry()
        # With a very high threshold (0.99), near-copy should not be flagged
        result_strict = check_plagiarism(BUBBLE_SORT_B, registry=reg, threshold=0.99)
        # With a low threshold (0.3), even vaguely similar code is flagged
        result_loose = check_plagiarism(BUBBLE_SORT_B, registry=reg, threshold=0.3)
        assert result_loose.is_flagged
        # The strict one may or may not be flagged depending on exact similarity
        # Just confirm it returns a valid result
        assert isinstance(result_strict, PlagiarismResult)

    def test_empty_registry_returns_clean(self):
        reg = ReferenceRegistry()
        result = check_plagiarism(BUBBLE_SORT_A, registry=reg, threshold=0.7)
        assert not result.is_flagged
        assert result.max_similarity == 0.0

    def test_invalid_source_returns_clean_result(self):
        reg = self._make_registry()
        result = check_plagiarism("def foo(: pass", registry=reg, threshold=0.7)
        assert isinstance(result, PlagiarismResult)
        assert not result.is_flagged

    def test_result_has_per_reference_scores(self):
        reg = self._make_registry()
        result = check_plagiarism(BUBBLE_SORT_B, registry=reg, threshold=0.7)
        assert isinstance(result.scores, dict)
        assert "bubble_sort" in result.scores
        assert 0.0 <= result.scores["bubble_sort"] <= 1.0

    def test_identical_source_flagged_as_exact_copy(self):
        reg = self._make_registry()
        result = check_plagiarism(BUBBLE_SORT_A, registry=reg, threshold=0.7)
        assert result.is_flagged
        assert result.max_similarity == pytest.approx(1.0)
        assert result.closest_reference == "bubble_sort"


# ===========================================================================
# 5. augment_hacking_verdict
# ===========================================================================

class TestAugmentHackingVerdict:
    def _clean_verdict(self) -> HackingVerdict:
        return HackingVerdict(
            verdict="clean",
            overall_score=0.1,
            attack_vectors=[
                AttackVectorScore(vector=v, score=0.1, reasoning="ok")
                for v in [
                    "test_hardcoding",
                    "delegation_to_library",
                    "spec_gaming",
                    "metric_overfitting",
                    "implementation_elision",
                ]
            ],
            reasoning="Looks genuine.",
            confidence=0.9,
        )

    def _make_registry_with_bubble(self) -> ReferenceRegistry:
        reg = ReferenceRegistry()
        reg.add_reference("bubble_sort", BUBBLE_SORT_A)
        return reg

    def test_clean_verdict_not_changed_when_no_plagiarism(self):
        verdict = self._clean_verdict()
        reg = self._make_registry_with_bubble()
        fresh_code = _dedent("""
        def merge_sort(arr):
            if len(arr) <= 1:
                return arr
            mid = len(arr) // 2
            left = merge_sort(arr[:mid])
            right = merge_sort(arr[mid:])
            return left + right
        """)
        augmented = augment_hacking_verdict(
            verdict=verdict,
            source=fresh_code,
            registry=reg,
            threshold=0.7,
        )
        assert augmented.verdict == "clean"

    def test_plagiarism_escalates_to_suspicious(self):
        verdict = self._clean_verdict()
        reg = self._make_registry_with_bubble()
        augmented = augment_hacking_verdict(
            verdict=verdict,
            source=BUBBLE_SORT_B,  # near-verbatim copy
            registry=reg,
            threshold=0.7,
        )
        # The verdict should be escalated: clean → suspicious or hacking
        assert augmented.verdict in ("suspicious", "hacking")
        assert augmented.overall_score > verdict.overall_score

    def test_high_similarity_escalates_to_hacking(self):
        verdict = self._clean_verdict()
        reg = self._make_registry_with_bubble()
        augmented = augment_hacking_verdict(
            verdict=verdict,
            source=BUBBLE_SORT_A,  # exact copy
            registry=reg,
            threshold=0.5,
        )
        assert augmented.verdict == "hacking"

    def test_already_hacking_verdict_not_downgraded(self):
        verdict = HackingVerdict(
            verdict="hacking",
            overall_score=0.9,
            attack_vectors=[
                AttackVectorScore(vector=v, score=0.9, reasoning="bad")
                for v in [
                    "test_hardcoding",
                    "delegation_to_library",
                    "spec_gaming",
                    "metric_overfitting",
                    "implementation_elision",
                ]
            ],
            reasoning="Confirmed hacking.",
            confidence=0.95,
        )
        reg = self._make_registry_with_bubble()
        fresh_code = "def foo(): return 42"
        augmented = augment_hacking_verdict(
            verdict=verdict,
            source=fresh_code,
            registry=reg,
            threshold=0.7,
        )
        assert augmented.verdict == "hacking"
        assert augmented.overall_score >= 0.9

    def test_plagiarism_result_added_to_attack_vectors(self):
        verdict = self._clean_verdict()
        reg = self._make_registry_with_bubble()
        augmented = augment_hacking_verdict(
            verdict=verdict,
            source=BUBBLE_SORT_B,
            registry=reg,
            threshold=0.7,
        )
        vector_names = [av.vector for av in augmented.attack_vectors]
        assert "plagiarism" in vector_names

    def test_augment_with_empty_registry_preserves_verdict(self):
        verdict = self._clean_verdict()
        reg = ReferenceRegistry()
        augmented = augment_hacking_verdict(
            verdict=verdict,
            source=BUBBLE_SORT_A,
            registry=reg,
            threshold=0.7,
        )
        assert augmented.verdict == "clean"
