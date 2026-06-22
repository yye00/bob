"""Tests that spec_critic.critique_feature emits correctly structured SpecDefect objects."""

from __future__ import annotations

import pytest

from bob3.spec_quality.spec_critic import (
    DEFECT_TYPES,
    SpecDefect,
    critique_feature,
)


# ---------------------------------------------------------------------------
# SpecDefect data class
# ---------------------------------------------------------------------------

class TestSpecDefect:
    def test_required_fields_stored(self):
        d = SpecDefect(
            feature_id="feat-001",
            ac_index=0,
            defect_type="ambiguity",
            rationale="vague",
            suggested_fix="use a structured form",
        )
        assert d.feature_id == "feat-001"
        assert d.ac_index == 0
        assert d.defect_type == "ambiguity"
        assert d.rationale == "vague"
        assert d.suggested_fix == "use a structured form"

    def test_invalid_defect_type_raises(self):
        with pytest.raises(ValueError, match="(?i)unknown defect_type"):
            SpecDefect(
                feature_id="x",
                ac_index=0,
                defect_type="not_a_real_type",
                rationale="r",
                suggested_fix="s",
            )

    def test_to_dict_contains_all_fields(self):
        d = SpecDefect(
            feature_id="f",
            ac_index=1,
            defect_type="untestable",
            rationale="r",
            suggested_fix="s",
        )
        d_dict = d.to_dict()
        assert set(d_dict.keys()) == {"feature_id", "ac_index", "defect_type", "rationale", "suggested_fix"}

    def test_all_defect_types_are_valid(self):
        for dt in DEFECT_TYPES:
            d = SpecDefect(feature_id="x", ac_index=0, defect_type=dt, rationale="r", suggested_fix="s")
            assert d.defect_type == dt


# ---------------------------------------------------------------------------
# critique_feature — happy path (no defects)
# ---------------------------------------------------------------------------

class TestCritiqueFeatureHappyPath:
    def test_clean_spec_returns_empty(self):
        defects = critique_feature(
            feature_id="clean-001",
            name="Clean feature",
            description="Adds a structured logging pipeline.",
            acceptance_criteria=[
                "File exists: src/bob3/logger.py",
                "Function defined: bob3.logger.log_event",
                "pytest: tests/test_logger.py",
                "pytest: tests/test_logger_invalid_payload.py",
            ],
        )
        assert defects == []

    def test_returns_list(self):
        result = critique_feature(
            feature_id="x",
            name="X",
            description="desc",
            acceptance_criteria=["File exists: src/x.py", "pytest: tests/test_x_error.py"],
        )
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Defect: ambiguity
# ---------------------------------------------------------------------------

class TestAmbiguityDefect:
    def test_detects_works_correctly(self):
        defects = critique_feature(
            feature_id="a-001",
            name="Ambiguous",
            description="d",
            acceptance_criteria=["The module works correctly"],
        )
        assert any(d.defect_type == "ambiguity" for d in defects)

    def test_empty_ac_is_ambiguity(self):
        defects = critique_feature(
            feature_id="a-002",
            name="Empty AC",
            description="d",
            acceptance_criteria=[""],
        )
        assert any(d.defect_type == "ambiguity" for d in defects)

    def test_structured_form_not_ambiguous(self):
        defects = critique_feature(
            feature_id="a-003",
            name="Structured",
            description="d",
            acceptance_criteria=[
                "File exists: src/bob3/foo.py",
                "pytest: tests/test_foo_error.py",
            ],
        )
        assert not any(d.defect_type == "ambiguity" for d in defects)


# ---------------------------------------------------------------------------
# Defect: untestable
# ---------------------------------------------------------------------------

class TestUntestableDefect:
    def test_detects_user_friendly(self):
        defects = critique_feature(
            feature_id="u-001",
            name="UI feature",
            description="d",
            acceptance_criteria=[
                "The UI is user-friendly",
                "pytest: tests/test_ui_error.py",
            ],
        )
        assert any(d.defect_type == "untestable" for d in defects)

    def test_detects_looks_good(self):
        defects = critique_feature(
            feature_id="u-002",
            name="Cosmetic",
            description="d",
            acceptance_criteria=[
                "The output looks good",
                "pytest: tests/test_output_invalid.py",
            ],
        )
        assert any(d.defect_type == "untestable" for d in defects)


# ---------------------------------------------------------------------------
# Defect: implementation_leak
# ---------------------------------------------------------------------------

class TestImplementationLeakDefect:
    def test_detects_uses_a_hashmap(self):
        defects = critique_feature(
            feature_id="il-001",
            name="Impl leak",
            description="d",
            acceptance_criteria=[
                "The system uses a hashmap for lookups",
                "pytest: tests/test_lookup_missing_key.py",
            ],
        )
        assert any(d.defect_type == "implementation_leak" for d in defects)


# ---------------------------------------------------------------------------
# Defect: vague_quantifier
# ---------------------------------------------------------------------------

class TestVagueQuantifierDefect:
    def test_detects_fast(self):
        defects = critique_feature(
            feature_id="vq-001",
            name="Perf",
            description="d",
            acceptance_criteria=[
                "Responses are fast",
                "pytest: tests/test_perf_timeout.py",
            ],
        )
        assert any(d.defect_type == "vague_quantifier" for d in defects)

    def test_detects_many(self):
        defects = critique_feature(
            feature_id="vq-002",
            name="Scale",
            description="d",
            acceptance_criteria=[
                "Handles many concurrent requests",
                "pytest: tests/test_concurrent_error.py",
            ],
        )
        assert any(d.defect_type == "vague_quantifier" for d in defects)


# ---------------------------------------------------------------------------
# Defect: missing_actor
# ---------------------------------------------------------------------------

class TestMissingActorDefect:
    def test_detects_shall_without_actor(self):
        defects = critique_feature(
            feature_id="ma-001",
            name="Actor missing",
            description="d",
            acceptance_criteria=[
                "shall persist findings to disk",
                "pytest: tests/test_persist_ioerror.py",
            ],
        )
        assert any(d.defect_type == "missing_actor" for d in defects)

    def test_must_without_actor(self):
        defects = critique_feature(
            feature_id="ma-002",
            name="Actor missing 2",
            description="d",
            acceptance_criteria=[
                "must reject invalid inputs",
                "pytest: tests/test_reject.py",
            ],
        )
        assert any(d.defect_type == "missing_actor" for d in defects)


# ---------------------------------------------------------------------------
# Defect: missing_edge_case
# ---------------------------------------------------------------------------

class TestMissingEdgeCaseDefect:
    def test_detects_all_happy_path(self):
        defects = critique_feature(
            feature_id="ec-001",
            name="Happy only",
            description="d",
            acceptance_criteria=[
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "pytest: tests/test_foo.py",
            ],
        )
        assert any(d.defect_type == "missing_edge_case" for d in defects)

    def test_no_defect_when_failure_ac_present(self):
        defects = critique_feature(
            feature_id="ec-002",
            name="Has edge case",
            description="d",
            acceptance_criteria=[
                "File exists: src/foo.py",
                "pytest: tests/test_foo_error.py",
            ],
        )
        assert not any(d.defect_type == "missing_edge_case" for d in defects)

    def test_no_defect_for_empty_ac_list(self):
        defects = critique_feature(
            feature_id="ec-003",
            name="No ACs",
            description="d",
            acceptance_criteria=[],
        )
        assert not any(d.defect_type == "missing_edge_case" for d in defects)


# ---------------------------------------------------------------------------
# Per-AC index tracking
# ---------------------------------------------------------------------------

class TestACIndexTracking:
    def test_defect_ac_index_matches_position(self):
        defects = critique_feature(
            feature_id="idx-001",
            name="Index test",
            description="d",
            acceptance_criteria=[
                "File exists: src/good.py",
                "The module works correctly",
                "pytest: tests/test_good_fail.py",
            ],
        )
        ambiguity_defects = [d for d in defects if d.defect_type == "ambiguity"]
        assert len(ambiguity_defects) == 1
        assert ambiguity_defects[0].ac_index == 1

    def test_feature_level_defect_has_minus_one_index(self):
        defects = critique_feature(
            feature_id="idx-002",
            name="Feature level",
            description="d",
            acceptance_criteria=[
                "File exists: src/x.py",
                "pytest: tests/test_x.py",
            ],
        )
        feature_defects = [d for d in defects if d.ac_index == -1]
        # missing_edge_case is a feature-level defect (ac_index=-1)
        edge_defects = [d for d in feature_defects if d.defect_type == "missing_edge_case"]
        assert len(edge_defects) == 1
