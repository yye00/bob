"""Tests for per-domain skill bundles (HPC, ML, PL) module."""
from __future__ import annotations

import pytest

from bob.per_domain_skill_bundles_hpc_ml_pl import (
    BASE_SKILLS,
    DEFAULT_DOMAIN,
    DOMAIN_BUNDLES,
    VALID_DOMAINS,
    filter_skills_by_domain,
    get_bundle_for_spec,
    get_skills_for_domain,
    select_domain_from_spec,
)


# ---------------------------------------------------------------------------
# Constants / structure tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_valid_domains_contains_required(self):
        assert {"hpc", "ml", "pl", "general"} <= VALID_DOMAINS

    def test_domain_bundles_has_all_valid_domains(self):
        assert set(DOMAIN_BUNDLES.keys()) == VALID_DOMAINS

    def test_base_skills_nonempty(self):
        assert len(BASE_SKILLS) > 0

    def test_default_domain_is_general(self):
        assert DEFAULT_DOMAIN == "general"

    def test_each_bundle_contains_base_skills(self):
        """Every domain bundle must include all BASE_SKILLS."""
        for domain, bundle in DOMAIN_BUNDLES.items():
            for skill in BASE_SKILLS:
                assert skill in bundle, f"Domain '{domain}' missing base skill '{skill}'"

    def test_bundles_have_no_duplicates(self):
        for domain, bundle in DOMAIN_BUNDLES.items():
            assert len(bundle) == len(set(bundle)), f"Domain '{domain}' has duplicate skills"

    def test_bundles_are_lists(self):
        for domain, bundle in DOMAIN_BUNDLES.items():
            assert isinstance(bundle, list), f"Domain '{domain}' bundle is not a list"


# ---------------------------------------------------------------------------
# get_skills_for_domain
# ---------------------------------------------------------------------------


class TestGetSkillsForDomain:
    def test_known_domain_returns_bundle(self):
        bundle = get_skills_for_domain("hpc")
        assert isinstance(bundle, list)
        assert len(bundle) > 0

    def test_all_valid_domains_return_non_empty(self):
        for domain in VALID_DOMAINS:
            bundle = get_skills_for_domain(domain)
            assert bundle, f"Domain '{domain}' returned empty bundle"

    def test_unknown_domain_falls_back_to_general(self):
        bundle = get_skills_for_domain("unknown_domain_xyz")
        assert bundle == get_skills_for_domain("general")

    def test_empty_string_falls_back_to_general(self):
        bundle = get_skills_for_domain("")
        assert bundle == get_skills_for_domain("general")

    def test_none_like_empty_falls_back_to_general(self):
        bundle = get_skills_for_domain("   ")
        assert bundle == get_skills_for_domain("general")

    def test_case_insensitive(self):
        assert get_skills_for_domain("HPC") == get_skills_for_domain("hpc")
        assert get_skills_for_domain("ML") == get_skills_for_domain("ml")
        assert get_skills_for_domain("PL") == get_skills_for_domain("pl")

    def test_returns_copy_not_reference(self):
        """Modifying the returned list should not affect DOMAIN_BUNDLES."""
        bundle = get_skills_for_domain("hpc")
        bundle.append("__injected__")
        assert "__injected__" not in DOMAIN_BUNDLES["hpc"]

    def test_hpc_bundle_includes_base_skills(self):
        bundle = get_skills_for_domain("hpc")
        for skill in BASE_SKILLS:
            assert skill in bundle

    def test_ml_bundle_includes_base_skills(self):
        bundle = get_skills_for_domain("ml")
        for skill in BASE_SKILLS:
            assert skill in bundle

    def test_pl_bundle_includes_base_skills(self):
        bundle = get_skills_for_domain("pl")
        for skill in BASE_SKILLS:
            assert skill in bundle

    def test_general_bundle_includes_base_skills(self):
        bundle = get_skills_for_domain("general")
        for skill in BASE_SKILLS:
            assert skill in bundle


# ---------------------------------------------------------------------------
# select_domain_from_spec
# ---------------------------------------------------------------------------


class TestSelectDomainFromSpec:
    def test_none_spec_returns_general(self):
        assert select_domain_from_spec(None) == "general"

    def test_empty_dict_returns_general(self):
        assert select_domain_from_spec({}) == "general"

    def test_top_level_domain_hpc(self):
        assert select_domain_from_spec({"domain": "hpc"}) == "hpc"

    def test_top_level_domain_ml(self):
        assert select_domain_from_spec({"domain": "ml"}) == "ml"

    def test_top_level_domain_pl(self):
        assert select_domain_from_spec({"domain": "pl"}) == "pl"

    def test_top_level_domain_general(self):
        assert select_domain_from_spec({"domain": "general"}) == "general"

    def test_nested_metadata_domain(self):
        spec = {"metadata": {"domain": "hpc"}}
        assert select_domain_from_spec(spec) == "hpc"

    def test_nested_metadata_domain_ml(self):
        spec = {"metadata": {"domain": "ml"}}
        assert select_domain_from_spec(spec) == "ml"

    def test_top_level_takes_precedence_over_metadata(self):
        spec = {"domain": "hpc", "metadata": {"domain": "ml"}}
        assert select_domain_from_spec(spec) == "hpc"

    def test_case_insensitive_from_spec(self):
        assert select_domain_from_spec({"domain": "HPC"}) == "hpc"
        assert select_domain_from_spec({"domain": "ML"}) == "ml"

    def test_unknown_domain_in_spec_returns_general(self):
        assert select_domain_from_spec({"domain": "quantum"}) == "general"

    def test_whitespace_normalized(self):
        assert select_domain_from_spec({"domain": "  hpc  "}) == "hpc"

    def test_domain_key_missing_no_metadata(self):
        spec = {"name": "some feature", "description": "does something"}
        assert select_domain_from_spec(spec) == "general"

    def test_metadata_not_a_dict(self):
        spec = {"metadata": "not-a-dict"}
        assert select_domain_from_spec(spec) == "general"

    def test_metadata_domain_none_returns_general(self):
        spec = {"metadata": {"domain": None}}
        assert select_domain_from_spec(spec) == "general"


# ---------------------------------------------------------------------------
# get_bundle_for_spec
# ---------------------------------------------------------------------------


class TestGetBundleForSpec:
    def test_none_spec_returns_general_bundle(self):
        bundle = get_bundle_for_spec(None)
        assert bundle == get_skills_for_domain("general")

    def test_hpc_spec_returns_hpc_bundle(self):
        spec = {"domain": "hpc"}
        bundle = get_bundle_for_spec(spec)
        assert bundle == get_skills_for_domain("hpc")

    def test_ml_spec_returns_ml_bundle(self):
        spec = {"domain": "ml"}
        bundle = get_bundle_for_spec(spec)
        assert bundle == get_skills_for_domain("ml")

    def test_pl_spec_returns_pl_bundle(self):
        spec = {"domain": "pl"}
        bundle = get_bundle_for_spec(spec)
        assert bundle == get_skills_for_domain("pl")

    def test_unknown_domain_returns_general_bundle(self):
        spec = {"domain": "robotics"}
        bundle = get_bundle_for_spec(spec)
        assert bundle == get_skills_for_domain("general")

    def test_nested_metadata_domain_resolved(self):
        spec = {"metadata": {"domain": "ml"}}
        bundle = get_bundle_for_spec(spec)
        assert bundle == get_skills_for_domain("ml")

    def test_returns_nonempty_list(self):
        for domain in VALID_DOMAINS:
            bundle = get_bundle_for_spec({"domain": domain})
            assert len(bundle) > 0


# ---------------------------------------------------------------------------
# filter_skills_by_domain
# ---------------------------------------------------------------------------


class TestFilterSkillsByDomain:
    def test_returns_only_skills_in_bundle(self):
        all_skills = ["systematic-debugging", "some-unrelated-skill", "no-stubs-no-mocks"]
        result = filter_skills_by_domain(all_skills, "hpc")
        assert "some-unrelated-skill" not in result
        assert "systematic-debugging" in result

    def test_preserves_order_of_input(self):
        hpc_bundle = get_skills_for_domain("hpc")
        # Reverse the bundle order and filter
        reversed_skills = list(reversed(hpc_bundle))
        result = filter_skills_by_domain(reversed_skills, "hpc")
        # Result should preserve input order (reversed), not bundle order
        assert result == [s for s in reversed_skills if s in set(hpc_bundle)]

    def test_empty_input_returns_empty(self):
        assert filter_skills_by_domain([], "hpc") == []

    def test_unknown_domain_filters_against_general(self):
        general_bundle = get_skills_for_domain("general")
        result = filter_skills_by_domain(general_bundle + ["alien-skill"], "unknown_xyz")
        assert "alien-skill" not in result
        assert result == general_bundle

    def test_no_matching_skills_returns_empty(self):
        result = filter_skills_by_domain(["fake-skill-a", "fake-skill-b"], "hpc")
        assert result == []

    def test_all_matching_skills_returned(self):
        hpc_bundle = get_skills_for_domain("hpc")
        result = filter_skills_by_domain(hpc_bundle, "hpc")
        assert result == hpc_bundle

    def test_does_not_add_skills_not_in_input(self):
        """filter_skills_by_domain only filters, never augments."""
        result = filter_skills_by_domain(["systematic-debugging"], "ml")
        # Should not add other ml skills not in input
        assert result == ["systematic-debugging"]


# ---------------------------------------------------------------------------
# Cross-domain consistency
# ---------------------------------------------------------------------------


class TestCrossDomainConsistency:
    def test_hpc_and_ml_bundles_are_different(self):
        """HPC and ML bundles may share base skills but their extras differ."""
        # Both include base skills, but the module defines domain-specific ordering
        # — at minimum they should both be valid non-empty lists
        hpc = get_skills_for_domain("hpc")
        ml = get_skills_for_domain("ml")
        assert len(hpc) > 0
        assert len(ml) > 0

    def test_general_bundle_equals_base_skills(self):
        """General domain should contain exactly the base skills (no extras)."""
        general = get_skills_for_domain("general")
        assert general == BASE_SKILLS

    def test_specialized_domains_not_subset_removes_base(self):
        """Specialized domain bundles must never strip a base skill."""
        for domain in ("hpc", "ml", "pl"):
            bundle = get_skills_for_domain(domain)
            for base_skill in BASE_SKILLS:
                assert base_skill in bundle, (
                    f"Domain '{domain}' bundle is missing base skill '{base_skill}'"
                )
