"""Tests that the F-R7-475 demonstrator spec.yaml declares an is_prime(n) feature
with deliberately weak tests — as required by AC-13.
"""

from __future__ import annotations

from pathlib import Path

import yaml


SPEC_PATH = Path(__file__).parent.parent / "bob4" / "research" / "demonstrators" / "F-R7-475" / "spec.yaml"


class TestMutationGateDemonstratorIsPrime:
    def test_spec_file_exists(self):
        assert SPEC_PATH.exists(), f"spec.yaml not found at {SPEC_PATH}"

    def test_spec_is_valid_yaml(self):
        spec = yaml.safe_load(SPEC_PATH.read_text())
        assert isinstance(spec, dict), "spec.yaml must parse to a dict"

    def test_spec_declares_is_prime_function(self):
        spec = yaml.safe_load(SPEC_PATH.read_text())
        # Check that the spec references is_prime somewhere
        spec_text = SPEC_PATH.read_text()
        assert "is_prime" in spec_text, "spec.yaml must reference the is_prime function"

    def test_spec_declares_deliberately_weak_tests(self):
        spec = yaml.safe_load(SPEC_PATH.read_text())
        spec_text = SPEC_PATH.read_text()
        assert "deliberately" in spec_text.lower() or "weak" in spec_text.lower(), (
            "spec.yaml must document that the tests are deliberately weak"
        )

    def test_spec_feature_id_is_f_r7_475(self):
        spec = yaml.safe_load(SPEC_PATH.read_text())
        assert spec.get("feature_id") == "F-R7-475", (
            f"Expected feature_id='F-R7-475', got {spec.get('feature_id')!r}"
        )

    def test_spec_has_acceptance_criteria(self):
        spec = yaml.safe_load(SPEC_PATH.read_text())
        acs = spec.get("acceptance_criteria", [])
        assert len(acs) > 0, "spec.yaml must have at least one acceptance criterion"

    def test_spec_mentions_is_prime_n(self):
        spec_text = SPEC_PATH.read_text()
        assert "is_prime(n)" in spec_text, "spec.yaml must mention the is_prime(n) signature"
