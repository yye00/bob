"""Tests that F-R7-477/spec.yaml declares two features requiring the missing xxd tool."""

import pathlib
import yaml


SPEC_PATH = pathlib.Path("bob4/research/demonstrators/F-R7-477/spec.yaml")


def test_spec_file_exists():
    assert SPEC_PATH.exists(), f"Demonstrator spec not found at {SPEC_PATH}"


def test_spec_declares_two_features():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    features = spec.get("features", [])
    assert len(features) == 2, f"Expected 2 features, got {len(features)}"


def test_both_features_require_xxd():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    features = spec.get("features", [])
    for feature in features:
        deps = feature.get("deps", {})
        cli_deps = deps.get("cli", [])
        cli_names = [d["name"] for d in cli_deps]
        assert "xxd" in cli_names, (
            f"Feature {feature.get('feature_id')} does not declare xxd as a CLI dep"
        )


def test_both_features_mark_xxd_not_present_in_ci():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    features = spec.get("features", [])
    for feature in features:
        deps = feature.get("deps", {})
        cli_deps = deps.get("cli", [])
        xxd_dep = next((d for d in cli_deps if d["name"] == "xxd"), None)
        assert xxd_dep is not None, (
            f"Feature {feature.get('feature_id')} missing xxd dep entry"
        )
        assert xxd_dep.get("present_in_ci") is False, (
            f"Feature {feature.get('feature_id')} does not mark xxd as absent in CI"
        )


def test_spec_feature_ids():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    features = spec.get("features", [])
    ids = [f.get("feature_id") for f in features]
    assert "F-R7-477a" in ids
    assert "F-R7-477b" in ids


def test_spec_has_notes_about_skill_library():
    spec = yaml.safe_load(SPEC_PATH.read_text())
    notes = spec.get("notes", "")
    assert "skill library" in notes.lower() or "skill_library" in notes.lower(), (
        "spec.yaml notes should mention the skill library purpose"
    )
