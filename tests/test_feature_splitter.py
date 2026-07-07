"""Tests for bob.feature_splitter — split oversized features + pin packages."""

from __future__ import annotations

import pytest

from bob import spec_extractor
from bob.feature_splitter import (
    SplitRecommendation,
    SubFeature,
    pin_canonical_package,
    recommend_split,
)


# ---------------------------------------------------------------------------
# recommend_split
# ---------------------------------------------------------------------------

def test_oversized_multi_module_feature_recommends_split():
    """A feature enumerating 3 entry points across 3 modules is split."""
    feature = {
        "name": "Statistics",
        "acceptance_criteria": [
            "Function defined: hippy.statistics.percentile",
            "Function defined: hippy.concatenate.concatenate",
            "Function defined: hippy.polynomial.polyfit",
            "pytest: tests/test_statistics.py",
        ],
    }
    rec = recommend_split(feature)
    assert isinstance(rec, SplitRecommendation)
    assert rec.should_split is True
    assert rec.num_modules == 3
    assert rec.num_entry_points == 3
    assert len(rec.sub_features) == 3
    assert all(isinstance(sf, SubFeature) for sf in rec.sub_features)


def test_split_groups_acs_by_module():
    """Each sub-feature groups the ACs targeting one module."""
    feature = {
        "name": "sparse",
        "acceptance_criteria": [
            "Function defined: hipsci.sparse.spmv",
            "Function defined: hipsci.sparse.spmm",
            "Function defined: hipsci.construction.build",
        ],
    }
    rec = recommend_split(feature)
    modules = {sf.module for sf in rec.sub_features}
    assert modules == {"hipsci.sparse", "hipsci.construction"}
    sparse = next(sf for sf in rec.sub_features if sf.module == "hipsci.sparse")
    assert len(sparse.acceptance_criteria) == 2


def test_split_emits_dependency_chain():
    """Sub-features carry an explicit linear dependency chain."""
    feature = {
        "name": "fft",
        "acceptance_criteria": [
            "Function defined: hippy.fft.fft",
            "Function defined: hippy.dct.dct",
            "Function defined: hippy.dst.dst",
        ],
    }
    rec = recommend_split(feature)
    # First sub-feature has no deps; subsequent ones depend on the previous.
    assert rec.sub_features[0].depends_on == []
    for prev, cur in zip(rec.sub_features, rec.sub_features[1:]):
        assert cur.depends_on == [prev.module]


def test_single_module_feature_not_split():
    """A feature confined to one module is left intact even with many entry points."""
    feature = {
        "name": "linalg",
        "acceptance_criteria": [
            "Function defined: hippy.linalg.solve",
            "Function defined: hippy.linalg.inv",
            "Function defined: hippy.linalg.det",
        ],
    }
    rec = recommend_split(feature)
    assert rec.should_split is False
    assert rec.num_modules == 1
    assert rec.sub_features == []


def test_too_few_entry_points_not_split():
    """A feature with only 2 entry points across 2 modules is not split."""
    feature = {
        "name": "small",
        "acceptance_criteria": [
            "Function defined: hippy.a.foo",
            "Function defined: hippy.b.bar",
        ],
    }
    rec = recommend_split(feature)
    assert rec.should_split is False


def test_class_defined_counts_as_entry_point():
    """Class defined: ACs are counted as independent entry points."""
    feature = {
        "name": "mixed",
        "acceptance_criteria": [
            "Class defined: hippy.tensor.Tensor",
            "Function defined: hippy.random.rand",
            "Function defined: hippy.io.load",
        ],
    }
    rec = recommend_split(feature)
    assert rec.num_entry_points == 3
    assert rec.should_split is True


def test_file_exists_source_counts_but_tests_do_not():
    """Source File-exists ACs count as entry points; test paths do not."""
    feature = {
        "name": "files",
        "acceptance_criteria": [
            "File exists: src/hippy/alpha.py",
            "File exists: src/hippy/beta.py",
            "File exists: src/hippy/gamma.py",
            "File exists: tests/test_files.py",
        ],
    }
    rec = recommend_split(feature)
    assert rec.num_entry_points == 3  # test file excluded
    assert rec.should_split is True


def test_pytest_only_feature_not_split():
    """A feature whose ACs are only pytest paths has zero entry points."""
    feature = {
        "name": "just_tests",
        "acceptance_criteria": [
            "pytest: tests/test_a.py",
            "pytest: tests/test_b.py",
        ],
    }
    rec = recommend_split(feature)
    assert rec.num_entry_points == 0
    assert rec.should_split is False


def test_reason_populated_when_split():
    """A recommended split includes a human-readable reason."""
    feature = {
        "name": "Statistics",
        "acceptance_criteria": [
            "Function defined: hippy.a.f1",
            "Function defined: hippy.b.f2",
            "Function defined: hippy.c.f3",
        ],
    }
    rec = recommend_split(feature)
    assert "Statistics" in rec.reason
    assert "split" in rec.reason.lower()


# ---------------------------------------------------------------------------
# pin_canonical_package
# ---------------------------------------------------------------------------

def test_pin_rewrites_leaked_workspace_package_in_file_path():
    """A src/dark_factory/ path is rewritten onto the canonical package."""
    acs = ["File exists: src/dark_factory/statistics.py"]
    out = pin_canonical_package(acs, "hippy")
    assert out == ["File exists: src/hippy/statistics.py"]


def test_pin_rewrites_function_defined_module():
    """A Function defined: dark_factory.x.y AC is pinned to canonical."""
    acs = ["Function defined: dark_factory.statistics.percentile"]
    out = pin_canonical_package(acs, "hippy")
    assert out == ["Function defined: hippy.statistics.percentile"]


def test_pin_leaves_canonical_paths_untouched():
    """Already-canonical ACs pass through unchanged."""
    acs = [
        "File exists: src/hippy/statistics.py",
        "Function defined: hippy.statistics.percentile",
    ]
    out = pin_canonical_package(acs, "hippy")
    assert out == acs


def test_pin_leaves_tests_and_pytest_untouched():
    """tests/ paths and pytest ACs are not rewritten."""
    acs = [
        "pytest: tests/test_statistics.py",
        "File exists: tests/test_statistics.py",
    ]
    out = pin_canonical_package(acs, "hippy")
    assert out == acs


def test_pin_accepts_multiple_canonical_packages():
    """When several canonical packages are given, hipsci stays, others map to first."""
    acs = [
        "Function defined: hipsci.sparse.spmv",
        "Function defined: dark_factory.foo.bar",
    ]
    out = pin_canonical_package(acs, ["hippy", "hipsci"])
    assert out[0] == "Function defined: hipsci.sparse.spmv"
    assert out[1] == "Function defined: hippy.foo.bar"


def test_pin_rewrites_integration_ac():
    """integration: ACs are pinned onto the canonical package."""
    acs = ["integration: dark_factory.spec_extractor"]
    out = pin_canonical_package(acs, "hippy")
    assert out == ["integration: hippy.spec_extractor"]


def test_pin_on_feature_dict_returns_copy():
    """Passing a feature dict rewrites acceptance_criteria in a copy."""
    feature = {
        "name": "stats",
        "acceptance_criteria": ["File exists: src/dark_factory/a.py"],
    }
    out = pin_canonical_package(feature, "hippy")
    assert out["acceptance_criteria"] == ["File exists: src/hippy/a.py"]
    # original untouched
    assert feature["acceptance_criteria"] == ["File exists: src/dark_factory/a.py"]


def test_pin_accepts_comma_separated_string():
    """A comma-separated package string is parsed correctly."""
    acs = ["Function defined: dark_factory.x.y"]
    out = pin_canonical_package(acs, "hippy, hipsci")
    assert out == ["Function defined: hippy.x.y"]


# ---------------------------------------------------------------------------
# integration: bob.spec_extractor re-exports
# ---------------------------------------------------------------------------

def test_spec_extractor_reexports_feature_splitter_api():
    """recommend_split and pin_canonical_package are importable from spec_extractor."""
    assert spec_extractor.recommend_split is recommend_split
    assert spec_extractor.pin_canonical_package is pin_canonical_package
    assert "recommend_split" in spec_extractor.__all__
    assert "pin_canonical_package" in spec_extractor.__all__
