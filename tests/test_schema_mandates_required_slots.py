"""Tests that schemas/spec.v1.json mandates the required PRD slots.

The pinned schema must contain all slots the spec critic grades:
functional_requirements, non_functional_requirements, acceptance_criteria,
out_of_scope, risks.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob.spec_quality.schema_constrained_emit import load_pinned_schema


REQUIRED_SLOTS = [
    "functional_requirements",
    "non_functional_requirements",
    "acceptance_criteria",
    "out_of_scope",
    "risks",
]


def test_schema_file_exists() -> None:
    schema_path = Path(__file__).parent.parent / "schemas" / "spec.v1.json"
    assert schema_path.exists(), f"schemas/spec.v1.json not found at {schema_path}"


def test_schema_is_valid_json() -> None:
    schema_path = Path(__file__).parent.parent / "schemas" / "spec.v1.json"
    schema = json.loads(schema_path.read_text())
    assert isinstance(schema, dict)


def test_schema_has_required_field_list() -> None:
    schema = load_pinned_schema()
    assert "required" in schema, "Schema must have a 'required' array"
    assert isinstance(schema["required"], list)


@pytest.mark.parametrize("slot", REQUIRED_SLOTS)
def test_schema_required_array_contains_slot(slot: str) -> None:
    schema = load_pinned_schema()
    required = schema.get("required", [])
    assert slot in required, f"Required slot '{slot}' missing from schema['required']"


def test_schema_contains_all_required_slots() -> None:
    schema = load_pinned_schema()
    required = set(schema.get("required", []))
    missing = [s for s in REQUIRED_SLOTS if s not in required]
    assert not missing, f"Missing required slots in schema: {missing}"


def test_schema_properties_include_required_slots() -> None:
    schema = load_pinned_schema()
    properties = schema.get("properties", {})
    for slot in REQUIRED_SLOTS:
        assert slot in properties, (
            f"Slot '{slot}' missing from schema['properties'] — "
            "schema must define the shape of each required slot"
        )
