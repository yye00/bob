"""Tests for typed memory pool Pydantic entity schemas.

Covers BugPattern, SkillLesson, CalibrationDatum entities and their
integration with the bob3 memory pool system.
"""

import pytest
from pydantic import ValidationError

from bob3.typed_memory_pools_pydantic_entity_schemas import (
    BugPattern,
    CalibrationDatum,
    SkillLesson,
    entity_to_memory_content,
    entity_from_memory_content,
)


# ---------------------------------------------------------------------------
# BugPattern tests
# ---------------------------------------------------------------------------


class TestBugPattern:
    def test_create_minimal(self):
        bug = BugPattern(
            trigger="import fails",
            pattern="missing __init__.py",
            fix="add __init__.py to package directory",
        )
        assert bug.trigger == "import fails"
        assert bug.pattern == "missing __init__.py"
        assert bug.fix == "add __init__.py to package directory"
        assert bug.pool == "lessons"

    def test_create_full(self):
        bug = BugPattern(
            trigger="pytest collection error",
            pattern="circular import between modules A and B",
            fix="break the cycle by moving shared types to a separate module",
            error_type="ImportError",
            feature_id="feat-123",
            frequency=5,
        )
        assert bug.error_type == "ImportError"
        assert bug.feature_id == "feat-123"
        assert bug.frequency == 5

    def test_frequency_defaults_to_1(self):
        bug = BugPattern(
            trigger="x",
            pattern="y",
            fix="z",
        )
        assert bug.frequency == 1

    def test_frequency_must_be_positive(self):
        with pytest.raises(ValidationError):
            BugPattern(trigger="x", pattern="y", fix="z", frequency=0)

    def test_pool_is_lessons(self):
        bug = BugPattern(trigger="x", pattern="y", fix="z")
        assert bug.pool == "lessons"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            BugPattern(trigger="x")  # missing pattern and fix

    def test_serialization_roundtrip(self):
        bug = BugPattern(
            trigger="db error",
            pattern="connection not closed",
            fix="use context manager",
            error_type="OperationalError",
        )
        data = bug.model_dump()
        restored = BugPattern(**data)
        assert restored == bug


# ---------------------------------------------------------------------------
# SkillLesson tests
# ---------------------------------------------------------------------------


class TestSkillLesson:
    def test_create_minimal(self):
        lesson = SkillLesson(
            skill="tdd",
            lesson="write tests before implementation",
            context="feature implementation",
        )
        assert lesson.skill == "tdd"
        assert lesson.lesson == "write tests before implementation"
        assert lesson.context == "feature implementation"
        assert lesson.pool == "lessons"

    def test_create_full(self):
        lesson = SkillLesson(
            skill="debugging",
            lesson="root cause before fix",
            context="unexpected test failure",
            outcome="fixed in 1 attempt",
            confidence=0.9,
            feature_id="feat-456",
        )
        assert lesson.outcome == "fixed in 1 attempt"
        assert lesson.confidence == 0.9
        assert lesson.feature_id == "feat-456"

    def test_confidence_default_is_none(self):
        lesson = SkillLesson(skill="s", lesson="l", context="c")
        assert lesson.confidence is None

    def test_confidence_must_be_in_range(self):
        with pytest.raises(ValidationError):
            SkillLesson(skill="s", lesson="l", context="c", confidence=1.5)
        with pytest.raises(ValidationError):
            SkillLesson(skill="s", lesson="l", context="c", confidence=-0.1)

    def test_pool_is_lessons(self):
        lesson = SkillLesson(skill="s", lesson="l", context="c")
        assert lesson.pool == "lessons"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            SkillLesson(skill="tdd")

    def test_serialization_roundtrip(self):
        lesson = SkillLesson(
            skill="tdd",
            lesson="write failing test first",
            context="greenfield feature",
            confidence=0.85,
        )
        data = lesson.model_dump()
        restored = SkillLesson(**data)
        assert restored == lesson


# ---------------------------------------------------------------------------
# CalibrationDatum tests
# ---------------------------------------------------------------------------


class TestCalibrationDatum:
    def test_create_minimal(self):
        datum = CalibrationDatum(
            model="claude-sonnet-4-6",
            task="code generation",
            predicted_score=0.8,
            actual_score=0.75,
        )
        assert datum.model == "claude-sonnet-4-6"
        assert datum.task == "code generation"
        assert datum.predicted_score == 0.8
        assert datum.actual_score == 0.75
        assert datum.pool == "facts"

    def test_create_full(self):
        datum = CalibrationDatum(
            model="claude-opus-4-7",
            task="bug fixing",
            predicted_score=0.9,
            actual_score=0.7,
            error=0.2,
            feature_id="feat-789",
            notes="model overconfident on complex bugs",
        )
        assert datum.error == pytest.approx(0.2)
        assert datum.notes == "model overconfident on complex bugs"

    def test_error_auto_computed_when_none(self):
        datum = CalibrationDatum(
            model="m",
            task="t",
            predicted_score=0.6,
            actual_score=0.4,
        )
        assert datum.error == pytest.approx(0.2)

    def test_scores_must_be_in_range(self):
        with pytest.raises(ValidationError):
            CalibrationDatum(model="m", task="t", predicted_score=1.5, actual_score=0.5)
        with pytest.raises(ValidationError):
            CalibrationDatum(model="m", task="t", predicted_score=0.5, actual_score=-0.1)

    def test_pool_is_facts(self):
        datum = CalibrationDatum(model="m", task="t", predicted_score=0.5, actual_score=0.5)
        assert datum.pool == "facts"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            CalibrationDatum(model="m", task="t")  # missing scores

    def test_serialization_roundtrip(self):
        datum = CalibrationDatum(
            model="claude-sonnet-4-6",
            task="test generation",
            predicted_score=0.7,
            actual_score=0.65,
            notes="slight overconfidence",
        )
        data = datum.model_dump()
        restored = CalibrationDatum(**data)
        assert restored == datum


# ---------------------------------------------------------------------------
# entity_to_memory_content tests
# ---------------------------------------------------------------------------


class TestEntityToMemoryContent:
    def test_bug_pattern_to_content(self):
        bug = BugPattern(
            trigger="import fails",
            pattern="missing module",
            fix="install package",
            error_type="ModuleNotFoundError",
        )
        content = entity_to_memory_content(bug)
        assert "BugPattern" in content
        assert "import fails" in content
        assert "missing module" in content
        assert "install package" in content
        assert "ModuleNotFoundError" in content

    def test_skill_lesson_to_content(self):
        lesson = SkillLesson(
            skill="tdd",
            lesson="write tests first",
            context="implementation",
        )
        content = entity_to_memory_content(lesson)
        assert "SkillLesson" in content
        assert "tdd" in content
        assert "write tests first" in content

    def test_calibration_datum_to_content(self):
        datum = CalibrationDatum(
            model="claude-sonnet-4-6",
            task="code generation",
            predicted_score=0.8,
            actual_score=0.75,
        )
        content = entity_to_memory_content(datum)
        assert "CalibrationDatum" in content
        assert "claude-sonnet-4-6" in content
        assert "code generation" in content

    def test_content_is_string(self):
        bug = BugPattern(trigger="x", pattern="y", fix="z")
        content = entity_to_memory_content(bug)
        assert isinstance(content, str)
        assert len(content) > 0


# ---------------------------------------------------------------------------
# entity_from_memory_content tests
# ---------------------------------------------------------------------------


class TestEntityFromMemoryContent:
    def test_roundtrip_bug_pattern(self):
        original = BugPattern(
            trigger="test failure",
            pattern="missing fixture",
            fix="add conftest.py",
            error_type="FixtureError",
            frequency=3,
        )
        content = entity_to_memory_content(original)
        restored = entity_from_memory_content(content)
        assert isinstance(restored, BugPattern)
        assert restored.trigger == original.trigger
        assert restored.pattern == original.pattern
        assert restored.fix == original.fix
        assert restored.error_type == original.error_type
        assert restored.frequency == original.frequency

    def test_roundtrip_skill_lesson(self):
        original = SkillLesson(
            skill="systematic-debugging",
            lesson="form hypothesis before fixing",
            context="test failure investigation",
            confidence=0.8,
        )
        content = entity_to_memory_content(original)
        restored = entity_from_memory_content(content)
        assert isinstance(restored, SkillLesson)
        assert restored.skill == original.skill
        assert restored.lesson == original.lesson
        assert restored.confidence == original.confidence

    def test_roundtrip_calibration_datum(self):
        original = CalibrationDatum(
            model="claude-opus-4-7",
            task="bug diagnosis",
            predicted_score=0.9,
            actual_score=0.6,
            notes="overconfident",
        )
        content = entity_to_memory_content(original)
        restored = entity_from_memory_content(content)
        assert isinstance(restored, CalibrationDatum)
        assert restored.model == original.model
        assert restored.task == original.task
        assert restored.notes == original.notes

    def test_returns_none_for_unrecognized_content(self):
        result = entity_from_memory_content("some random text without entity marker")
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = entity_from_memory_content("")
        assert result is None


# ---------------------------------------------------------------------------
# Pool assignment tests
# ---------------------------------------------------------------------------


class TestPoolAssignment:
    def test_bug_pattern_pool(self):
        assert BugPattern(trigger="x", pattern="y", fix="z").pool == "lessons"

    def test_skill_lesson_pool(self):
        assert SkillLesson(skill="s", lesson="l", context="c").pool == "lessons"

    def test_calibration_datum_pool(self):
        assert CalibrationDatum(
            model="m", task="t", predicted_score=0.5, actual_score=0.5
        ).pool == "facts"
