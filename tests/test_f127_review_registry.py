"""Tests for the bob3 review-findings registry."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from bob3 import reviews as registry_module
from bob3.reviews import (
    Finding,
    Registry,
    add_finding,
    load_registry,
    mark_fixed,
    next_finding_id,
    render_summary,
    save_registry,
    summarize_severity,
    summarize_status,
)


REPO_REGISTRY = Path(__file__).resolve().parents[1] / "reviews" / "findings.yaml"


@pytest.fixture
def tmp_registry(tmp_path) -> Path:
    """Copy the real registry to a tmp location for non-destructive editing."""
    dest = tmp_path / "reviews" / "findings.yaml"
    dest.parent.mkdir(parents=True)
    shutil.copy(REPO_REGISTRY, dest)
    return dest


class TestLoad:
    def test_loads_real_registry(self):
        reg = load_registry()
        assert len(reg.findings) > 0
        assert reg.schema_version == 1

    def test_findings_have_required_fields(self):
        reg = load_registry()
        for f in reg.findings:
            assert f.id, f"empty id"
            assert f.title, f"{f.id}: empty title"
            assert f.severity in {"critical", "high", "medium", "low"}, (
                f"{f.id}: invalid severity {f.severity}"
            )
            assert f.status in {"open", "in_progress", "fixed", "partially_fixed",
                                "wontfix", "duplicate"}, (
                f"{f.id}: invalid status {f.status}"
            )

    def test_id_format(self):
        reg = load_registry()
        import re

        pattern = re.compile(r"^R\d+-\d{3}$")
        for f in reg.findings:
            assert pattern.match(f.id), f"{f.id} does not match format R<n>-<seq>"

    def test_round_property(self):
        f = Finding(
            id="R3-007", title="x", pattern="y", files=[], severity="low", status="open"
        )
        assert f.round == "R3"


class TestSearch:
    def test_search_by_tag(self):
        reg = load_registry()
        hits = reg.search(tag="signal-safety")
        assert len(hits) >= 2
        for h in hits:
            assert "signal-safety" in h.tags

    def test_search_by_severity(self):
        reg = load_registry()
        criticals = reg.search(severity="critical", limit=100)
        assert all(f.severity == "critical" for f in criticals)
        assert len(criticals) >= 5

    def test_search_by_status(self):
        reg = load_registry()
        fixed = reg.search(status="fixed", limit=200)
        assert all(f.status == "fixed" for f in fixed)

    def test_search_by_file_substring(self):
        reg = load_registry()
        hits = reg.search(files_glob="run_loop.py")
        assert len(hits) >= 1
        for h in hits:
            assert any("run_loop.py" in p for p in h.files)

    def test_search_by_query_text(self):
        reg = load_registry()
        hits = reg.search(query="cascade", limit=20)
        assert len(hits) >= 1
        for h in hits:
            blob = (h.title + h.pattern + h.notes).lower()
            assert "cascade" in blob

    def test_search_combined_filters(self):
        reg = load_registry()
        hits = reg.search(severity="critical", status="fixed", limit=100)
        for h in hits:
            assert h.severity == "critical"
            assert h.status == "fixed"

    def test_search_limit_honored(self):
        reg = load_registry()
        hits = reg.search(limit=3)
        assert len(hits) == 3


class TestRecurringPatterns:
    def test_patterns_loaded(self):
        reg = load_registry()
        assert len(reg.recurring_patterns) > 0

    def test_pattern_lookup(self):
        reg = load_registry()
        rp = reg.patterns_for_tag("subprocess-pitfalls")
        assert rp is not None
        assert len(rp.occurrences) >= 2

    def test_pattern_occurrences_exist_in_findings(self):
        reg = load_registry()
        all_ids = {f.id for f in reg.findings}
        for rp in reg.recurring_patterns:
            for fid in rp.occurrences:
                assert fid in all_ids, (
                    f"Recurring pattern '{rp.tag}' references missing id {fid}"
                )


class TestModification:
    def test_next_finding_id_for_existing_round(self):
        reg = load_registry()
        next_id = next_finding_id(reg, "R3")
        assert next_id.startswith("R3-")
        # should be greater than any current R3-* id
        existing = [int(f.id.split("-")[1]) for f in reg.findings if f.id.startswith("R3-")]
        assert int(next_id.split("-")[1]) > max(existing)

    def test_next_finding_id_for_new_round(self):
        reg = load_registry()
        assert next_finding_id(reg, "R99") == "R99-001"

    def test_add_finding_assigns_id(self, tmp_registry, monkeypatch):
        monkeypatch.setattr(registry_module, "_registry_path", lambda: tmp_registry)
        reg = load_registry()
        before_count = len(reg.findings)
        f = add_finding(
            reg,
            round_prefix="R99",
            title="Test finding",
            pattern="test pattern",
            files=["src/foo.py"],
            severity="medium",
            tags=["test-tag"],
        )
        assert f.id == "R99-001"
        assert len(reg.findings) == before_count + 1
        save_registry(reg)
        # Round-trip
        reloaded = load_registry()
        assert reloaded.by_id("R99-001") is not None
        assert reloaded.by_id("R99-001").title == "Test finding"
        # Post-reload total count must equal the in-memory count we
        # just saved. Without this assertion, ``save_registry`` could
        # silently drop unrelated findings (e.g. due to a serialization
        # bug touching a field on a different finding) and this test
        # would still pass because it only checked existence of the
        # newly-added finding.
        assert len(reloaded.findings) == before_count + 1, (
            f"save_registry round-trip lost findings: had {before_count + 1} "
            f"in memory after add_finding, reload found {len(reloaded.findings)}"
        )

    def test_mark_fixed(self, tmp_registry, monkeypatch):
        monkeypatch.setattr(registry_module, "_registry_path", lambda: tmp_registry)
        reg = load_registry()
        # Find an open finding (or use partially_fixed for the test)
        target = next(
            (f for f in reg.findings if f.status != "fixed"), None
        )
        if target is None:
            # Create one for the test
            target = add_finding(
                reg,
                round_prefix="R99",
                title="Test",
                pattern="x",
                files=[],
                severity="low",
            )
        ok = mark_fixed(reg, target.id, commit="abc1234")
        assert ok
        save_registry(reg)
        reloaded = load_registry()
        f = reloaded.by_id(target.id)
        assert f.status == "fixed"
        assert f.fixed_in == "abc1234"
        assert f.fixed_at is not None

    def test_mark_fixed_returns_false_for_unknown_id(self, tmp_registry, monkeypatch):
        monkeypatch.setattr(registry_module, "_registry_path", lambda: tmp_registry)
        reg = load_registry()
        assert mark_fixed(reg, "NOPE-999", commit="x") is False


class TestSummary:
    def test_summarize_status(self):
        reg = load_registry()
        counts = summarize_status(reg)
        assert sum(counts.values()) == len(reg.findings)
        assert counts.get("fixed", 0) > 0

    def test_summarize_severity(self):
        reg = load_registry()
        counts = summarize_severity(reg)
        assert sum(counts.values()) == len(reg.findings)

    def test_render_summary_human_readable(self):
        reg = load_registry()
        text = render_summary(reg)
        assert "Total findings:" in text
        assert "Status:" in text
        assert "Severity:" in text


class TestRoundTrip:
    def test_save_then_load_preserves_data(self, tmp_registry, monkeypatch):
        monkeypatch.setattr(registry_module, "_registry_path", lambda: tmp_registry)
        before = load_registry()
        save_registry(before)
        after = load_registry()
        assert len(before.findings) == len(after.findings)
        for a, b in zip(before.findings, after.findings):
            assert a.id == b.id
            assert a.title == b.title
            assert a.tags == b.tags

    def test_save_emits_valid_yaml(self, tmp_registry, monkeypatch):
        monkeypatch.setattr(registry_module, "_registry_path", lambda: tmp_registry)
        reg = load_registry()
        save_registry(reg)
        # Reload as raw YAML to ensure it parses
        with open(tmp_registry) as fh:
            data = yaml.safe_load(fh)
        assert "findings" in data
        assert isinstance(data["findings"], list)
        assert "schema_version" in data
