"""Boundary tests: empty/zero/minimum input to parse_depends_on / emit_stub_features
returns a well-defined result rather than raising."""
from __future__ import annotations

from bob.extract_from_peas import parse_depends_on, emit_stub_features


class TestParseDependsOnBoundary:
    def test_none_returns_empty_list(self):
        assert parse_depends_on(None) == []

    def test_empty_string_returns_empty_list(self):
        assert parse_depends_on("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert parse_depends_on("   \n\t ") == []

    def test_depends_clause_with_no_slot_returns_empty(self):
        # "Depends on" with no recognizable slot ref -> no dependencies.
        assert parse_depends_on("Depends on the weather.") == []

    def test_minimum_single_slot(self):
        assert parse_depends_on("Depends on F-HP-001.") == ["F-HP-001"]


class TestEmitStubFeaturesBoundary:
    def test_empty_feature_list_returns_empty(self):
        assert emit_stub_features([]) == []

    def test_feature_with_only_metadata_no_deps(self):
        parsed = [
            {
                "title": "Metadata-only feature",
                "tier": "Core",
                "priority": "medium",
                "slot": "F-HP-010",
                "description": "A short prose line, no depends clause.",
            }
        ]
        stubs = emit_stub_features(parsed)
        assert "depends_on" not in stubs[0]
        assert stubs[0]["key"] == "F-HP-010"

    def test_feature_with_empty_description(self):
        parsed = [
            {
                "title": "Empty description",
                "tier": "Core",
                "priority": "low",
                "slot": "F-HP-011",
                "description": "",
            }
        ]
        stubs = emit_stub_features(parsed)
        assert "depends_on" not in stubs[0]
