"""Typed Pydantic entity schemas for bob memory pools.

Replaces free-text lesson strings in the learning ledger with structured
Pydantic entities: BugPattern, SkillLesson, CalibrationDatum. Enables
structured retrieval, deduplication, and schema evolution.

Each entity carries a ``pool`` field indicating its target memory pool
(``lessons`` for BugPattern/SkillLesson, ``facts`` for CalibrationDatum).

Serialization helpers ``entity_to_memory_content`` and
``entity_from_memory_content`` convert entities to/from the string format
stored in the memory backend.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

_ENTITY_PREFIX = "__entity__:"


class BugPattern(BaseModel):
    """A recurring bug pattern observed during feature implementation.

    Captures the trigger condition, the underlying structural pattern,
    and the fix so future agents can avoid repeating the same mistake.
    """

    trigger: str = Field(description="The context or symptom that surfaces this bug.")
    pattern: str = Field(description="The root structural/logical cause of the bug.")
    fix: str = Field(description="The concrete action that resolves the bug.")
    error_type: str | None = Field(default=None, description="Exception class name, if applicable.")
    feature_id: str | None = Field(default=None, description="Feature that first surfaced this bug.")
    frequency: Annotated[int, Field(ge=1)] = Field(
        default=1, description="Number of times this pattern has been observed."
    )
    pool: Literal["lessons"] = "lessons"

    model_config = {"frozen": False}


class SkillLesson(BaseModel):
    """A lesson learned about applying a particular skill or technique.

    Records what was learned, in what context, and with what outcome so
    future agents can apply the same approach more reliably.
    """

    skill: str = Field(description="Name of the skill or technique this lesson covers.")
    lesson: str = Field(description="The core insight or principle learned.")
    context: str = Field(description="Situation or trigger that produced this lesson.")
    outcome: str | None = Field(default=None, description="Result of applying this lesson.")
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = Field(
        default=None, description="Subjective confidence in this lesson (0–1)."
    )
    feature_id: str | None = Field(default=None, description="Feature where lesson was learned.")
    pool: Literal["lessons"] = "lessons"

    model_config = {"frozen": False}


class CalibrationDatum(BaseModel):
    """A single model calibration observation.

    Records predicted vs. actual scores for a specific model/task pair,
    enabling downstream calibration-aware budget and confidence adjustments.
    """

    model: str = Field(description="Model identifier (e.g. 'claude-sonnet-4-6').")
    task: str = Field(description="Task category or description.")
    predicted_score: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        description="Model's self-reported or predicted performance score."
    )
    actual_score: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        description="Empirically measured performance score."
    )
    error: float | None = Field(
        default=None,
        description="Absolute calibration error |predicted - actual|. Auto-computed if not set.",
    )
    feature_id: str | None = Field(default=None, description="Feature associated with this datum.")
    notes: str | None = Field(default=None, description="Free-text observations.")
    pool: Literal["facts"] = "facts"

    model_config = {"frozen": False}

    @model_validator(mode="after")
    def _compute_error(self) -> "CalibrationDatum":
        if self.error is None:
            self.error = abs(self.predicted_score - self.actual_score)
        return self


# Union type for all supported typed entities.
MemoryEntity = Union[BugPattern, SkillLesson, CalibrationDatum]

_ENTITY_TYPE_MAP: dict[str, type[MemoryEntity]] = {
    "BugPattern": BugPattern,
    "SkillLesson": SkillLesson,
    "CalibrationDatum": CalibrationDatum,
}


def entity_to_memory_content(entity: MemoryEntity) -> str:
    """Serialize a typed entity to a string for storage in the memory backend.

    The string begins with a sentinel prefix so ``entity_from_memory_content``
    can distinguish typed entries from legacy free-text entries.
    """
    type_name = type(entity).__name__
    payload = entity.model_dump(mode="json")
    return f"{_ENTITY_PREFIX}{type_name}:{json.dumps(payload, ensure_ascii=False)}"


def entity_from_memory_content(content: str) -> MemoryEntity | None:
    """Deserialize a typed entity from a memory content string.

    Returns ``None`` if the content is not a typed entity (e.g. legacy
    free-text lessons), so callers can handle both old and new entries.
    """
    if not content or not content.startswith(_ENTITY_PREFIX):
        return None

    rest = content[len(_ENTITY_PREFIX):]
    colon_idx = rest.find(":")
    if colon_idx == -1:
        return None

    type_name = rest[:colon_idx]
    json_str = rest[colon_idx + 1:]

    entity_cls = _ENTITY_TYPE_MAP.get(type_name)
    if entity_cls is None:
        logger.warning("Unknown entity type in memory content: %r", type_name)
        return None

    try:
        data = json.loads(json_str)
        return entity_cls(**data)
    except Exception as exc:
        logger.warning("Failed to deserialize %s entity: %s", type_name, exc)
        return None
