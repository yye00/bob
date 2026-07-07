"""Tests for extract_from_peas.parse_depends_on and its emit_stub_features wiring.

The PEAS extractor MUST parse prose "Depends on F-XX-NNN" clauses into a
feature's depends_on list so the run loop's dependency gate can enforce build
order (foundations before leaves).
"""
from __future__ import annotations

import pytest

from bob.extract_from_peas import parse_depends_on, emit_stub_features


class TestParseDependsOn:
    def test_single_dependency(self):
        desc = "Sorts an array. Depends on F-HP-009."
        assert parse_depends_on(desc) == ["F-HP-009"]

    def test_multiple_dependencies_and_clause(self):
        desc = "Computes FFT. Depends on F-HP-009 and F-HP-010."
        assert parse_depends_on(desc) == ["F-HP-009", "F-HP-010"]

    def test_only_captures_slots_inside_depends_clause(self):
        # A slot mentioned elsewhere (see ...) must NOT become a dependency.
        desc = "See F-HP-577 for context. Depends on F-HP-009."
        assert parse_depends_on(desc) == ["F-HP-009"]

    def test_trailing_letter_slot_form(self):
        desc = "Depends on F-HP-200b."
        assert parse_depends_on(desc) == ["F-HP-200b"]

    def test_self_reference_dropped(self):
        desc = "Depends on F-HP-009 and F-HP-050."
        assert parse_depends_on(desc, self_slot="F-HP-050") == ["F-HP-009"]

    def test_no_depends_clause_returns_empty(self):
        desc = "A standalone root feature that mentions F-HP-001 casually."
        assert parse_depends_on(desc) == []

    def test_dedup_preserves_first_seen_order(self):
        desc = "Depends on F-HP-009 and F-HP-009 and F-HP-003."
        assert parse_depends_on(desc) == ["F-HP-009", "F-HP-003"]

    def test_bob_r7_prefix_slots(self):
        desc = "Depends on F-R7-553."
        assert parse_depends_on(desc) == ["F-R7-553"]

    def test_case_insensitive_clause(self):
        desc = "depends on F-HP-009."
        assert parse_depends_on(desc) == ["F-HP-009"]


class TestEmitStubFeaturesWiring:
    def test_deps_flow_into_stub(self):
        parsed = [
            {
                "title": "Leaf feature",
                "tier": "Core",
                "priority": "high",
                "slot": "F-HP-100",
                "permanent_forward_carry": False,
                "description": "Depends on F-HP-009.",
            }
        ]
        stubs = emit_stub_features(parsed)
        assert stubs[0]["depends_on"] == ["F-HP-009"]

    def test_root_feature_has_no_depends_on_key(self):
        parsed = [
            {
                "title": "Root feature",
                "tier": "Core",
                "priority": "high",
                "slot": "F-HP-009",
                "permanent_forward_carry": False,
                "description": "The foundational facade. No dependencies.",
            }
        ]
        stubs = emit_stub_features(parsed)
        assert "depends_on" not in stubs[0]

    def test_stub_drops_self_reference(self):
        parsed = [
            {
                "title": "Self-referential feature",
                "tier": "Core",
                "priority": "medium",
                "slot": "F-HP-050",
                "permanent_forward_carry": False,
                "description": "Depends on F-HP-050 and F-HP-009.",
            }
        ]
        stubs = emit_stub_features(parsed)
        assert stubs[0]["depends_on"] == ["F-HP-009"]
