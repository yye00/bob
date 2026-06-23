"""Tests for the 22-smell catalogue (smell_catalog.py)."""

from __future__ import annotations

import pytest

from bob3.spec_quality.smell_catalog import (
    BLOCKING_SMELLS,
    SMELL_BY_ID,
    SMELL_CATALOG,
    SPACY_SMELLS,
    SmellDefinition,
)


# ---------------------------------------------------------------------------
# Catalogue completeness
# ---------------------------------------------------------------------------

class TestCatalogueCompleteness:
    def test_exactly_22_smells(self):
        assert len(SMELL_CATALOG) == 22

    def test_all_ids_s01_to_s22(self):
        ids = {s.id for s in SMELL_CATALOG}
        expected = {f"S{i:02d}" for i in range(1, 23)}
        assert ids == expected

    def test_no_duplicate_ids(self):
        ids = [s.id for s in SMELL_CATALOG]
        assert len(ids) == len(set(ids))

    def test_smell_by_id_matches_catalog(self):
        assert len(SMELL_BY_ID) == 22
        for smell in SMELL_CATALOG:
            assert SMELL_BY_ID[smell.id] is smell

    def test_all_entries_are_smell_definition_instances(self):
        for s in SMELL_CATALOG:
            assert isinstance(s, SmellDefinition)


# ---------------------------------------------------------------------------
# Individual smell definitions
# ---------------------------------------------------------------------------

class TestSmellDefinitions:
    @pytest.mark.parametrize("smell_id,expected_name,expected_severity", [
        ("S01", "subjective-adjective", "E"),
        ("S02", "ambiguous-adverb", "W"),
        ("S03", "loophole", "E"),
        ("S04", "open-ended-enumeration", "W"),
        ("S05", "unbounded-superlative", "E"),
        ("S06", "comparative-without-baseline", "W"),
        ("S07", "vague-pronoun", "W"),
        ("S08", "passive-without-agent", "W"),
        ("S09", "modal-weakness", "E"),
        ("S10", "negation-without-scope", "W"),
        ("S11", "magic-number-without-unit", "E"),
        ("S12", "undefined-acronym", "W"),
        ("S13", "run-on-multi-requirement", "E"),
        ("S14", "implementation-leak", "W"),
        ("S15", "tautology", "I"),
        ("S16", "future-tense-drift", "I"),
        ("S17", "dangling-feature-id-reference", "W"),
        ("S18", "untestable-adjective", "E"),
        ("S19", "self-referential-test", "E"),
        ("S20", "empty-quantifier", "E"),
        ("S21", "shall-should-mixing", "W"),
        ("S22", "behavior-ac-without-test-mapping", "W"),
    ])
    def test_smell_name_and_severity(self, smell_id, expected_name, expected_severity):
        smell = SMELL_BY_ID[smell_id]
        assert smell.name == expected_name
        assert smell.severity == expected_severity

    def test_all_severities_valid(self):
        valid = {"E", "W", "I"}
        for s in SMELL_CATALOG:
            assert s.severity in valid, f"{s.id} has invalid severity {s.severity!r}"

    def test_all_descriptions_non_empty(self):
        for s in SMELL_CATALOG:
            assert s.description.strip(), f"{s.id} has an empty description"


# ---------------------------------------------------------------------------
# Derived sets: blocking smells and spaCy smells
# ---------------------------------------------------------------------------

class TestDerivedSets:
    def test_blocking_smells_are_error_severity(self):
        for sid in BLOCKING_SMELLS:
            assert SMELL_BY_ID[sid].severity == "E", f"{sid} is in BLOCKING_SMELLS but not E"

    def test_all_error_smells_in_blocking_set(self):
        error_ids = {s.id for s in SMELL_CATALOG if s.severity == "E"}
        assert error_ids == BLOCKING_SMELLS

    def test_spacy_smells_flagged_correctly(self):
        for sid in SPACY_SMELLS:
            assert SMELL_BY_ID[sid].uses_spacy is True

    def test_non_spacy_smells_not_flagged(self):
        for s in SMELL_CATALOG:
            if s.id not in SPACY_SMELLS:
                assert s.uses_spacy is False, f"{s.id} unexpectedly has uses_spacy=True"

    def test_spacy_smells_count(self):
        # S01, S02, S05, S06, S07, S08, S18 = 7 spaCy smells
        assert len(SPACY_SMELLS) == 7

    def test_expected_spacy_smell_ids(self):
        expected = {"S01", "S02", "S05", "S06", "S07", "S08", "S18"}
        assert SPACY_SMELLS == expected

    def test_blocking_smells_count(self):
        # E: S01, S03, S05, S09, S11, S13, S18, S19, S20 = 9
        assert len(BLOCKING_SMELLS) >= 8  # at least 8 E-severity smells

    def test_s15_and_s16_informational(self):
        assert SMELL_BY_ID["S15"].severity == "I"
        assert SMELL_BY_ID["S16"].severity == "I"
        assert "S15" not in BLOCKING_SMELLS
        assert "S16" not in BLOCKING_SMELLS
