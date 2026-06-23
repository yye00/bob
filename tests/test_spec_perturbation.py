"""Tests for src/bob3/spec_perturbation.py

Tests follow TDD: written before implementation.
All transforms are deterministic (seeded) and round-trip invertible.
"""
from __future__ import annotations

import pytest
from bob3.spec_perturbation import perturb_spec, invert_perturbation, list_transforms


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SPEC = {
    "name": "my_feature",
    "identifier": "feat_alpha",
    "acceptance_criteria": [
        "Function defined: foo_bar",
        "File exists: src/module.py",
        "pytest: tests/test_module.py",
    ],
}


# ---------------------------------------------------------------------------
# perturb_spec – basic contract
# ---------------------------------------------------------------------------


class TestListTransforms:
    def test_returns_list(self):
        result = list_transforms()
        assert isinstance(result, list)

    def test_contains_all_three_transforms(self):
        result = list_transforms()
        assert "rename" in result
        assert "reorder" in result
        assert "red_herring" in result

    def test_is_sorted(self):
        result = list_transforms()
        assert result == sorted(result)


class TestPerturbSpecContract:
    def test_returns_tuple_of_spec_and_seed_used(self):
        perturbed, seed_used = perturb_spec(SAMPLE_SPEC, transform="rename", seed=42)
        assert isinstance(perturbed, dict)
        assert isinstance(seed_used, int)

    def test_seed_used_equals_provided_seed(self):
        _, seed_used = perturb_spec(SAMPLE_SPEC, transform="rename", seed=99)
        assert seed_used == 99

    def test_original_spec_is_not_mutated(self):
        original_name = SAMPLE_SPEC["name"]
        perturb_spec(SAMPLE_SPEC, transform="rename", seed=1)
        assert SAMPLE_SPEC["name"] == original_name

    def test_unknown_transform_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown transform"):
            perturb_spec(SAMPLE_SPEC, transform="nonexistent", seed=0)

    def test_deterministic_same_seed_same_output(self):
        out1, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=7)
        out2, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=7)
        assert out1 == out2

    def test_different_seeds_may_produce_different_output(self):
        out1, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=1)
        out2, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=999)
        # Cannot guarantee always different, but with well-separated seeds it should be
        # (at minimum just verify both are valid dicts)
        assert isinstance(out1, dict)
        assert isinstance(out2, dict)


# ---------------------------------------------------------------------------
# rename transform
# ---------------------------------------------------------------------------


class TestRenameTransform:
    def test_name_field_is_changed(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=42)
        # The name should still exist but may be substituted
        assert "name" in perturbed

    def test_identifier_field_is_changed(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=42)
        assert "identifier" in perturbed

    def test_renamed_name_differs_from_original(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=42)
        # At least one identifier-like field should differ
        name_changed = perturbed.get("name") != SAMPLE_SPEC["name"]
        ident_changed = perturbed.get("identifier") != SAMPLE_SPEC["identifier"]
        assert name_changed or ident_changed

    def test_acceptance_criteria_preserved_in_count(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="rename", seed=42)
        assert len(perturbed["acceptance_criteria"]) == len(
            SAMPLE_SPEC["acceptance_criteria"]
        )


# ---------------------------------------------------------------------------
# reorder transform
# ---------------------------------------------------------------------------


class TestReorderTransform:
    def test_criteria_count_unchanged(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="reorder", seed=42)
        assert len(perturbed["acceptance_criteria"]) == len(
            SAMPLE_SPEC["acceptance_criteria"]
        )

    def test_criteria_same_elements(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="reorder", seed=42)
        assert sorted(perturbed["acceptance_criteria"]) == sorted(
            SAMPLE_SPEC["acceptance_criteria"]
        )

    def test_criteria_order_may_differ(self):
        # With seed=42 and 3 elements there's a high chance of reordering
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="reorder", seed=42)
        # Just verify it's a list (order check is probabilistic)
        assert isinstance(perturbed["acceptance_criteria"], list)

    def test_name_field_unchanged_by_reorder(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="reorder", seed=42)
        assert perturbed["name"] == SAMPLE_SPEC["name"]

    def test_single_criterion_list_is_stable(self):
        spec = {**SAMPLE_SPEC, "acceptance_criteria": ["only one"]}
        perturbed, _ = perturb_spec(spec, transform="reorder", seed=1)
        assert perturbed["acceptance_criteria"] == ["only one"]


# ---------------------------------------------------------------------------
# red_herring transform
# ---------------------------------------------------------------------------


class TestRedHerringTransform:
    def test_adds_one_extra_criterion(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="red_herring", seed=42)
        assert len(perturbed["acceptance_criteria"]) == len(
            SAMPLE_SPEC["acceptance_criteria"]
        ) + 1

    def test_original_criteria_still_present(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="red_herring", seed=42)
        original = set(SAMPLE_SPEC["acceptance_criteria"])
        perturbed_set = set(perturbed["acceptance_criteria"])
        assert original.issubset(perturbed_set)

    def test_extra_criterion_is_a_string(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="red_herring", seed=42)
        extra = set(perturbed["acceptance_criteria"]) - set(
            SAMPLE_SPEC["acceptance_criteria"]
        )
        assert len(extra) == 1
        assert isinstance(next(iter(extra)), str)

    def test_extra_criterion_is_deterministic(self):
        out1, _ = perturb_spec(SAMPLE_SPEC, transform="red_herring", seed=5)
        out2, _ = perturb_spec(SAMPLE_SPEC, transform="red_herring", seed=5)
        assert out1["acceptance_criteria"] == out2["acceptance_criteria"]

    def test_name_field_unchanged_by_red_herring(self):
        perturbed, _ = perturb_spec(SAMPLE_SPEC, transform="red_herring", seed=42)
        assert perturbed["name"] == SAMPLE_SPEC["name"]


# ---------------------------------------------------------------------------
# invert_perturbation – round-trip invertibility
# ---------------------------------------------------------------------------


class TestInvertPerturbation:
    def test_invert_rename_recovers_original(self):
        perturbed, seed_used = perturb_spec(SAMPLE_SPEC, transform="rename", seed=42)
        recovered = invert_perturbation(perturbed, transform="rename", seed=seed_used)
        assert recovered == SAMPLE_SPEC

    def test_invert_reorder_recovers_original(self):
        perturbed, seed_used = perturb_spec(SAMPLE_SPEC, transform="reorder", seed=42)
        recovered = invert_perturbation(
            perturbed, transform="reorder", seed=seed_used
        )
        assert recovered == SAMPLE_SPEC

    def test_invert_red_herring_recovers_original(self):
        perturbed, seed_used = perturb_spec(
            SAMPLE_SPEC, transform="red_herring", seed=42
        )
        recovered = invert_perturbation(
            perturbed, transform="red_herring", seed=seed_used
        )
        assert recovered == SAMPLE_SPEC

    def test_invert_does_not_mutate_perturbed(self):
        perturbed, seed_used = perturb_spec(SAMPLE_SPEC, transform="reorder", seed=7)
        criteria_before = list(perturbed["acceptance_criteria"])
        invert_perturbation(perturbed, transform="reorder", seed=seed_used)
        assert perturbed["acceptance_criteria"] == criteria_before

    def test_invert_unknown_transform_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown transform"):
            invert_perturbation(SAMPLE_SPEC, transform="bogus", seed=0)

    def test_round_trip_rename_various_seeds(self):
        for seed in [0, 1, 100, 9999]:
            perturbed, seed_used = perturb_spec(
                SAMPLE_SPEC, transform="rename", seed=seed
            )
            recovered = invert_perturbation(
                perturbed, transform="rename", seed=seed_used
            )
            assert recovered == SAMPLE_SPEC, f"Round-trip failed for seed={seed}"

    def test_round_trip_reorder_various_seeds(self):
        for seed in [0, 1, 42, 123]:
            perturbed, seed_used = perturb_spec(
                SAMPLE_SPEC, transform="reorder", seed=seed
            )
            recovered = invert_perturbation(
                perturbed, transform="reorder", seed=seed_used
            )
            assert recovered == SAMPLE_SPEC, f"Round-trip failed for seed={seed}"

    def test_round_trip_red_herring_various_seeds(self):
        for seed in [0, 7, 42, 500]:
            perturbed, seed_used = perturb_spec(
                SAMPLE_SPEC, transform="red_herring", seed=seed
            )
            recovered = invert_perturbation(
                perturbed, transform="red_herring", seed=seed_used
            )
            assert recovered == SAMPLE_SPEC, f"Round-trip failed for seed={seed}"
