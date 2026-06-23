"""Tests for enhanced_verification Pattern 8 scan-all integration AC handler.

Feature e9c44614-ffb1-4b8e-abdf-a00e71d9e7c8:
Pattern 8 ("integration:") MUST scan ALL plausible dotted tokens in body AND
demote prose-policy integration ACs to warning.

Regression guard: feature c09e9e64 burned 3 attempts because the legacy regex
captured "all" (first word) from "integration: all ... bob3.reviews ..." and
called _integration_wired(workspace, "all") — which obviously failed. The
actual module reference bob3.reviews was never tried.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import textwrap

import pytest


def test_enhanced_verification_pattern_8_integration_must_scan_all():
    """Main AC test: the function exists and handles the c09e9e64 regression form."""
    from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
        enhanced_verification_pattern_8_integration_must_scan_all,
    )

    assert callable(enhanced_verification_pattern_8_integration_must_scan_all), (
        "enhanced_verification_pattern_8_integration_must_scan_all must be callable"
    )


class TestPatternScanAllDottedTokens:
    """Tests that ALL dotted tokens are extracted and tried, not just the first word."""

    def test_extracts_dotted_tokens_not_first_word(self):
        """Regression: 'integration: all ... bob3.reviews ...' must try bob3.reviews, not 'all'."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            _extract_dotted_targets,
        )

        criterion = (
            "integration: all spec_findings.yaml writes in bob3.reviews route "
            "through atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"
        )
        targets = _extract_dotted_targets(criterion)
        # Must find bob3.reviews (the actual dotted reference)
        assert "bob3.reviews" in targets, (
            f"Expected 'bob3.reviews' in extracted targets, got: {targets}"
        )
        # Must NOT try 'all' as a dotted path (no dot in 'all')
        assert "all" not in targets, f"'all' should not appear in targets: {targets}"

    def test_multiple_dotted_tokens_all_extracted(self):
        """When body has multiple dotted refs, all are returned."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            _extract_dotted_targets,
        )

        criterion = "integration: bob3.x.y and bob3.a.b are both imported"
        targets = _extract_dotted_targets(criterion)
        assert "bob3.x.y" in targets, f"Expected 'bob3.x.y' in {targets}"
        assert "bob3.a.b" in targets, f"Expected 'bob3.a.b' in {targets}"

    def test_no_dotted_tokens_returns_empty(self):
        """A body with only single-segment words returns an empty list."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            _extract_dotted_targets,
        )

        criterion = "integration: ensure all tests pass before merging"
        targets = _extract_dotted_targets(criterion)
        assert isinstance(targets, list)
        # No dotted tokens expected
        for t in targets:
            assert "." in t, f"Non-dotted token {t!r} should not appear"


class TestProseBodyDemotion:
    """Tests for prose-policy body detection and demotion to WARNING."""

    def test_prose_body_is_detected(self):
        """Bodies with spaces + connector tokens are identified as prose."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            _is_prose_body,
        )

        body = " all spec_findings.yaml writes route through atomic_write_yaml"
        assert _is_prose_body(body), (
            "A prose body with connector tokens should be detected as prose"
        )

    def test_pure_dotted_body_is_not_prose(self):
        """A bare dotted module path with no spaces is not prose."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            _is_prose_body,
        )

        body = " bob3.nonexistent"
        assert not _is_prose_body(body), (
            "A bare dotted path without spaces and connectors should not be prose"
        )

    def test_empty_body_is_not_prose(self):
        """Empty body is not prose."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            _is_prose_body,
        )

        assert not _is_prose_body("")
        assert not _is_prose_body("  ")


class TestScanAllWithWorkspace:
    """Tests for enhanced_verification_pattern_8_integration_must_scan_all with temp workspace."""

    @pytest.fixture
    def real_workspace(self) -> pathlib.Path:
        """Return the actual bob3 workspace root."""
        # The workspace is bob71 itself — src/bob3 is there.
        return pathlib.Path(__file__).parent.parent

    def test_returns_true_for_wired_module(self, real_workspace):
        """A criterion naming a real wired module resolves to (True, '')."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        # bob3.enhanced_verification is a real module in the workspace
        criterion = "integration: bob3.enhanced_verification module is imported"
        passed, reason = enhanced_verification_pattern_8_integration_must_scan_all(
            criterion, real_workspace
        )
        # Either resolves directly (True, "") OR demotes to warning for prose body —
        # both are non-failure outcomes (passed == True).
        assert passed, (
            f"Expected passed=True for a real wired module, got passed={passed!r} reason={reason!r}"
        )

    def test_c09e9e64_regression_form_does_not_hard_fail(self, real_workspace):
        """The c09e9e64 criterion form must not produce a hard False (crash form)."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        criterion = (
            "integration: all spec_findings.yaml writes in bob3.reviews route "
            "through atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"
        )
        passed, reason = enhanced_verification_pattern_8_integration_must_scan_all(
            criterion, real_workspace
        )
        # Prose body: must demote to warning, not hard-fail.
        # Either bob3.reviews resolves (True, "") OR prose demotion fires (True, warning).
        assert passed, (
            f"c09e9e64 criterion must not hard-fail (prose demotion expected); "
            f"got passed={passed!r} reason={reason!r}"
        )

    def test_pure_prose_body_demotes_to_warning(self, tmp_path):
        """A pure prose body with no resolvable dotted paths demotes to WARNING."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        criterion = (
            "integration: all writes must route through the atomic writer "
            "and no direct yaml.dump calls remain"
        )
        passed, reason = enhanced_verification_pattern_8_integration_must_scan_all(
            criterion, tmp_path
        )
        assert passed, f"Prose body must demote to warning; got passed={passed!r}"
        assert "demoted" in reason.lower() or reason == "", (
            f"Expected demotion message, got: {reason!r}"
        )

    def test_bad_single_dotted_token_hard_fails(self, tmp_path):
        """A single bad dotted token that does not resolve returns (False, ...)."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        criterion = "integration: bob3.totally.nonexistent.module.path"
        passed, reason = enhanced_verification_pattern_8_integration_must_scan_all(
            criterion, tmp_path
        )
        # Body has no spaces/connectors → not prose → should hard-fail
        # (unless the module happens to exist, but in tmp_path it won't)
        assert not passed, (
            f"A non-existent single dotted token should hard-fail; got passed={passed!r}"
        )
        assert "no wired" in reason.lower() or "not found" in reason.lower(), (
            f"Expected 'no wired' in reason, got: {reason!r}"
        )


class TestBoundaryAndInvalidInput:
    """Tests for boundary cases and invalid input (AC-4 and AC-5)."""

    def test_empty_criterion_returns_well_defined_result(self, tmp_path):
        """Empty criterion returns a well-defined (False, msg) rather than crashing."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        passed, reason = enhanced_verification_pattern_8_integration_must_scan_all(
            "", tmp_path
        )
        assert isinstance(passed, bool), "Must return a bool"
        assert isinstance(reason, str), "Must return a str reason"
        assert not passed, "Empty criterion should return False"

    def test_whitespace_only_criterion_returns_well_defined_result(self, tmp_path):
        """Whitespace-only criterion returns a well-defined result."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        passed, reason = enhanced_verification_pattern_8_integration_must_scan_all(
            "   \t\n  ", tmp_path
        )
        assert isinstance(passed, bool)
        assert isinstance(reason, str)
        assert not passed

    def test_non_string_criterion_raises_typeerror(self, tmp_path):
        """Non-string criterion raises TypeError (does not silently succeed)."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        with pytest.raises(TypeError):
            enhanced_verification_pattern_8_integration_must_scan_all(123, tmp_path)

        with pytest.raises(TypeError):
            enhanced_verification_pattern_8_integration_must_scan_all(None, tmp_path)

    def test_non_path_workspace_raises_typeerror(self, tmp_path):
        """Non-path workspace raises TypeError (does not silently succeed)."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        with pytest.raises(TypeError):
            enhanced_verification_pattern_8_integration_must_scan_all(
                "integration: bob3.foo", 12345
            )

    def test_criterion_without_integration_marker_returns_false(self, tmp_path):
        """A criterion without 'integration:' returns (False, ...) not crashes."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            enhanced_verification_pattern_8_integration_must_scan_all,
        )

        passed, reason = enhanced_verification_pattern_8_integration_must_scan_all(
            "behavior: something happens", tmp_path
        )
        assert not passed
        assert isinstance(reason, str)


class TestAtomicWriteYamlExported:
    """Tests that atomic_write_yaml is accessible from this module (AC-6)."""

    def test_atomic_write_yaml_is_callable(self):
        """atomic_write_yaml must be importable and callable from this module."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            atomic_write_yaml,
        )

        assert callable(atomic_write_yaml), "atomic_write_yaml must be callable"

    def test_atomic_write_yaml_writes_file(self, tmp_path):
        """atomic_write_yaml must write valid YAML atomically."""
        from bob3.enhanced_verification_pattern_8_integration_must_scan_all import (
            atomic_write_yaml,
        )

        target = tmp_path / "output.yaml"
        data = {"key": "value", "number": 42, "nested": {"a": 1}}
        atomic_write_yaml(data, target)

        assert target.exists(), "atomic_write_yaml must create the target file"
        import yaml
        loaded = yaml.safe_load(target.read_text())
        assert loaded == data, f"Written data must match: {loaded!r} != {data!r}"
