"""Tests for the HPC skill bundle (OpenMP / MPI / CUDA / ROCm / SIMD)."""
from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# File existence tests
# ---------------------------------------------------------------------------

HPC_PKG = Path(__file__).parent.parent / "src" / "bob3" / "skill_bundles" / "hpc"

REQUIRED_FILES = [
    "__init__.py",
    "openmp.md",
    "mpi.md",
    "cuda.md",
    "rocm.md",
    "simd.md",
]


class TestFileExistence:
    @pytest.mark.parametrize("filename", REQUIRED_FILES)
    def test_file_exists(self, filename: str) -> None:
        path = HPC_PKG / filename
        assert path.exists(), f"Missing required file: {path}"

    def test_init_py_importable(self) -> None:
        import bob3.skill_bundles.hpc  # noqa: F401

    def test_markdown_files_nonempty(self) -> None:
        for md in ["openmp.md", "mpi.md", "cuda.md", "rocm.md", "simd.md"]:
            path = HPC_PKG / md
            assert path.stat().st_size > 0, f"{md} is empty"


# ---------------------------------------------------------------------------
# __init__.py API tests
# ---------------------------------------------------------------------------


class TestHPCBundleAPI:
    def test_is_hpc_spec_none_returns_false(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec(None) is False

    def test_is_hpc_spec_empty_dict_returns_false(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({}) is False

    def test_is_hpc_spec_domain_hpc_true(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"domain": "hpc"}) is True

    def test_is_hpc_spec_metadata_domain_hpc_true(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"metadata": {"domain": "hpc"}}) is True

    def test_is_hpc_spec_compile_target_nvcc(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"compile_target": "nvcc"}) is True

    def test_is_hpc_spec_compile_target_hipcc(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"compile_target": "hipcc"}) is True

    def test_is_hpc_spec_compile_target_mpicc(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"compile_target": "mpicc"}) is True

    def test_is_hpc_spec_compile_target_list_contains_nvcc(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"compile_target": ["gcc", "nvcc"]}) is True

    def test_is_hpc_spec_compile_target_other_returns_false(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"compile_target": "gcc"}) is False

    def test_is_hpc_spec_domain_ml_returns_false(self) -> None:
        from bob3.skill_bundles.hpc import is_hpc_spec

        assert is_hpc_spec({"domain": "ml"}) is False

    def test_load_hpc_skills_returns_dict(self) -> None:
        from bob3.skill_bundles.hpc import load_hpc_skills

        result = load_hpc_skills()
        assert isinstance(result, dict)

    def test_load_hpc_skills_has_all_keys(self) -> None:
        from bob3.skill_bundles.hpc import load_hpc_skills

        result = load_hpc_skills()
        expected_keys = {"openmp.md", "mpi.md", "cuda.md", "rocm.md", "simd.md"}
        assert expected_keys == set(result.keys())

    def test_load_hpc_skills_values_are_nonempty_strings(self) -> None:
        from bob3.skill_bundles.hpc import load_hpc_skills

        result = load_hpc_skills()
        for key, value in result.items():
            assert isinstance(value, str), f"{key} value is not a string"
            assert len(value.strip()) > 0, f"{key} value is empty"

    def test_hpc_skill_files_constant_defined(self) -> None:
        from bob3.skill_bundles.hpc import HPC_SKILL_FILES

        assert isinstance(HPC_SKILL_FILES, (list, tuple))
        assert len(HPC_SKILL_FILES) == 5


# ---------------------------------------------------------------------------
# Markdown content quality tests
# ---------------------------------------------------------------------------


class TestMarkdownContent:
    def test_openmp_md_contains_pragma(self) -> None:
        content = (HPC_PKG / "openmp.md").read_text()
        assert "pragma" in content.lower() or "#pragma" in content

    def test_mpi_md_contains_mpi(self) -> None:
        content = (HPC_PKG / "mpi.md").read_text()
        assert "MPI" in content or "mpi" in content.lower()

    def test_cuda_md_contains_cuda_keywords(self) -> None:
        content = (HPC_PKG / "cuda.md").read_text()
        assert any(kw in content for kw in ["CUDA", "cuda", "kernel", "__global__", "blockDim"])

    def test_rocm_md_contains_rocm_or_hip(self) -> None:
        content = (HPC_PKG / "rocm.md").read_text()
        assert any(kw in content for kw in ["ROCm", "HIP", "hip", "rocm", "hipcc"])

    def test_simd_md_contains_simd_keywords(self) -> None:
        content = (HPC_PKG / "simd.md").read_text()
        assert any(kw in content for kw in ["SIMD", "simd", "intrinsic", "AVX", "SSE", "vectoriz"])

    def test_all_md_files_have_markdown_heading(self) -> None:
        for md in ["openmp.md", "mpi.md", "cuda.md", "rocm.md", "simd.md"]:
            content = (HPC_PKG / md).read_text()
            assert content.lstrip().startswith("#"), f"{md} lacks a markdown heading"


# ---------------------------------------------------------------------------
# Integration with per_domain_skill_bundles_hpc_ml_pl
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_get_hpc_skill_content_returns_none_for_non_hpc(self) -> None:
        from bob3.per_domain_skill_bundles_hpc_ml_pl import get_hpc_skill_content

        result = get_hpc_skill_content({"domain": "ml"})
        assert result is None

    def test_get_hpc_skill_content_returns_dict_for_hpc_spec(self) -> None:
        from bob3.per_domain_skill_bundles_hpc_ml_pl import get_hpc_skill_content

        result = get_hpc_skill_content({"domain": "hpc"})
        assert isinstance(result, dict)
        assert len(result) == 5

    def test_get_hpc_skill_content_returns_dict_for_nvcc_target(self) -> None:
        from bob3.per_domain_skill_bundles_hpc_ml_pl import get_hpc_skill_content

        result = get_hpc_skill_content({"compile_target": "nvcc"})
        assert isinstance(result, dict)

    def test_get_hpc_skill_content_returns_none_for_none(self) -> None:
        from bob3.per_domain_skill_bundles_hpc_ml_pl import get_hpc_skill_content

        result = get_hpc_skill_content(None)
        assert result is None
