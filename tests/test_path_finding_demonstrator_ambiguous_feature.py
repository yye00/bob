"""Tests that F-R7-474 spec.yaml declares a deliberately ambiguous feature for path-finding demo."""

import pathlib

import pytest
import yaml


SPEC_PATH = pathlib.Path(__file__).parent.parent / "bob4" / "research" / "demonstrators" / "F-R7-474" / "spec.yaml"


def _load_spec() -> dict:
    assert SPEC_PATH.exists(), f"Demonstrator spec not found: {SPEC_PATH}"
    return yaml.safe_load(SPEC_PATH.read_text())


def test_spec_file_exists():
    assert SPEC_PATH.exists(), f"F-R7-474 spec.yaml not found at {SPEC_PATH}"


def test_spec_has_feature_id():
    spec = _load_spec()
    assert "feature_id" in spec
    assert spec["feature_id"] == "F-R7-474"


def test_spec_declares_ambiguous_feature():
    """Spec is explicitly a deliberately ambiguous feature for path-finding demo."""
    spec = _load_spec()
    description = (spec.get("description") or "").lower()
    assert "ambiguous" in description, (
        "Spec description must state it is deliberately ambiguous for path-finding demo"
    )


def test_spec_has_acceptance_criteria():
    spec = _load_spec()
    assert "acceptance_criteria" in spec
    assert len(spec["acceptance_criteria"]) >= 1


def test_spec_ac_contains_ambiguous_language():
    """At least one AC must contain vague/ambiguous language markers."""
    spec = _load_spec()
    ambiguity_markers = spec.get("ambiguity_markers", [])
    ac_text = " ".join(str(ac) for ac in spec["acceptance_criteria"]).lower()
    # Either explicit ambiguity_markers or AC text contains known ambiguous phrases
    if ambiguity_markers:
        for marker in ambiguity_markers:
            assert marker.lower() in ac_text, (
                f"Ambiguity marker {marker!r} declared in spec but not found in AC text"
            )
    else:
        vague_words = ["somehow", "appropriate", "best", "as needed", "unclear", "ambiguous"]
        found = [w for w in vague_words if w in ac_text]
        assert found, (
            f"No ambiguous language found in AC text. Expected one of: {vague_words}"
        )


def test_spec_has_notes_mentioning_demonstrator():
    spec = _load_spec()
    notes = (spec.get("notes") or "").lower()
    assert "demonstrator" in notes, "Spec notes must indicate this is a demonstrator spec only"


def test_spec_not_for_build_loop():
    """Spec notes must clarify it's NOT meant for the build loop."""
    spec = _load_spec()
    notes = (spec.get("notes") or "").lower()
    assert "not" in notes and ("build loop" in notes or "implement" in notes), (
        "Spec notes must clarify it is not for production build loop implementation"
    )
