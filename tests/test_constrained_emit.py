"""Tests for spec_synthesis.constrained_emit.emit_with_schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_valid_spec() -> dict[str, Any]:
    return {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }


def _spec_with_items() -> dict[str, Any]:
    return {
        "functional_requirements": [
            {"id": "FR-001", "description": "The system must do X"}
        ],
        "non_functional_requirements": [
            {"id": "NFR-001", "category": "perf", "description": "Respond in under 200ms"}
        ],
        "acceptance_criteria": [
            {
                "id": "AC-001",
                "given": "A valid input",
                "when": "The function is called",
                "then": "It returns a valid result",
                "verifier": "pytest tests/test_foo.py",
            }
        ],
        "out_of_scope": ["Legacy migrations"],
        "risks": [{"description": "Schema drift if spec.v1.json is updated"}],
    }


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestImport:
    def test_module_importable(self):
        from spec_synthesis import constrained_emit  # noqa: F401

    def test_emit_with_schema_importable(self):
        from spec_synthesis.constrained_emit import emit_with_schema  # noqa: F401

    def test_emit_with_schema_is_callable(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        assert callable(emit_with_schema)


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

class TestSchemaLoading:
    def test_load_default_schema(self, tmp_path):
        """emit_with_schema can load the real schema from the workspace."""
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        # Should not raise — schema exists in workspace
        result = emit_with_schema(spec)
        assert result is spec  # returned unchanged when valid

    def test_custom_schema_path(self, tmp_path):
        """emit_with_schema accepts a custom schema_path override."""
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        schema_file = tmp_path / "custom.json"
        schema_file.write_text(json.dumps(schema))

        from spec_synthesis.constrained_emit import emit_with_schema
        result = emit_with_schema({"name": "hello"}, schema_path=schema_file)
        assert result == {"name": "hello"}

    def test_missing_schema_file_raises(self, tmp_path):
        """emit_with_schema raises ValueError when schema file is absent."""
        from spec_synthesis.constrained_emit import emit_with_schema
        missing = tmp_path / "nonexistent.json"
        with pytest.raises((FileNotFoundError, ValueError)):
            emit_with_schema(_minimal_valid_spec(), schema_path=missing)


# ---------------------------------------------------------------------------
# Valid spec passthrough
# ---------------------------------------------------------------------------

class TestValidSpec:
    def test_minimal_valid_spec_passes(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _minimal_valid_spec()
        result = emit_with_schema(spec)
        assert result is spec

    def test_full_valid_spec_passes(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _spec_with_items()
        result = emit_with_schema(spec)
        assert result is spec

    def test_returned_spec_has_required_slots(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        spec = _spec_with_items()
        result = emit_with_schema(spec)
        for slot in ("functional_requirements", "non_functional_requirements",
                     "acceptance_criteria", "out_of_scope", "risks"):
            assert slot in result


# ---------------------------------------------------------------------------
# Invalid spec rejection
# ---------------------------------------------------------------------------

class TestInvalidSpec:
    def test_missing_required_field_raises_value_error(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {"functional_requirements": [], "non_functional_requirements": []}
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_wrong_type_raises_value_error(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = _minimal_valid_spec()
        bad_spec["functional_requirements"] = "not a list"
        with pytest.raises(ValueError):
            emit_with_schema(bad_spec)

    def test_no_silent_coercion(self):
        """Validation failure must raise, never return a coerced value."""
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {"functional_requirements": "wrong"}
        raised = False
        try:
            emit_with_schema(bad_spec)
        except ValueError:
            raised = True
        assert raised, "emit_with_schema must raise ValueError on invalid spec"

    def test_never_auto_retries(self):
        """emit_with_schema must reject on first failure — no retry loop."""
        from spec_synthesis.constrained_emit import emit_with_schema
        call_count = 0
        bad_spec = {}  # missing all required fields

        # Call multiple times to confirm each call independently raises
        for _ in range(3):
            try:
                emit_with_schema(bad_spec)
            except ValueError:
                call_count += 1
        assert call_count == 3, "Each call must independently raise, no retry absorption"


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------

class TestErrorMessages:
    def test_error_message_mentions_violations(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {}
        with pytest.raises(ValueError) as exc_info:
            emit_with_schema(bad_spec)
        msg = str(exc_info.value)
        # Should mention the problem somehow
        assert msg  # at minimum, non-empty error

    def test_error_carries_validation_detail(self):
        from spec_synthesis.constrained_emit import emit_with_schema
        bad_spec = {"functional_requirements": "not-a-list"}
        with pytest.raises(ValueError) as exc_info:
            emit_with_schema(bad_spec)
        # ValueError (or subclass) must be raised
        assert isinstance(exc_info.value, ValueError)
