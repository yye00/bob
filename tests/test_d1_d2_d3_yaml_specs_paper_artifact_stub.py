"""Tests for D1, D2, D3 YAML specification paper artifacts.

Validates that the three benchmark spec YAML files are well-formed,
self-contained, and usable by the sweep orchestrator.
"""

from __future__ import annotations

import pytest
import yaml

from bob3.d1_d2_d3_yaml_specs_paper_artifact_stub import (
    get_d1_spec,
    get_d2_spec,
    get_d3_spec,
    get_all_specs,
    SPEC_D1_YAML,
    SPEC_D2_YAML,
    SPEC_D3_YAML,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse(yaml_str: str) -> dict:
    data = yaml.safe_load(yaml_str)
    assert isinstance(data, dict), "Spec must be a YAML mapping"
    return data


# ---------------------------------------------------------------------------
# D1: nanoGPT / GPT-2 small on OpenWebText
# ---------------------------------------------------------------------------

class TestD1Spec:
    def test_d1_yaml_is_valid(self):
        doc = _parse(SPEC_D1_YAML)
        assert doc  # non-empty

    def test_d1_has_name(self):
        doc = _parse(SPEC_D1_YAML)
        assert "name" in doc
        assert doc["name"]

    def test_d1_has_version(self):
        doc = _parse(SPEC_D1_YAML)
        assert "version" in doc

    def test_d1_has_features(self):
        doc = _parse(SPEC_D1_YAML)
        assert "features" in doc
        assert doc["features"]

    def test_d1_features_have_acceptance_criteria(self):
        doc = _parse(SPEC_D1_YAML)
        for key, feat in doc["features"].items():
            assert "acceptance_criteria" in feat, f"Feature {key} missing acceptance_criteria"
            assert feat["acceptance_criteria"], f"Feature {key} has empty acceptance_criteria"

    def test_d1_acceptance_criteria_use_allowed_prefixes(self):
        doc = _parse(SPEC_D1_YAML)
        allowed = ("File exists:", "pytest:", "Function defined:", "CLI command:", "python:")
        for key, feat in doc["features"].items():
            for ac in feat["acceptance_criteria"]:
                assert any(ac.strip().startswith(p) for p in allowed), (
                    f"D1 feature {key} criterion not machine-verifiable: {ac!r}"
                )

    def test_d1_description_mentions_perplexity(self):
        assert "perplexity" in SPEC_D1_YAML.lower() or "25" in SPEC_D1_YAML

    def test_d1_get_function_returns_dict(self):
        result = get_d1_spec()
        assert isinstance(result, dict)
        assert "name" in result

    def test_d1_domain_is_ml(self):
        doc = _parse(SPEC_D1_YAML)
        domain = doc.get("domain") or doc.get("metadata", {}).get("domain", "")
        assert domain.lower() == "ml"


# ---------------------------------------------------------------------------
# D2: WASM bytecode interpreter (500 ops subset)
# ---------------------------------------------------------------------------

class TestD2Spec:
    def test_d2_yaml_is_valid(self):
        doc = _parse(SPEC_D2_YAML)
        assert doc

    def test_d2_has_name(self):
        doc = _parse(SPEC_D2_YAML)
        assert "name" in doc
        assert doc["name"]

    def test_d2_has_version(self):
        doc = _parse(SPEC_D2_YAML)
        assert "version" in doc

    def test_d2_has_features(self):
        doc = _parse(SPEC_D2_YAML)
        assert "features" in doc
        assert doc["features"]

    def test_d2_features_have_acceptance_criteria(self):
        doc = _parse(SPEC_D2_YAML)
        for key, feat in doc["features"].items():
            assert "acceptance_criteria" in feat, f"Feature {key} missing acceptance_criteria"
            assert feat["acceptance_criteria"], f"Feature {key} has empty acceptance_criteria"

    def test_d2_acceptance_criteria_use_allowed_prefixes(self):
        doc = _parse(SPEC_D2_YAML)
        allowed = ("File exists:", "pytest:", "Function defined:", "CLI command:", "python:")
        for key, feat in doc["features"].items():
            for ac in feat["acceptance_criteria"]:
                assert any(ac.strip().startswith(p) for p in allowed), (
                    f"D2 feature {key} criterion not machine-verifiable: {ac!r}"
                )

    def test_d2_description_mentions_wasm_or_interpreter(self):
        text = SPEC_D2_YAML.lower()
        assert "wasm" in text or "interpreter" in text or "bytecode" in text

    def test_d2_get_function_returns_dict(self):
        result = get_d2_spec()
        assert isinstance(result, dict)
        assert "name" in result

    def test_d2_domain_is_pl(self):
        doc = _parse(SPEC_D2_YAML)
        domain = doc.get("domain") or doc.get("metadata", {}).get("domain", "")
        assert domain.lower() == "pl"


# ---------------------------------------------------------------------------
# D3: Navier-Stokes lid-driven cavity solver
# ---------------------------------------------------------------------------

class TestD3Spec:
    def test_d3_yaml_is_valid(self):
        doc = _parse(SPEC_D3_YAML)
        assert doc

    def test_d3_has_name(self):
        doc = _parse(SPEC_D3_YAML)
        assert "name" in doc
        assert doc["name"]

    def test_d3_has_version(self):
        doc = _parse(SPEC_D3_YAML)
        assert "version" in doc

    def test_d3_has_features(self):
        doc = _parse(SPEC_D3_YAML)
        assert "features" in doc
        assert doc["features"]

    def test_d3_features_have_acceptance_criteria(self):
        doc = _parse(SPEC_D3_YAML)
        for key, feat in doc["features"].items():
            assert "acceptance_criteria" in feat, f"Feature {key} missing acceptance_criteria"
            assert feat["acceptance_criteria"], f"Feature {key} has empty acceptance_criteria"

    def test_d3_acceptance_criteria_use_allowed_prefixes(self):
        doc = _parse(SPEC_D3_YAML)
        allowed = ("File exists:", "pytest:", "Function defined:", "CLI command:", "python:")
        for key, feat in doc["features"].items():
            for ac in feat["acceptance_criteria"]:
                assert any(ac.strip().startswith(p) for p in allowed), (
                    f"D3 feature {key} criterion not machine-verifiable: {ac!r}"
                )

    def test_d3_description_mentions_reynolds_or_cavity(self):
        text = SPEC_D3_YAML.lower()
        assert "reynolds" in text or "cavity" in text or "navier" in text

    def test_d3_get_function_returns_dict(self):
        result = get_d3_spec()
        assert isinstance(result, dict)
        assert "name" in result

    def test_d3_domain_is_hpc(self):
        doc = _parse(SPEC_D3_YAML)
        domain = doc.get("domain") or doc.get("metadata", {}).get("domain", "")
        assert domain.lower() == "hpc"


# ---------------------------------------------------------------------------
# Combined / registry tests
# ---------------------------------------------------------------------------

class TestAllSpecs:
    def test_get_all_specs_returns_three(self):
        specs = get_all_specs()
        assert len(specs) == 3

    def test_all_specs_have_distinct_names(self):
        specs = get_all_specs()
        names = [s["name"] for s in specs]
        assert len(set(names)) == 3, f"Spec names must be unique: {names}"

    def test_all_specs_keys_present(self):
        specs = get_all_specs()
        for spec in specs:
            assert "name" in spec
            assert "version" in spec
            assert "features" in spec

    def test_constants_are_strings(self):
        assert isinstance(SPEC_D1_YAML, str)
        assert isinstance(SPEC_D2_YAML, str)
        assert isinstance(SPEC_D3_YAML, str)
        assert len(SPEC_D1_YAML) > 100
        assert len(SPEC_D2_YAML) > 100
        assert len(SPEC_D3_YAML) > 100

    def test_specs_have_no_tbd_criteria(self):
        for const, label in [(SPEC_D1_YAML, "D1"), (SPEC_D2_YAML, "D2"), (SPEC_D3_YAML, "D3")]:
            doc = yaml.safe_load(const)
            for key, feat in doc["features"].items():
                for ac in feat["acceptance_criteria"]:
                    low = ac.strip().upper()
                    assert not low.startswith("TBD"), (
                        f"{label} feature {key} has TBD criterion: {ac!r}"
                    )
