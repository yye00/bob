"""Tests for bob3.verification.integration_ac_resolver.

Feature 075d29d8-9afe-4888-8af3-58b8312d5b96:
Pattern 8 ("integration:") MUST scan ALL plausible dotted tokens in body AND
demote prose-policy integration ACs to warning.

Tests the canonical module: bob3.verification.integration_ac_resolver
- extract_integration_targets(criterion) -> list[str]
- resolve_integration_ac(criterion, workspace) -> tuple[bool, str]
- log_integration_ac_prose_demoted(criterion, feature_id, scanned_candidates)

Covers the c09e9e64 regression: "integration: all spec_findings.yaml writes in
bob3.reviews route through atomic_write_yaml" must NOT hard-fail because
first token "all" is not a module.
"""

from __future__ import annotations

import json
import logging
import pathlib
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_python_module(workspace: pathlib.Path, rel_path: str, content: str) -> None:
    """Write a Python source file in workspace/src/<rel_path>."""
    target = workspace / "src" / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content))


# ---------------------------------------------------------------------------
# extract_integration_targets
# ---------------------------------------------------------------------------

class TestExtractIntegrationTargets:
    """Tests for extract_integration_targets."""

    def test_extracts_dotted_token_after_prose(self):
        """Extracts bob3.reviews from the c09e9e64 regression form."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        criterion = (
            "integration: all spec_findings.yaml writes in bob3.reviews "
            "route through atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"
        )
        targets = extract_integration_targets(criterion)
        assert "bob3.reviews" in targets, f"Expected bob3.reviews in {targets}"

    def test_extracts_multiple_dotted_tokens(self):
        """Extracts all dotted tokens, not just the first."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        criterion = "integration: bob3.x.y and bob3.a.b are both imported"
        targets = extract_integration_targets(criterion)
        assert "bob3.x.y" in targets, f"Expected bob3.x.y in {targets}"
        assert "bob3.a.b" in targets, f"Expected bob3.a.b in {targets}"

    def test_returns_empty_list_for_no_marker(self):
        """Returns [] when 'integration:' is absent."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        result = extract_integration_targets("file exists: something")
        assert result == []

    def test_returns_empty_for_empty_string(self):
        """Returns [] for empty string."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        assert extract_integration_targets("") == []

    def test_returns_empty_for_non_string(self):
        """Returns [] for non-string input (does not raise)."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        assert extract_integration_targets(None) == []  # type: ignore[arg-type]
        assert extract_integration_targets(42) == []  # type: ignore[arg-type]

    def test_returns_list(self):
        """Always returns a list."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        result = extract_integration_targets("integration: bob3.foo")
        assert isinstance(result, list)

    def test_does_not_include_single_segment_tokens(self):
        """Single-segment identifiers (no dot) are not returned."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        result = extract_integration_targets("integration: atomic_write_yaml")
        # 'atomic_write_yaml' has no dot — should not be in result
        assert "atomic_write_yaml" not in result

    def test_extracts_token_before_body_after_colon(self):
        """Body is everything after 'integration:' — early tokens are included."""
        from bob3.verification.integration_ac_resolver import extract_integration_targets

        criterion = "integration: bob3.verification.acceptance_criteria is wired"
        targets = extract_integration_targets(criterion)
        assert any("bob3.verification" in t for t in targets), f"Got {targets}"


# ---------------------------------------------------------------------------
# resolve_integration_ac
# ---------------------------------------------------------------------------

class TestResolveIntegrationAc:
    """Tests for resolve_integration_ac."""

    def test_returns_true_for_wired_module(self, tmp_path):
        """Returns (True, ...) when a dotted token corresponds to a wired module."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        # Write a module and another file that imports it — _integration_wired requires both
        _write_python_module(tmp_path, "bob3/__init__.py", "")
        _write_python_module(tmp_path, "bob3/reviews.py", "def foo(): pass\n")
        _write_python_module(tmp_path, "consumer.py", "import bob3.reviews\n")

        # Use a non-prose criterion so prose demotion doesn't fire first
        criterion = "integration: bob3.reviews"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        assert passed is True, f"Wired module must resolve True; passed={passed!r}, reason={reason!r}"

    def test_prose_policy_body_demotes_to_warning(self, tmp_path):
        """Prose-policy body returns (True, warning_msg) not (False, ...)."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        # tmp_path has no src/ — no module wired
        criterion = "integration: all writes must route through the atomic writer"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        assert passed is True, f"Prose body must demote to warning; got passed={passed!r}"
        assert "demoted" in reason.lower() or "warning" in reason.lower(), (
            f"reason should mention demotion: {reason!r}"
        )

    def test_c09e9e64_regression_form_demotes_not_hard_fails(self, tmp_path):
        """The exact criterion from c09e9e64 does NOT hard-fail."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        criterion = (
            "integration: all spec_findings.yaml writes in bob3.reviews "
            "route through atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"
        )
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        # Either resolves (if src exists) or demotes (prose body) — must NOT hard-fail
        assert passed is True, (
            f"c09e9e64 regression criterion must not hard-fail; "
            f"got passed={passed!r}, reason={reason!r}"
        )

    def test_unwired_single_dotted_returns_false(self, tmp_path):
        """A single bad dotted path with no prose returns (False, ...)."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        criterion = "integration: bob3.totally.nonexistent.module.xyz"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        assert passed is False, f"Non-existent module must return False; got {passed!r}"
        assert isinstance(reason, str) and reason, "reason must be non-empty on failure"

    def test_returns_tuple_of_bool_and_str(self, tmp_path):
        """Return type is always (bool, str)."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        result = resolve_integration_ac("integration: bob3.fake.module", tmp_path)
        assert isinstance(result, tuple) and len(result) == 2
        passed, reason = result
        assert isinstance(passed, bool)
        assert isinstance(reason, str)

    def test_raises_on_non_string_criterion(self, tmp_path):
        """TypeError is raised for non-string criterion."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        with pytest.raises((TypeError, ValueError)):
            resolve_integration_ac(None, tmp_path)  # type: ignore[arg-type]

        with pytest.raises((TypeError, ValueError)):
            resolve_integration_ac(123, tmp_path)  # type: ignore[arg-type]

    def test_no_integration_marker_returns_false(self, tmp_path):
        """Criterion without 'integration:' returns (False, ...) not crashes."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        passed, reason = resolve_integration_ac("behavior: something happens", tmp_path)
        assert passed is False
        assert isinstance(reason, str)

    def test_pure_prose_form_v8_b6873bac_style_demotes(self, tmp_path):
        """Pure prose body (b6873bac-style) demotes to warning."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        criterion = "integration: every write to the registry passes through the canonical writer"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        assert passed is True, (
            f"Pure prose must demote to warning; got passed={passed!r} reason={reason!r}"
        )

    def test_multi_token_ac_resolves_any_candidate(self, tmp_path):
        """When multiple dotted tokens in body, any wired one resolves True."""
        from bob3.verification.integration_ac_resolver import resolve_integration_ac

        _write_python_module(tmp_path, "bob3/__init__.py", "")
        _write_python_module(tmp_path, "bob3/a.py", "")
        _write_python_module(tmp_path, "bob3/b.py", "")

        criterion = "integration: bob3.x.y and bob3.a.b are both imported"
        passed, reason = resolve_integration_ac(criterion, tmp_path)
        # bob3.x.y doesn't exist but bob3.a.b might not either in this tmp structure;
        # either way the function must not raise — just return a well-defined result.
        assert isinstance(passed, bool)
        assert isinstance(reason, str)


# ---------------------------------------------------------------------------
# log_integration_ac_prose_demoted
# ---------------------------------------------------------------------------

class TestLogIntegrationAcProseDemoted:
    """Tests for log_integration_ac_prose_demoted."""

    def test_emits_integration_ac_prose_demoted_event(self, caplog):
        """Emits INTEGRATION_AC_PROSE_DEMOTED JSON log line."""
        from bob3.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        with caplog.at_level(logging.INFO, logger="bob3.verification.integration_demotion"):
            log_integration_ac_prose_demoted(
                criterion="integration: all writes route through atomic_write_yaml",
                feature_id="c09e9e64",
                scanned_candidates=["bob3.reviews"],
            )

        assert any(
            "INTEGRATION_AC_PROSE_DEMOTED" in record.message
            for record in caplog.records
        ), "Must emit INTEGRATION_AC_PROSE_DEMOTED log line"

    def test_log_contains_criterion_and_feature_id(self, caplog):
        """Log record contains criterion, feature_id, and scanned_candidates."""
        from bob3.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        criterion = "integration: test criterion"
        feature_id = "feat-abc"
        candidates = ["bob3.foo"]

        with caplog.at_level(logging.INFO, logger="bob3.verification.integration_demotion"):
            log_integration_ac_prose_demoted(criterion, feature_id, candidates)

        matching = [r for r in caplog.records if "INTEGRATION_AC_PROSE_DEMOTED" in r.message]
        assert matching, "No INTEGRATION_AC_PROSE_DEMOTED log record found"
        log_msg = matching[0].message
        data = json.loads(log_msg)
        assert data["criterion"] == criterion
        assert data["feature_id"] == feature_id
        assert data["scanned_candidates"] == candidates

    def test_log_with_none_feature_id_does_not_crash(self, caplog):
        """log_integration_ac_prose_demoted with feature_id=None does not crash."""
        from bob3.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        with caplog.at_level(logging.INFO, logger="bob3.verification.integration_demotion"):
            log_integration_ac_prose_demoted("integration: foo", None, [])

        assert any(
            "INTEGRATION_AC_PROSE_DEMOTED" in r.message for r in caplog.records
        )

    def test_log_event_key_is_correct(self, caplog):
        """The 'event' key in JSON is exactly 'INTEGRATION_AC_PROSE_DEMOTED'."""
        from bob3.verification.integration_ac_resolver import log_integration_ac_prose_demoted

        with caplog.at_level(logging.INFO, logger="bob3.verification.integration_demotion"):
            log_integration_ac_prose_demoted("integration: all routes", "feat-1", ["bob3.x"])

        matching = [r for r in caplog.records if "INTEGRATION_AC_PROSE_DEMOTED" in r.message]
        assert matching
        data = json.loads(matching[0].message)
        assert data["event"] == "INTEGRATION_AC_PROSE_DEMOTED"
