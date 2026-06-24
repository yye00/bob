"""Tests for src/bob/embedded_reproducer_per_finding.py.

Each registry finding can store a minimal failing case (the smallest diff
that reproduces the finding) plus the fix diff, enabling test-driven
regression prevention in future spawns.
"""

from __future__ import annotations

import pytest

from bob.embedded_reproducer_per_finding import (
    Reproducer,
    attach_reproducer,
    get_reproducer,
    list_reproducers,
    validate_reproducer,
    ReproducerValidationError,
)
from bob.reviews import Finding


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_finding() -> Finding:
    return Finding(
        id="R1-001",
        title="Test finding",
        pattern="some pattern",
        files=["src/foo.py"],
        severity="high",
        status="open",
    )


@pytest.fixture
def sample_reproducer() -> Reproducer:
    return Reproducer(
        failing_diff="--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1,3 +1,3 @@\n-x = 1\n+x = None\n",
        fix_diff="--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1,3 +1,3 @@\n-x = None\n+x = 1\n",
        description="Setting x to None causes TypeError downstream",
        test_command="pytest tests/test_foo.py::test_x_is_not_none -x",
    )


# ---------------------------------------------------------------------------
# Reproducer dataclass
# ---------------------------------------------------------------------------


class TestReproducer:
    def test_required_fields(self, sample_reproducer):
        assert sample_reproducer.failing_diff
        assert sample_reproducer.fix_diff

    def test_optional_fields_have_defaults(self):
        r = Reproducer(
            failing_diff="--- a/f.py\n+++ b/f.py\n@@ -0,0 +1 @@\n+bad\n",
            fix_diff="--- a/f.py\n+++ b/f.py\n@@ -1 +0,0 @@\n-bad\n",
        )
        assert r.description == ""
        assert r.test_command == ""

    def test_to_dict_includes_all_fields(self, sample_reproducer):
        d = sample_reproducer.to_dict()
        assert "failing_diff" in d
        assert "fix_diff" in d
        assert "description" in d
        assert "test_command" in d

    def test_from_dict_roundtrip(self, sample_reproducer):
        d = sample_reproducer.to_dict()
        restored = Reproducer.from_dict(d)
        assert restored.failing_diff == sample_reproducer.failing_diff
        assert restored.fix_diff == sample_reproducer.fix_diff
        assert restored.description == sample_reproducer.description
        assert restored.test_command == sample_reproducer.test_command

    def test_from_dict_missing_optional_fields(self):
        d = {
            "failing_diff": "--- a/f.py\n+++ b/f.py\n@@ -0,0 +1 @@\n+bad\n",
            "fix_diff": "--- a/f.py\n+++ b/f.py\n@@ -1 +0,0 @@\n-bad\n",
        }
        r = Reproducer.from_dict(d)
        assert r.description == ""
        assert r.test_command == ""


# ---------------------------------------------------------------------------
# validate_reproducer
# ---------------------------------------------------------------------------


class TestValidateReproducer:
    def test_valid_reproducer_passes(self, sample_reproducer):
        validate_reproducer(sample_reproducer)  # should not raise

    def test_empty_failing_diff_raises(self):
        r = Reproducer(failing_diff="", fix_diff="some diff")
        with pytest.raises(ReproducerValidationError, match="failing_diff"):
            validate_reproducer(r)

    def test_empty_fix_diff_raises(self):
        r = Reproducer(
            failing_diff="--- a/f.py\n+++ b/f.py\n@@ -0,0 +1 @@\n+bad\n",
            fix_diff="",
        )
        with pytest.raises(ReproducerValidationError, match="fix_diff"):
            validate_reproducer(r)

    def test_failing_diff_not_unified_format_raises(self):
        r = Reproducer(failing_diff="just some text", fix_diff="other text")
        with pytest.raises(ReproducerValidationError, match="unified diff"):
            validate_reproducer(r)


# ---------------------------------------------------------------------------
# attach_reproducer / get_reproducer
# ---------------------------------------------------------------------------


class TestAttachAndGet:
    def test_attach_sets_reproducer_on_finding(self, minimal_finding, sample_reproducer):
        attach_reproducer(minimal_finding, sample_reproducer)
        assert minimal_finding.reproducer is not None

    def test_get_returns_reproducer_after_attach(self, minimal_finding, sample_reproducer):
        attach_reproducer(minimal_finding, sample_reproducer)
        r = get_reproducer(minimal_finding)
        assert r is not None
        assert r.failing_diff == sample_reproducer.failing_diff
        assert r.fix_diff == sample_reproducer.fix_diff

    def test_get_returns_none_when_no_reproducer(self, minimal_finding):
        r = get_reproducer(minimal_finding)
        assert r is None

    def test_attach_validates_reproducer(self, minimal_finding):
        bad = Reproducer(failing_diff="", fix_diff="something")
        with pytest.raises(ReproducerValidationError):
            attach_reproducer(minimal_finding, bad)

    def test_attach_overwrites_existing(self, minimal_finding, sample_reproducer):
        attach_reproducer(minimal_finding, sample_reproducer)
        new_r = Reproducer(
            failing_diff="--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-y\n+z\n",
            fix_diff="--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-z\n+y\n",
            description="New reproducer",
        )
        attach_reproducer(minimal_finding, new_r)
        r = get_reproducer(minimal_finding)
        assert r.description == "New reproducer"


# ---------------------------------------------------------------------------
# list_reproducers
# ---------------------------------------------------------------------------


class TestListReproducers:
    def _make_finding(self, fid: str, with_reproducer: bool) -> Finding:
        f = Finding(
            id=fid,
            title=f"Finding {fid}",
            pattern="p",
            files=["src/a.py"],
            severity="low",
            status="open",
        )
        if with_reproducer:
            r = Reproducer(
                failing_diff="--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n",
                fix_diff="--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-b\n+a\n",
            )
            attach_reproducer(f, r)
        return f

    def test_returns_only_findings_with_reproducers(self):
        findings = [
            self._make_finding("R1-001", with_reproducer=True),
            self._make_finding("R1-002", with_reproducer=False),
            self._make_finding("R1-003", with_reproducer=True),
        ]
        result = list_reproducers(findings)
        assert len(result) == 2
        ids = [f.id for f, _ in result]
        assert "R1-001" in ids
        assert "R1-003" in ids
        assert "R1-002" not in ids

    def test_returns_tuples_of_finding_and_reproducer(self):
        f = self._make_finding("R1-001", with_reproducer=True)
        result = list_reproducers([f])
        assert len(result) == 1
        finding, reproducer = result[0]
        assert isinstance(finding, Finding)
        assert isinstance(reproducer, Reproducer)

    def test_empty_list_returns_empty(self):
        assert list_reproducers([]) == []

    def test_no_reproducers_returns_empty(self):
        findings = [self._make_finding("R1-001", with_reproducer=False)]
        assert list_reproducers(findings) == []


# ---------------------------------------------------------------------------
# Integration: Finding.to_dict() persists reproducer
# ---------------------------------------------------------------------------


class TestFindingIntegration:
    def test_finding_to_dict_includes_reproducer_when_attached(
        self, minimal_finding, sample_reproducer
    ):
        attach_reproducer(minimal_finding, sample_reproducer)
        d = minimal_finding.to_dict()
        assert "reproducer" in d
        assert d["reproducer"]["failing_diff"] == sample_reproducer.failing_diff

    def test_finding_to_dict_no_reproducer_key_when_absent(self, minimal_finding):
        d = minimal_finding.to_dict()
        assert "reproducer" not in d
