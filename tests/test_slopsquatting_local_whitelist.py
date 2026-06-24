"""Integration tests: local whitelist prevents false positives while genuine fictitious packages still fail."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from bob3.security.slopsquatting_scan import (
    find_local_modules,
    check_imports_with_local_whitelist,
)


@pytest.fixture
def workspace_with_local_module(tmp_path: Path) -> Path:
    """Fixture with a src/bob3/ tree that includes spec_quality_score as a local module."""
    src_bob3 = tmp_path / "src" / "bob3"
    src_bob3.mkdir(parents=True)
    # local module with same name as a real local file
    (src_bob3 / "spec_quality_score.py").write_text("# spec quality scoring\n")
    return tmp_path


def test_local_module_whitelisted_produces_no_finding(workspace_with_local_module: Path) -> None:
    """spec_quality_score (local module fixture) is whitelisted and produces NO finding.

    When the import list includes spec_quality_score and the whitelist is derived from
    find_local_modules, check_imports_with_local_whitelist must return it filtered out.
    """
    whitelist = find_local_modules(workspace_with_local_module)
    assert "spec_quality_score" in whitelist

    imports_to_check = ["requests", "spec_quality_score", "flask"]
    remaining = check_imports_with_local_whitelist(imports_to_check, whitelist)
    assert "spec_quality_score" not in remaining, (
        "spec_quality_score is a local module and should be whitelisted from PyPI check"
    )


def test_genuinely_missing_package_still_flagged(workspace_with_local_module: Path) -> None:
    """A genuinely missing PyPI package (totally_made_up_pkg_xyz) still appears in the output.

    It is NOT in the local module whitelist, so check_imports_with_local_whitelist
    must leave it in the list, meaning it would proceed to the PyPI probe step.
    """
    whitelist = find_local_modules(workspace_with_local_module)
    # The made-up package is not a local module
    assert "totally_made_up_pkg_xyz" not in whitelist

    imports_to_check = ["totally_made_up_pkg_xyz"]
    remaining = check_imports_with_local_whitelist(imports_to_check, whitelist)
    assert "totally_made_up_pkg_xyz" in remaining, (
        "totally_made_up_pkg_xyz is not local — it must NOT be whitelisted and must proceed to PyPI check"
    )


def test_local_module_same_name_as_real_pypi_prefers_local(tmp_path: Path) -> None:
    """A package with the same name as both a local module AND real PyPI dist prefers local.

    E.g. if 'requests' appeared as a local module file, it would be whitelisted and
    would produce no security finding (no false alarm).
    """
    src_bob3 = tmp_path / "src" / "bob3"
    src_bob3.mkdir(parents=True)
    # Simulate 'requests' as a local module file (unusual but valid test scenario)
    (src_bob3 / "requests.py").write_text("# local override of requests\n")

    whitelist = find_local_modules(tmp_path)
    assert "requests" in whitelist, "Local module named 'requests' must appear in whitelist"

    imports_to_check = ["requests", "numpy"]
    remaining = check_imports_with_local_whitelist(imports_to_check, whitelist)
    # 'requests' is local → whitelisted → filtered out → no false security finding
    assert "requests" not in remaining, (
        "When 'requests' is also a local module, it should be whitelisted to avoid false positives"
    )
    # 'numpy' is not local → stays in the list
    assert "numpy" in remaining
