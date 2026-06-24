"""Tests for check_imports_with_local_whitelist function."""
from __future__ import annotations

import pytest
from bob.security.slopsquatting_scan import check_imports_with_local_whitelist


def test_check_imports_filters_whitelisted_names() -> None:
    """Names in the whitelist set are removed from the import list."""
    imports = ["requests", "spec_quality_score", "numpy"]
    whitelist = {"spec_quality_score", "bob"}
    result = check_imports_with_local_whitelist(imports, whitelist)
    assert "spec_quality_score" not in result
    assert "requests" in result
    assert "numpy" in result


def test_check_imports_returns_only_non_whitelisted() -> None:
    """Return value contains ONLY names not present in the whitelist."""
    imports = ["foo", "bar", "baz"]
    whitelist = {"foo", "baz"}
    result = check_imports_with_local_whitelist(imports, whitelist)
    assert result == ["bar"]


def test_check_imports_with_no_matching_whitelist() -> None:
    """When no imports match the whitelist, all imports are returned."""
    imports = ["requests", "flask"]
    whitelist = {"some_local_module"}
    result = check_imports_with_local_whitelist(imports, whitelist)
    assert set(result) == {"requests", "flask"}


def test_check_imports_preserves_order() -> None:
    """Order of non-whitelisted imports is preserved."""
    imports = ["a", "b", "c", "d"]
    whitelist = {"b"}
    result = check_imports_with_local_whitelist(imports, whitelist)
    assert result == ["a", "c", "d"]


def test_check_imports_returns_list() -> None:
    """The return type is a list."""
    result = check_imports_with_local_whitelist(["requests"], set())
    assert isinstance(result, list)
