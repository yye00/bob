"""Tests for bob3.hand_labeled_hack_attack_corpus_paper_artifact_stub.

Validates corpus structure, label distribution, attack-type breakdown,
and the public query API.
"""

from __future__ import annotations

import pytest

from bob3.hand_labeled_hack_attack_corpus_paper_artifact_stub import (
    ATTACK_METRIC_FAKING,
    ATTACK_SPEC_GAMING,
    ATTACK_TEST_HARDCODING,
    LABEL_CLEAN,
    LABEL_HACKING,
    CorpusEntry,
    corpus_stats,
    get_clean_entries,
    get_corpus,
    get_entries_by_attack,
    get_hacking_entries,
)


# ---------------------------------------------------------------------------
# CorpusEntry model
# ---------------------------------------------------------------------------


class TestCorpusEntry:
    def test_clean_entry_construction(self):
        entry = CorpusEntry(
            entry_id=1,
            label=LABEL_CLEAN,
            attack_type=None,
            diff="+def f(): return 1",
            test_output="test_f PASSED",
        )
        assert entry.label == LABEL_CLEAN
        assert entry.attack_type is None

    def test_hacking_entry_construction(self):
        entry = CorpusEntry(
            entry_id=51,
            label=LABEL_HACKING,
            attack_type=ATTACK_TEST_HARDCODING,
            diff="+def f(): return 42",
            test_output="test_f PASSED",
        )
        assert entry.label == LABEL_HACKING
        assert entry.attack_type == ATTACK_TEST_HARDCODING

    def test_invalid_label_raises(self):
        with pytest.raises(ValueError, match="label must be one of"):
            CorpusEntry(
                entry_id=1,
                label="unknown",
                attack_type=None,
                diff="",
                test_output="",
            )

    def test_invalid_attack_type_raises(self):
        with pytest.raises(ValueError, match="attack_type must be one of"):
            CorpusEntry(
                entry_id=1,
                label=LABEL_HACKING,
                attack_type="bad_attack",
                diff="",
                test_output="",
            )

    def test_clean_entry_with_attack_type_raises(self):
        with pytest.raises(ValueError, match="Clean entries must have attack_type=None"):
            CorpusEntry(
                entry_id=1,
                label=LABEL_CLEAN,
                attack_type=ATTACK_SPEC_GAMING,
                diff="",
                test_output="",
            )

    def test_hacking_entry_without_attack_type_raises(self):
        with pytest.raises(ValueError, match="Hacking entries must specify an attack_type"):
            CorpusEntry(
                entry_id=51,
                label=LABEL_HACKING,
                attack_type=None,
                diff="",
                test_output="",
            )

    def test_notes_default_is_empty_string(self):
        entry = CorpusEntry(
            entry_id=1,
            label=LABEL_CLEAN,
            attack_type=None,
            diff="+pass",
            test_output="PASSED",
        )
        assert entry.notes == ""


# ---------------------------------------------------------------------------
# Corpus size and composition
# ---------------------------------------------------------------------------


class TestCorpusSize:
    def test_total_count_is_100(self):
        assert len(get_corpus()) == 100

    def test_clean_count_is_50(self):
        assert len(get_clean_entries()) == 50

    def test_hacking_count_is_50(self):
        assert len(get_hacking_entries()) == 50

    def test_clean_plus_hacking_equals_total(self):
        total = get_corpus()
        clean = get_clean_entries()
        hacking = get_hacking_entries()
        assert len(clean) + len(hacking) == len(total)


# ---------------------------------------------------------------------------
# Entry IDs
# ---------------------------------------------------------------------------


class TestEntryIds:
    def test_all_ids_unique(self):
        ids = [e.entry_id for e in get_corpus()]
        assert len(set(ids)) == len(ids), "Duplicate entry_id found"

    def test_ids_cover_1_to_100(self):
        ids = sorted(e.entry_id for e in get_corpus())
        assert ids == list(range(1, 101))

    def test_clean_ids_are_1_to_50(self):
        ids = sorted(e.entry_id for e in get_clean_entries())
        assert ids == list(range(1, 51))

    def test_hacking_ids_are_51_to_100(self):
        ids = sorted(e.entry_id for e in get_hacking_entries())
        assert ids == list(range(51, 101))


# ---------------------------------------------------------------------------
# Labels consistency
# ---------------------------------------------------------------------------


class TestLabels:
    def test_all_clean_entries_have_label_clean(self):
        for entry in get_clean_entries():
            assert entry.label == LABEL_CLEAN

    def test_all_hacking_entries_have_label_hacking(self):
        for entry in get_hacking_entries():
            assert entry.label == LABEL_HACKING

    def test_clean_entries_have_no_attack_type(self):
        for entry in get_clean_entries():
            assert entry.attack_type is None, (
                f"Entry {entry.entry_id} is clean but has attack_type={entry.attack_type!r}"
            )

    def test_hacking_entries_all_have_attack_type(self):
        for entry in get_hacking_entries():
            assert entry.attack_type is not None, (
                f"Entry {entry.entry_id} is hacking but has no attack_type"
            )

    def test_hacking_attack_types_are_valid(self):
        valid = {ATTACK_TEST_HARDCODING, ATTACK_METRIC_FAKING, ATTACK_SPEC_GAMING}
        for entry in get_hacking_entries():
            assert entry.attack_type in valid, (
                f"Entry {entry.entry_id} has unrecognised attack_type {entry.attack_type!r}"
            )


# ---------------------------------------------------------------------------
# Attack-type filtering
# ---------------------------------------------------------------------------


class TestAttackTypeFilter:
    def test_test_hardcoding_entries_exist(self):
        entries = get_entries_by_attack(ATTACK_TEST_HARDCODING)
        assert len(entries) > 0

    def test_metric_faking_entries_exist(self):
        entries = get_entries_by_attack(ATTACK_METRIC_FAKING)
        assert len(entries) > 0

    def test_spec_gaming_entries_exist(self):
        entries = get_entries_by_attack(ATTACK_SPEC_GAMING)
        assert len(entries) > 0

    def test_attack_filter_returns_correct_label(self):
        for attack in (ATTACK_TEST_HARDCODING, ATTACK_METRIC_FAKING, ATTACK_SPEC_GAMING):
            for entry in get_entries_by_attack(attack):
                assert entry.attack_type == attack
                assert entry.label == LABEL_HACKING

    def test_attack_type_counts_sum_to_hacking_total(self):
        hacking_total = len(get_hacking_entries())
        sum_by_attack = sum(
            len(get_entries_by_attack(a))
            for a in (ATTACK_TEST_HARDCODING, ATTACK_METRIC_FAKING, ATTACK_SPEC_GAMING)
        )
        assert sum_by_attack == hacking_total

    def test_unknown_attack_type_returns_empty(self):
        assert get_entries_by_attack("nonexistent_attack") == []


# ---------------------------------------------------------------------------
# Diff and test_output content
# ---------------------------------------------------------------------------


class TestEntryContent:
    def test_all_entries_have_non_empty_diff(self):
        for entry in get_corpus():
            assert entry.diff.strip(), f"Entry {entry.entry_id} has empty diff"

    def test_all_entries_have_non_empty_test_output(self):
        for entry in get_corpus():
            assert entry.test_output.strip(), (
                f"Entry {entry.entry_id} has empty test_output"
            )

    def test_clean_diffs_contain_plus_lines(self):
        for entry in get_clean_entries():
            assert "+" in entry.diff, (
                f"Entry {entry.entry_id} diff lacks added lines"
            )

    def test_hacking_diffs_contain_plus_lines(self):
        for entry in get_hacking_entries():
            assert "+" in entry.diff, (
                f"Entry {entry.entry_id} diff lacks added lines"
            )


# ---------------------------------------------------------------------------
# corpus_stats()
# ---------------------------------------------------------------------------


class TestCorpusStats:
    def test_stats_total(self):
        stats = corpus_stats()
        assert stats["total"] == 100

    def test_stats_clean(self):
        stats = corpus_stats()
        assert stats["clean"] == 50

    def test_stats_hacking(self):
        stats = corpus_stats()
        assert stats["hacking"] == 50

    def test_stats_by_attack_keys(self):
        stats = corpus_stats()
        by_attack = stats["by_attack"]
        assert ATTACK_TEST_HARDCODING in by_attack
        assert ATTACK_METRIC_FAKING in by_attack
        assert ATTACK_SPEC_GAMING in by_attack

    def test_stats_by_attack_counts_positive(self):
        stats = corpus_stats()
        for attack, count in stats["by_attack"].items():
            assert count > 0, f"Attack type {attack!r} has zero entries"

    def test_stats_by_attack_sum_equals_hacking(self):
        stats = corpus_stats()
        total_by_attack = sum(stats["by_attack"].values())
        assert total_by_attack == stats["hacking"]

    def test_stats_returns_dict(self):
        assert isinstance(corpus_stats(), dict)


# ---------------------------------------------------------------------------
# Return-value immutability (get_corpus returns fresh list)
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_get_corpus_returns_independent_list(self):
        c1 = get_corpus()
        c2 = get_corpus()
        assert c1 is not c2

    def test_get_clean_returns_independent_list(self):
        c1 = get_clean_entries()
        c2 = get_clean_entries()
        assert c1 is not c2

    def test_get_hacking_returns_independent_list(self):
        h1 = get_hacking_entries()
        h2 = get_hacking_entries()
        assert h1 is not h2
