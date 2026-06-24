"""Tests for the is_prime demonstrator worktree setup — AC-18."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


DEMO_DIR = Path(__file__).parent.parent / "bob4" / "research" / "demonstrators" / "F-R7-475"
SPEC_PATH = DEMO_DIR / "spec.yaml"


class TestDemoIsPrimeInWorktree:
    def test_spec_yaml_exists(self):
        assert SPEC_PATH.exists(), f"Demonstrator spec not found: {SPEC_PATH}"

    def test_spec_yaml_is_valid_yaml(self):
        content = SPEC_PATH.read_text()
        data = yaml.safe_load(content)
        assert isinstance(data, dict)

    def test_spec_contains_is_prime_feature(self):
        content = SPEC_PATH.read_text()
        assert "is_prime" in content, "Spec must reference is_prime"

    def test_spec_documents_deliberately_weak_tests(self):
        content = SPEC_PATH.read_text()
        assert "deliberately" in content.lower() or "weak" in content.lower(), (
            "Spec must document that test weaknesses are intentional"
        )

    def test_spec_feature_id_present(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        assert "feature_id" in data, "Spec must have a feature_id field"
        assert data["feature_id"] == "F-R7-475"

    def test_spec_has_description(self):
        data = yaml.safe_load(SPEC_PATH.read_text())
        desc = data.get("description", "")
        assert desc, "Spec must have a non-empty description"
        assert "is_prime" in str(desc).lower() or "prime" in str(desc).lower()

    def test_spec_mentions_mutation_gate(self):
        content = SPEC_PATH.read_text()
        assert "mutation" in content.lower(), (
            "Spec should mention mutation testing (it's the gate demonstrator)"
        )

    def test_demo_dir_exists(self):
        assert DEMO_DIR.exists(), f"Demonstrator directory not found: {DEMO_DIR}"
        assert DEMO_DIR.is_dir()
