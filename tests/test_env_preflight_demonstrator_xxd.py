"""Test: F-R7-473 demonstrator spec declares xxd as a dep.

Asserts that bob4/research/demonstrators/F-R7-473/spec.yaml exists and declares
a feature whose deps include the deliberately-absent CLI xxd.
"""
import pathlib

import yaml

SPEC_PATH = pathlib.Path("bob4/research/demonstrators/F-R7-473/spec.yaml")


def test_demonstrator_spec_exists():
    assert SPEC_PATH.exists(), f"Expected spec file at {SPEC_PATH}"


def test_demonstrator_spec_is_valid_yaml():
    content = SPEC_PATH.read_text()
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "spec.yaml must be a YAML mapping"


def test_demonstrator_spec_has_feature_id():
    data = yaml.safe_load(SPEC_PATH.read_text())
    assert "feature_id" in data, "spec.yaml must have a feature_id field"
    assert data["feature_id"] == "F-R7-473"


def test_demonstrator_spec_declares_xxd_cli_dep():
    """The spec must declare xxd as a CLI dependency."""
    data = yaml.safe_load(SPEC_PATH.read_text())
    deps = data.get("deps", {})
    cli_deps = deps.get("cli", [])
    cli_names = [d["name"] if isinstance(d, dict) else d for d in cli_deps]
    assert "xxd" in cli_names, (
        f"Expected xxd in cli deps, got: {cli_names}"
    )


def test_demonstrator_spec_xxd_not_present_in_ci():
    """xxd should be marked as absent in CI environments."""
    data = yaml.safe_load(SPEC_PATH.read_text())
    cli_deps = data.get("deps", {}).get("cli", [])
    xxd_entry = next((d for d in cli_deps if isinstance(d, dict) and d.get("name") == "xxd"), None)
    assert xxd_entry is not None, "xxd entry not found in cli deps"
    assert xxd_entry.get("present_in_ci") is False, (
        "xxd should be marked present_in_ci: false"
    )


def test_demonstrator_spec_xxd_has_workaround():
    """xxd entry must include a workaround string."""
    data = yaml.safe_load(SPEC_PATH.read_text())
    cli_deps = data.get("deps", {}).get("cli", [])
    xxd_entry = next((d for d in cli_deps if isinstance(d, dict) and d.get("name") == "xxd"), None)
    assert xxd_entry is not None
    assert "workaround" in xxd_entry, "xxd entry must have a workaround field"
    assert len(xxd_entry["workaround"]) > 0, "workaround must not be empty"


def test_demonstrator_spec_acceptance_criteria_mention_xxd():
    """At least one AC in the spec references xxd."""
    data = yaml.safe_load(SPEC_PATH.read_text())
    acs = data.get("acceptance_criteria", [])
    xxd_acs = [ac for ac in acs if "xxd" in str(ac)]
    assert len(xxd_acs) >= 1, (
        "Expected at least one AC mentioning xxd"
    )
