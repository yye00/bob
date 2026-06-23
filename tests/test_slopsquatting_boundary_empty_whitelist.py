"""Tests for zero/empty boundary conditions of check_imports_with_local_whitelist."""
from __future__ import annotations

import pytest
from bob3.security.slopsquatting_scan import check_imports_with_local_whitelist


def test_empty_whitelist_returns_full_input() -> None:
    """With an empty whitelist, the full import list is returned unchanged."""
    imports = ["requests", "flask", "totally_made_up_pkg_xyz"]
    result = check_imports_with_local_whitelist(imports, set())
    assert result == imports


def test_empty_imports_and_whitelist_returns_empty() -> None:
    """Both empty inputs → empty output."""
    result = check_imports_with_local_whitelist([], set())
    assert result == []


def test_empty_imports_non_empty_whitelist_returns_empty() -> None:
    """Empty imports list → empty output regardless of whitelist content."""
    result = check_imports_with_local_whitelist([], {"some_module"})
    assert result == []


def test_full_whitelist_match_returns_empty() -> None:
    """When every import is whitelisted, result is empty."""
    imports = ["mod_a", "mod_b"]
    whitelist = {"mod_a", "mod_b"}
    result = check_imports_with_local_whitelist(imports, whitelist)
    assert result == []


def test_whitelist_with_none_matching_returns_all() -> None:
    """Whitelist that shares no names with imports → full input returned."""
    imports = ["requests", "numpy"]
    whitelist = {"unrelated_local_mod"}
    result = check_imports_with_local_whitelist(imports, whitelist)
    assert result == imports
