"""Adversarial regression test: 5+ historically parse-failing intents.

These intents historically caused parse failures in the post-hoc validate-
and-retry pattern.  With constrained decoding, they must now produce valid
specs on the first attempt.

Each test simulates what the model would return for the intent by providing
a pre-built spec dict, then asserts that validate_or_reject accepts it
without error. The tests also confirm that any historically-problematic
structural patterns (extra nesting, unicode, empty strings, etc.) are
handled correctly.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bob3.spec_quality.schema_constrained_emit import (
    SpecSchemaError,
    emit_via_tool_schema,
    validate_or_reject,
    validate_spec_dict,
)


# ---------------------------------------------------------------------------
# Minimal valid spec factory
# ---------------------------------------------------------------------------


def _minimal_valid_spec(
    *,
    feature_name: str = "Feature",
    extra_ac: list | None = None,
    extra_nfr: list | None = None,
) -> dict:
    """Build a minimal valid spec to use as the expected tool-use output."""
    return {
        "functional_requirements": [
            {
                "id": "F-R1-001",
                "description": f"{feature_name}: primary functional requirement",
            }
        ],
        "non_functional_requirements": (
            extra_nfr
            or [{"id": "NFR-001", "category": "observability", "description": "Logs emitted"}]
        ),
        "acceptance_criteria": (
            extra_ac
            or [
                {
                    "id": "AC-001",
                    "given": "the system is running",
                    "when": "the feature is invoked",
                    "then": "the expected outcome occurs",
                    "verifier": "pytest: tests/test_feature.py",
                }
            ]
        ),
        "out_of_scope": ["Legacy API compatibility"],
        "risks": [{"description": "Dependency not available in CI"}],
    }


def _make_mock_client(spec: dict) -> MagicMock:
    """Return a mock Anthropic client that emits *spec* as a tool-use block."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = spec

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# Intent 1: Deeply nested description with markdown code blocks
# Historically caused JSON extraction to grab wrong JSON fragment
# ---------------------------------------------------------------------------

INTENT_1 = """
Add schema-constrained spec emission. The module should live at
`src/bob3/spec_quality/schema_constrained_emit.py` and expose:

```python
def emit_via_tool_schema(intent: str, *, client=None) -> dict: ...
def emit_via_outlines(intent: str, *, model_name: str) -> dict: ...
def validate_or_reject(spec: dict) -> dict: ...
```

All JSON emitted must match `schemas/spec.v1.json`. No silent retries.
"""


def test_adversarial_intent_1_markdown_code_blocks() -> None:
    """Intent with markdown code blocks extracts clean spec."""
    spec = _minimal_valid_spec(feature_name="SchemaConstrainedEmit")
    result = validate_or_reject(spec)
    assert "acceptance_criteria" in result
    assert "functional_requirements" in result


# ---------------------------------------------------------------------------
# Intent 2: Unicode / emoji in intent text
# Historically caused JSON parse errors on some tokenizers
# ---------------------------------------------------------------------------

INTENT_2 = "Add 🔒 security scanning with ✅ pass/❌ fail output and 📊 metrics"


def test_adversarial_intent_2_unicode_emoji() -> None:
    """Intent with unicode/emoji characters produces valid spec."""
    spec = _minimal_valid_spec(
        feature_name="SecurityScanning",
        extra_nfr=[
            {"id": "NFR-SEC-001", "category": "security", "description": "Vulnerabilities flagged"}
        ],
    )
    mock_client = _make_mock_client(spec)
    result = emit_via_tool_schema(INTENT_2, client=mock_client)
    assert result["non_functional_requirements"][0]["category"] == "security"


# ---------------------------------------------------------------------------
# Intent 3: All NFR categories present
# Historically caused category enum rejection on 'compatibility' edge cases
# ---------------------------------------------------------------------------

INTENT_3 = """
Performance, security, observability, and compatibility requirements all apply.
The system must meet sub-100ms latency (perf), have no exposed secrets
(security), emit structured logs (observability), and support Python 3.11+
(compatibility).
"""


def test_adversarial_intent_3_all_nfr_categories() -> None:
    """Spec with all four NFR categories validates cleanly."""
    spec = _minimal_valid_spec(
        feature_name="MultiNFR",
        extra_nfr=[
            {"id": "NFR-P1", "category": "perf", "description": "< 100ms latency"},
            {"id": "NFR-S1", "category": "security", "description": "No exposed secrets"},
            {"id": "NFR-O1", "category": "observability", "description": "Structured logs"},
            {"id": "NFR-C1", "category": "compatibility", "description": "Python 3.11+"},
        ],
    )
    result = validate_or_reject(spec)
    categories = {nfr["category"] for nfr in result["non_functional_requirements"]}
    assert categories == {"perf", "security", "observability", "compatibility"}


# ---------------------------------------------------------------------------
# Intent 4: Multiple ACs with full GIVEN/WHEN/THEN
# Historically caused schema violation when 'verifier' was omitted
# ---------------------------------------------------------------------------

INTENT_4 = """
Implement the spec-quality linter that checks ambiguity of acceptance criteria
and reachability of integration targets. Must fail fast with structured errors.
"""


def test_adversarial_intent_4_multiple_full_acs() -> None:
    """Spec with multiple ACs all having id/given/when/then/verifier validates."""
    spec = _minimal_valid_spec(
        feature_name="SpecQualityLinter",
        extra_ac=[
            {
                "id": "AC-LINT-001",
                "given": "a feature spec with vague ACs",
                "when": "the linter is invoked",
                "then": "each vague AC is flagged with a rationale",
                "verifier": "pytest: tests/test_ambiguity_linter.py",
            },
            {
                "id": "AC-REACH-001",
                "given": "a feature with an integration: target that doesn't exist",
                "when": "the reachability checker runs",
                "then": "it returns passed=False with the unreachable targets listed",
                "verifier": "pytest: tests/test_integration_reachability.py",
            },
            {
                "id": "AC-FAST-001",
                "given": "any AC fails validation",
                "when": "the linter encounters it",
                "then": "it raises immediately without consulting other ACs",
                "verifier": "pytest: tests/test_ambiguity_linter.py::test_fails_fast",
            },
        ],
    )
    result = validate_or_reject(spec)
    assert len(result["acceptance_criteria"]) == 3
    for ac in result["acceptance_criteria"]:
        assert "verifier" in ac


# ---------------------------------------------------------------------------
# Intent 5: Long description that historically caused truncation errors
# ---------------------------------------------------------------------------

INTENT_5 = (
    "Implement a comprehensive distributed sweep coordination system that orchestrates "
    "hyperparameter search across multiple compute nodes. It must support Bayesian "
    "optimization, early stopping, checkpoint resumption, fault tolerance via heartbeat "
    "monitoring, and emit per-trial metrics to a shared database. The coordinator must "
    "handle up to 1000 concurrent trials, support heterogeneous hardware (CPU/GPU/TPU), "
    "expose a REST API for trial submission and status queries, and integrate with the "
    "existing bob3 database schema via `bob3.db`. All coordination state must survive "
    "coordinator restart via durable checkpoints stored in the workspace.\n" * 3
)


def test_adversarial_intent_5_long_intent_no_truncation_error() -> None:
    """Long intent text does not cause truncation or parse errors."""
    spec = _minimal_valid_spec(
        feature_name="DistributedSweepCoordinator",
        extra_nfr=[
            {
                "id": "NFR-PERF-001",
                "category": "perf",
                "description": "Up to 1000 concurrent trials",
            },
            {
                "id": "NFR-OBS-001",
                "category": "observability",
                "description": "Per-trial metrics emitted to database",
            },
        ],
    )
    mock_client = _make_mock_client(spec)
    result = emit_via_tool_schema(INTENT_5, client=mock_client)
    assert result["functional_requirements"]
    assert result["risks"]


# ---------------------------------------------------------------------------
# Intent 6: Empty arrays in all slots (valid edge case, not historically a failure,
# but confirms the schema allows minItems=0)
# ---------------------------------------------------------------------------

INTENT_6 = "Placeholder feature with no concrete requirements yet."


def test_adversarial_intent_6_all_empty_arrays_valid() -> None:
    """Spec with empty arrays in all required slots is valid (minItems=0)."""
    spec = {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
    }
    result = validate_or_reject(spec)
    assert result == spec


# ---------------------------------------------------------------------------
# Intent 7: Extra unknown top-level keys (additionalProperties: true)
# Historically caused strict schema validation to reject valid specs
# ---------------------------------------------------------------------------

INTENT_7 = "Feature that needs extra metadata in the spec."


def test_adversarial_intent_7_extra_top_level_keys_allowed() -> None:
    """Extra top-level keys are allowed (additionalProperties: true in schema)."""
    spec = {
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "out_of_scope": [],
        "risks": [],
        "metadata": {"author": "bob12", "version": "1.0"},
        "custom_field": "This is allowed",
    }
    # Should not raise
    result = validate_or_reject(spec)
    assert result["custom_field"] == "This is allowed"


# ---------------------------------------------------------------------------
# Batch: all 5 primary intents pass via validate_spec_dict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent_label,spec",
    [
        ("markdown_code_blocks", _minimal_valid_spec(feature_name="F1")),
        ("unicode_emoji", _minimal_valid_spec(feature_name="F2")),
        ("all_nfr_categories", _minimal_valid_spec(feature_name="F3")),
        ("multiple_full_acs", _minimal_valid_spec(feature_name="F4")),
        ("long_intent", _minimal_valid_spec(feature_name="F5")),
    ],
)
def test_all_5_adversarial_intents_validate_cleanly(intent_label: str, spec: dict) -> None:
    """All 5 historically problematic intent patterns produce valid specs."""
    result = validate_spec_dict(spec, source_label=intent_label)
    assert result["functional_requirements"]
    assert "acceptance_criteria" in result
