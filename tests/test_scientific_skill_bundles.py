"""Tests for the scientific domain skill bundles (CFD / geomech / NR / plasma / particle)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BUNDLES_ROOT = Path(__file__).parent.parent / "src" / "bob" / "skill_bundles"

CFD_PKG      = BUNDLES_ROOT / "cfd"
GEOMECH_PKG  = BUNDLES_ROOT / "geomech"
NR_PKG       = BUNDLES_ROOT / "nr"
PLASMA_PKG   = BUNDLES_ROOT / "plasma"
PARTICLE_PKG = BUNDLES_ROOT / "particle"

# ---------------------------------------------------------------------------
# Expected files per bundle
# ---------------------------------------------------------------------------

CFD_FILES = [
    "__init__.py",
    "fvm_fem.md",
    "simple_piso.md",
    "turbulence.md",
    "boundary_conditions.md",
]

GEOMECH_FILES = [
    "__init__.py",
    "poroelasticity.md",
    "frictional_contact.md",
    "fault_slip.md",
    "plasticity.md",
]

NR_FILES = [
    "__init__.py",
    "bssn.md",
    "gauge_conditions.md",
    "initial_data.md",
    "gw_extraction.md",
    "amr.md",
]

PLASMA_FILES = [
    "__init__.py",
    "pic.md",
    "boris_pusher.md",
    "field_gather_scatter.md",
    "mhd.md",
    "vlasov_poisson.md",
]

PARTICLE_FILES = [
    "__init__.py",
    "geant4_user_actions.md",
    "custom_physics_lists.md",
]


# ===========================================================================
# File existence tests
# ===========================================================================

class TestFileExistence:
    @pytest.mark.parametrize("filename", CFD_FILES)
    def test_cfd_file_exists(self, filename: str) -> None:
        assert (CFD_PKG / filename).exists(), f"Missing: {CFD_PKG / filename}"

    @pytest.mark.parametrize("filename", GEOMECH_FILES)
    def test_geomech_file_exists(self, filename: str) -> None:
        assert (GEOMECH_PKG / filename).exists(), f"Missing: {GEOMECH_PKG / filename}"

    @pytest.mark.parametrize("filename", NR_FILES)
    def test_nr_file_exists(self, filename: str) -> None:
        assert (NR_PKG / filename).exists(), f"Missing: {NR_PKG / filename}"

    @pytest.mark.parametrize("filename", PLASMA_FILES)
    def test_plasma_file_exists(self, filename: str) -> None:
        assert (PLASMA_PKG / filename).exists(), f"Missing: {PLASMA_PKG / filename}"

    @pytest.mark.parametrize("filename", PARTICLE_FILES)
    def test_particle_file_exists(self, filename: str) -> None:
        assert (PARTICLE_PKG / filename).exists(), f"Missing: {PARTICLE_PKG / filename}"


# ===========================================================================
# Importability tests
# ===========================================================================

class TestImportability:
    def test_cfd_importable(self) -> None:
        import bob.skill_bundles.cfd  # noqa: F401

    def test_geomech_importable(self) -> None:
        import bob.skill_bundles.geomech  # noqa: F401

    def test_nr_importable(self) -> None:
        import bob.skill_bundles.nr  # noqa: F401

    def test_plasma_importable(self) -> None:
        import bob.skill_bundles.plasma  # noqa: F401

    def test_particle_importable(self) -> None:
        import bob.skill_bundles.particle  # noqa: F401


# ===========================================================================
# Markdown files non-empty
# ===========================================================================

class TestMarkdownNonEmpty:
    @pytest.mark.parametrize("pkg,files", [
        (CFD_PKG,      [f for f in CFD_FILES if f.endswith(".md")]),
        (GEOMECH_PKG,  [f for f in GEOMECH_FILES if f.endswith(".md")]),
        (NR_PKG,       [f for f in NR_FILES if f.endswith(".md")]),
        (PLASMA_PKG,   [f for f in PLASMA_FILES if f.endswith(".md")]),
        (PARTICLE_PKG, [f for f in PARTICLE_FILES if f.endswith(".md")]),
    ])
    def test_all_md_files_nonempty(self, pkg: Path, files: list[str]) -> None:
        for filename in files:
            path = pkg / filename
            assert path.stat().st_size > 0, f"{path} is empty"

    @pytest.mark.parametrize("pkg,files", [
        (CFD_PKG,      [f for f in CFD_FILES if f.endswith(".md")]),
        (GEOMECH_PKG,  [f for f in GEOMECH_FILES if f.endswith(".md")]),
        (NR_PKG,       [f for f in NR_FILES if f.endswith(".md")]),
        (PLASMA_PKG,   [f for f in PLASMA_FILES if f.endswith(".md")]),
        (PARTICLE_PKG, [f for f in PARTICLE_FILES if f.endswith(".md")]),
    ])
    def test_all_md_files_have_heading(self, pkg: Path, files: list[str]) -> None:
        for filename in files:
            content = (pkg / filename).read_text(encoding="utf-8")
            assert content.lstrip().startswith("#"), f"{pkg / filename} lacks a markdown heading"


# ===========================================================================
# Bundle API: is_*_spec and load_*_skills
# ===========================================================================

class TestCFDBundleAPI:
    def test_is_cfd_spec_none_returns_false(self) -> None:
        from bob.skill_bundles.cfd import is_cfd_spec
        assert is_cfd_spec(None) is False

    def test_is_cfd_spec_empty_returns_false(self) -> None:
        from bob.skill_bundles.cfd import is_cfd_spec
        assert is_cfd_spec({}) is False

    def test_is_cfd_spec_domain_cfd_true(self) -> None:
        from bob.skill_bundles.cfd import is_cfd_spec
        assert is_cfd_spec({"domain": "cfd"}) is True

    def test_is_cfd_spec_metadata_domain_true(self) -> None:
        from bob.skill_bundles.cfd import is_cfd_spec
        assert is_cfd_spec({"metadata": {"domain": "cfd"}}) is True

    def test_is_cfd_spec_other_domain_false(self) -> None:
        from bob.skill_bundles.cfd import is_cfd_spec
        assert is_cfd_spec({"domain": "hpc"}) is False

    def test_load_cfd_skills_returns_dict(self) -> None:
        from bob.skill_bundles.cfd import load_cfd_skills
        result = load_cfd_skills()
        assert isinstance(result, dict)
        assert len(result) == 4

    def test_load_cfd_skills_values_nonempty_strings(self) -> None:
        from bob.skill_bundles.cfd import load_cfd_skills
        for key, value in load_cfd_skills().items():
            assert isinstance(value, str)
            assert len(value.strip()) > 0, f"{key} is empty"

    def test_cfd_skill_files_constant(self) -> None:
        from bob.skill_bundles.cfd import CFD_SKILL_FILES
        assert isinstance(CFD_SKILL_FILES, list)
        assert len(CFD_SKILL_FILES) == 4


class TestGeomechBundleAPI:
    def test_is_geomech_spec_none_returns_false(self) -> None:
        from bob.skill_bundles.geomech import is_geomech_spec
        assert is_geomech_spec(None) is False

    def test_is_geomech_spec_domain_true(self) -> None:
        from bob.skill_bundles.geomech import is_geomech_spec
        assert is_geomech_spec({"domain": "geomech"}) is True

    def test_is_geomech_spec_metadata_domain_true(self) -> None:
        from bob.skill_bundles.geomech import is_geomech_spec
        assert is_geomech_spec({"metadata": {"domain": "geomech"}}) is True

    def test_is_geomech_spec_other_domain_false(self) -> None:
        from bob.skill_bundles.geomech import is_geomech_spec
        assert is_geomech_spec({"domain": "cfd"}) is False

    def test_load_geomech_skills_returns_dict(self) -> None:
        from bob.skill_bundles.geomech import load_geomech_skills
        result = load_geomech_skills()
        assert isinstance(result, dict)
        assert len(result) == 4

    def test_load_geomech_skills_all_nonempty(self) -> None:
        from bob.skill_bundles.geomech import load_geomech_skills
        for key, value in load_geomech_skills().items():
            assert len(value.strip()) > 0, f"{key} is empty"

    def test_geomech_skill_files_constant(self) -> None:
        from bob.skill_bundles.geomech import GEOMECH_SKILL_FILES
        assert isinstance(GEOMECH_SKILL_FILES, list)
        assert len(GEOMECH_SKILL_FILES) == 4


class TestNRBundleAPI:
    def test_is_nr_spec_none_returns_false(self) -> None:
        from bob.skill_bundles.nr import is_nr_spec
        assert is_nr_spec(None) is False

    def test_is_nr_spec_domain_nr_true(self) -> None:
        from bob.skill_bundles.nr import is_nr_spec
        assert is_nr_spec({"domain": "nr"}) is True

    def test_is_nr_spec_metadata_domain_true(self) -> None:
        from bob.skill_bundles.nr import is_nr_spec
        assert is_nr_spec({"metadata": {"domain": "nr"}}) is True

    def test_is_nr_spec_other_domain_false(self) -> None:
        from bob.skill_bundles.nr import is_nr_spec
        assert is_nr_spec({"domain": "plasma"}) is False

    def test_load_nr_skills_returns_dict(self) -> None:
        from bob.skill_bundles.nr import load_nr_skills
        result = load_nr_skills()
        assert isinstance(result, dict)
        assert len(result) == 5

    def test_load_nr_skills_all_nonempty(self) -> None:
        from bob.skill_bundles.nr import load_nr_skills
        for key, value in load_nr_skills().items():
            assert len(value.strip()) > 0, f"{key} is empty"

    def test_nr_skill_files_constant(self) -> None:
        from bob.skill_bundles.nr import NR_SKILL_FILES
        assert isinstance(NR_SKILL_FILES, list)
        assert len(NR_SKILL_FILES) == 5


class TestPlasmaBundleAPI:
    def test_is_plasma_spec_none_returns_false(self) -> None:
        from bob.skill_bundles.plasma import is_plasma_spec
        assert is_plasma_spec(None) is False

    def test_is_plasma_spec_domain_true(self) -> None:
        from bob.skill_bundles.plasma import is_plasma_spec
        assert is_plasma_spec({"domain": "plasma"}) is True

    def test_is_plasma_spec_metadata_domain_true(self) -> None:
        from bob.skill_bundles.plasma import is_plasma_spec
        assert is_plasma_spec({"metadata": {"domain": "plasma"}}) is True

    def test_is_plasma_spec_other_domain_false(self) -> None:
        from bob.skill_bundles.plasma import is_plasma_spec
        assert is_plasma_spec({"domain": "nr"}) is False

    def test_load_plasma_skills_returns_dict(self) -> None:
        from bob.skill_bundles.plasma import load_plasma_skills
        result = load_plasma_skills()
        assert isinstance(result, dict)
        assert len(result) == 5

    def test_load_plasma_skills_all_nonempty(self) -> None:
        from bob.skill_bundles.plasma import load_plasma_skills
        for key, value in load_plasma_skills().items():
            assert len(value.strip()) > 0, f"{key} is empty"

    def test_plasma_skill_files_constant(self) -> None:
        from bob.skill_bundles.plasma import PLASMA_SKILL_FILES
        assert isinstance(PLASMA_SKILL_FILES, list)
        assert len(PLASMA_SKILL_FILES) == 5


class TestParticleBundleAPI:
    def test_is_particle_spec_none_returns_false(self) -> None:
        from bob.skill_bundles.particle import is_particle_spec
        assert is_particle_spec(None) is False

    def test_is_particle_spec_domain_true(self) -> None:
        from bob.skill_bundles.particle import is_particle_spec
        assert is_particle_spec({"domain": "particle"}) is True

    def test_is_particle_spec_metadata_domain_true(self) -> None:
        from bob.skill_bundles.particle import is_particle_spec
        assert is_particle_spec({"metadata": {"domain": "particle"}}) is True

    def test_is_particle_spec_other_domain_false(self) -> None:
        from bob.skill_bundles.particle import is_particle_spec
        assert is_particle_spec({"domain": "plasma"}) is False

    def test_load_particle_skills_returns_dict(self) -> None:
        from bob.skill_bundles.particle import load_particle_skills
        result = load_particle_skills()
        assert isinstance(result, dict)
        assert len(result) == 2

    def test_load_particle_skills_all_nonempty(self) -> None:
        from bob.skill_bundles.particle import load_particle_skills
        for key, value in load_particle_skills().items():
            assert len(value.strip()) > 0, f"{key} is empty"

    def test_particle_skill_files_constant(self) -> None:
        from bob.skill_bundles.particle import PARTICLE_SKILL_FILES
        assert isinstance(PARTICLE_SKILL_FILES, list)
        assert len(PARTICLE_SKILL_FILES) == 2


# ===========================================================================
# Markdown content quality
# ===========================================================================

class TestMarkdownContentQuality:
    def test_cfd_fvm_fem_contains_fvm(self) -> None:
        content = (CFD_PKG / "fvm_fem.md").read_text()
        assert "FVM" in content or "Finite Volume" in content

    def test_cfd_simple_piso_contains_simple(self) -> None:
        content = (CFD_PKG / "simple_piso.md").read_text()
        assert "SIMPLE" in content

    def test_cfd_turbulence_contains_ke_or_sst(self) -> None:
        content = (CFD_PKG / "turbulence.md").read_text()
        assert any(kw in content for kw in ["k-ε", "k-omega", "SST", "RANS", "turbulence"])

    def test_cfd_bc_contains_inlet(self) -> None:
        content = (CFD_PKG / "boundary_conditions.md").read_text()
        assert "inlet" in content.lower() or "Inlet" in content

    def test_geomech_poroelasticity_contains_biot(self) -> None:
        content = (GEOMECH_PKG / "poroelasticity.md").read_text()
        assert "Biot" in content or "poroelastic" in content.lower()

    def test_geomech_fault_slip_contains_coulomb(self) -> None:
        content = (GEOMECH_PKG / "fault_slip.md").read_text()
        assert "Coulomb" in content or "rate-and-state" in content.lower()

    def test_geomech_plasticity_contains_drucker_prager(self) -> None:
        content = (GEOMECH_PKG / "plasticity.md").read_text()
        assert "Drucker" in content or "Mohr" in content

    def test_nr_bssn_contains_bssn(self) -> None:
        content = (NR_PKG / "bssn.md").read_text()
        assert "BSSN" in content or "conformal" in content.lower()

    def test_nr_gauge_contains_1plus_log(self) -> None:
        content = (NR_PKG / "gauge_conditions.md").read_text()
        assert "1+log" in content or "Gamma-driver" in content or "gauge" in content.lower()

    def test_nr_gw_extraction_contains_psi4(self) -> None:
        content = (NR_PKG / "gw_extraction.md").read_text()
        assert "Psi4" in content or "Ψ₄" in content or "GW" in content

    def test_nr_amr_contains_amr_or_berger(self) -> None:
        content = (NR_PKG / "amr.md").read_text()
        assert "AMR" in content or "Berger" in content or "refinement" in content.lower()

    def test_plasma_pic_contains_particle_in_cell(self) -> None:
        content = (PLASMA_PKG / "pic.md").read_text()
        assert "PIC" in content or "Particle-in-Cell" in content

    def test_plasma_boris_contains_boris(self) -> None:
        content = (PLASMA_PKG / "boris_pusher.md").read_text()
        assert "Boris" in content or "boris" in content.lower()

    def test_plasma_mhd_contains_mhd(self) -> None:
        content = (PLASMA_PKG / "mhd.md").read_text()
        assert "MHD" in content or "magnetohydrodynamic" in content.lower()

    def test_plasma_vlasov_contains_vlasov(self) -> None:
        content = (PLASMA_PKG / "vlasov_poisson.md").read_text()
        assert "Vlasov" in content or "vlasov" in content.lower()

    def test_particle_geant4_contains_geant4(self) -> None:
        content = (PARTICLE_PKG / "geant4_user_actions.md").read_text()
        assert "Geant4" in content or "G4" in content

    def test_particle_physics_lists_contains_physics_list(self) -> None:
        content = (PARTICLE_PKG / "custom_physics_lists.md").read_text()
        assert "PhysicsList" in content or "physics list" in content.lower()


# ===========================================================================
# Integration: per_domain_skill_bundles_hpc_ml_pl
# ===========================================================================

class TestIntegration:
    def test_new_domains_in_valid_domains(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import VALID_DOMAINS
        for domain in ("cfd", "geomech", "nr", "plasma", "particle"):
            assert domain in VALID_DOMAINS, f"{domain} not in VALID_DOMAINS"

    def test_get_skills_for_cfd(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_skills_for_domain
        skills = get_skills_for_domain("cfd")
        assert isinstance(skills, list)
        assert len(skills) > 0

    def test_get_skills_for_nr(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_skills_for_domain
        skills = get_skills_for_domain("nr")
        assert isinstance(skills, list)
        assert len(skills) > 0

    def test_select_domain_from_spec_cfd(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import select_domain_from_spec
        assert select_domain_from_spec({"domain": "cfd"}) == "cfd"

    def test_select_domain_from_spec_plasma(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import select_domain_from_spec
        assert select_domain_from_spec({"metadata": {"domain": "plasma"}}) == "plasma"

    def test_get_cfd_skill_content_returns_none_for_non_cfd(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_cfd_skill_content
        assert get_cfd_skill_content({"domain": "hpc"}) is None

    def test_get_cfd_skill_content_returns_dict_for_cfd(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_cfd_skill_content
        result = get_cfd_skill_content({"domain": "cfd"})
        assert isinstance(result, dict)
        assert len(result) == 4

    def test_get_geomech_skill_content_returns_none_for_other(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_geomech_skill_content
        assert get_geomech_skill_content({"domain": "cfd"}) is None

    def test_get_geomech_skill_content_returns_dict(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_geomech_skill_content
        result = get_geomech_skill_content({"domain": "geomech"})
        assert isinstance(result, dict)
        assert len(result) == 4

    def test_get_nr_skill_content_returns_none_for_non_nr(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_nr_skill_content
        assert get_nr_skill_content({"domain": "plasma"}) is None

    def test_get_nr_skill_content_returns_dict(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_nr_skill_content
        result = get_nr_skill_content({"domain": "nr"})
        assert isinstance(result, dict)
        assert len(result) == 5

    def test_get_plasma_skill_content_returns_none_for_non_plasma(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_plasma_skill_content
        assert get_plasma_skill_content({"domain": "nr"}) is None

    def test_get_plasma_skill_content_returns_dict(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_plasma_skill_content
        result = get_plasma_skill_content({"domain": "plasma"})
        assert isinstance(result, dict)
        assert len(result) == 5

    def test_get_particle_skill_content_returns_none_for_non_particle(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_particle_skill_content
        assert get_particle_skill_content({"domain": "cfd"}) is None

    def test_get_particle_skill_content_returns_dict(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_particle_skill_content
        result = get_particle_skill_content({"domain": "particle"})
        assert isinstance(result, dict)
        assert len(result) == 2

    def test_get_bundle_for_spec_cfd(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import get_bundle_for_spec
        bundle = get_bundle_for_spec({"domain": "cfd"})
        assert isinstance(bundle, list)
        assert len(bundle) > 0

    def test_all_new_domains_have_nonempty_bundles(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import DOMAIN_BUNDLES
        for domain in ("cfd", "geomech", "nr", "plasma", "particle"):
            assert len(DOMAIN_BUNDLES[domain]) > 0, f"{domain} bundle is empty"

    def test_get_skill_content_for_none_returns_none(self) -> None:
        from bob.per_domain_skill_bundles_hpc_ml_pl import (
            get_cfd_skill_content, get_geomech_skill_content,
            get_nr_skill_content, get_plasma_skill_content,
            get_particle_skill_content,
        )
        for fn in [get_cfd_skill_content, get_geomech_skill_content,
                   get_nr_skill_content, get_plasma_skill_content,
                   get_particle_skill_content]:
            assert fn(None) is None
