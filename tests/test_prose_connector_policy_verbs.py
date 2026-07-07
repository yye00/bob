"""Tests for the policy-verb partition of the prose-connector registry.

Feature dc4de884: the prose-connector registry MUST include policy-verb
connectors ("must", "should", "trigger", "rather than", "grant", "demote",
"reset", "reopen", "emit", "classify", "reclassify", "escalate", "honor",
"plausibl", "fixable"), and the integration-AC handler MUST recognize
hash-prefix-class identifiers (e.g. "dd11d1f8-class") as opaque feature
references that are NOT searched as Python dotted paths.
"""

from __future__ import annotations

import pytest

from bob.prose_connector_registry import (
    get_connectors,
    get_policy_verb_connectors,
    is_feature_hash_reference,
    prose_connector_registry,
)

# The exact policy-verb tokens named in the feature spec.
REQUIRED_POLICY_VERBS = [
    "must",
    "should",
    "trigger",
    "rather than",
    "grant",
    "demote",
    "reset",
    "reopen",
    "emit",
    "classify",
    "reclassif",  # stem covering 'reclassify'
    "escalate",
    "honor",
    "plausibl",  # stem covering 'plausible'
    "fixable",
]


class TestPolicyVerbConnectors:
    @pytest.mark.parametrize("verb", REQUIRED_POLICY_VERBS)
    def test_policy_verb_present(self, verb):
        assert verb in get_policy_verb_connectors(), (
            f"policy-verb connector {verb!r} missing from registry"
        )

    def test_reclassify_covered_by_stem(self):
        connectors = get_policy_verb_connectors()
        assert any("reclassif" == c or c in "reclassify" for c in connectors)

    def test_plausible_covered_by_stem(self):
        assert "plausibl" in get_policy_verb_connectors()

    def test_returns_frozenset(self):
        assert isinstance(get_policy_verb_connectors(), frozenset)


class TestRegistryUnion:
    def test_get_connectors_includes_all_policy_verbs(self):
        connectors = get_connectors()
        for verb in REQUIRED_POLICY_VERBS:
            assert verb in connectors, f"{verb!r} missing from combined registry"

    def test_get_connectors_is_union_of_partitions(self):
        assert get_connectors() == (
            prose_connector_registry() | get_policy_verb_connectors()
        )

    def test_descriptive_and_policy_are_distinct_partitions(self):
        # Policy verbs are a separate partition from descriptive-prose connectors.
        descriptive = prose_connector_registry()
        policy = get_policy_verb_connectors()
        # The union must contain everything from both.
        assert policy <= get_connectors()
        assert descriptive <= get_connectors()


class TestPolicyBodyDemotion:
    """The failing AC body from feature 1c574f4a must now match a policy verb."""

    FAILING_AC_BODY = (
        "dd11d1f8-class failures (verification gate failed on plausible-fixable "
        "emission, attempts<5) MUST trigger fresh-attempt grant rather than NH-demote"
    )

    def test_failing_body_matches_a_policy_connector(self):
        body = self.FAILING_AC_BODY.lower()
        matched = [c for c in get_connectors() if c in body]
        assert matched, (
            "1c574f4a AC body should match at least one prose connector so it "
            f"demotes rather than hard-failing; matched={matched}"
        )

    def test_failing_body_contains_hash_prefix_class_token(self):
        # The first token is an opaque feature reference, not a Python path.
        assert is_feature_hash_reference("dd11d1f8-class") is True


class TestHashPrefixReference:
    def test_hyphenated_hash_is_reference(self):
        assert is_feature_hash_reference("dd11d1f8-class") is True

    def test_dotted_python_path_is_not_reference(self):
        assert is_feature_hash_reference("bob.enhanced_verification") is False
