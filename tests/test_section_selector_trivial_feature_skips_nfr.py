"""Tests: trivial features get NFR sections auto-classified as SKIP."""

from __future__ import annotations

from bob3.spec_quality.section_selector import select_sections


_NFR_SECTIONS = {"perf", "security", "observability", "ops", "ux", "compat"}


def _trivial_feature(keyword: str, extra_desc: str = "") -> dict:
    return {
        "feature_id": "trivial-001",
        "name": f"A {keyword} task",
        "description": f"This is a {keyword} operation. {extra_desc}".strip(),
        "acceptance_criteria": [],
    }


class TestTrivialFeatureSkipsNfr:
    def test_trivial_keyword_skips_nfr_sections(self):
        out = select_sections(**_trivial_feature("trivial"))
        for nfr in _NFR_SECTIONS:
            assert out[nfr] == "SKIP", f"Expected SKIP for {nfr!r}, got {out[nfr]!r}"

    def test_internal_keyword_skips_nfr(self):
        out = select_sections(**_trivial_feature("internal"))
        for nfr in _NFR_SECTIONS:
            assert out[nfr] == "SKIP"

    def test_helper_keyword_skips_nfr(self):
        out = select_sections(**_trivial_feature("helper"))
        for nfr in _NFR_SECTIONS:
            assert out[nfr] == "SKIP"

    def test_refactor_keyword_skips_nfr(self):
        out = select_sections(**_trivial_feature("refactor"))
        for nfr in _NFR_SECTIONS:
            assert out[nfr] == "SKIP"

    def test_trivial_functional_still_required(self):
        out = select_sections(**_trivial_feature("trivial"))
        assert out["functional"] == "REQUIRED"

    def test_non_trivial_feature_may_have_nfr(self):
        out = select_sections(
            feature_id="non-trivial-001",
            name="Auth service",
            description="Handles authentication, token validation, and permission checks with encryption",
            acceptance_criteria=["security tokens are rotated"],
        )
        # Non-trivial with security keywords should NOT be SKIP
        assert out["security"] in {"REQUIRED", "OPTIONAL"}

    def test_cleanup_keyword_skips_nfr(self):
        out = select_sections(**_trivial_feature("cleanup"))
        for nfr in _NFR_SECTIONS:
            assert out[nfr] == "SKIP"

    def test_migration_keyword_skips_nfr(self):
        out = select_sections(**_trivial_feature("migration"))
        for nfr in _NFR_SECTIONS:
            assert out[nfr] == "SKIP"
