"""Tests for pending_successor_verify_auto_defer_verifier_self_extension.

Acceptance criteria:
- File exists: src/bob3/pending_successor_verify_auto_defer_verifier_self_extension.py
- Function defined: bob3.pending_successor_verify_auto_defer_verifier_self_extension.pending_successor_verify_auto_defer_verifier_self_extension
- pytest: tests/test_pending_successor_verify_auto_defer_verifier_self_extension.py::test_pending_successor_verify_auto_defer_verifier_self_extension
"""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


FEATURE_NAME_VERIFIER = (
    "AC artifact-existence verifier — refuse to pass AC when referenced files are missing"
)
FEATURE_NAME_REGULAR = "Periodic resume scan — promote interrupted rows mid-run"

VERIFIER_BEHAVIOR_ACS = [
    "behavior: enhanced_verification._check_criterion_with_details MUST demote pure-prose",
    "behavior: _demote_prose_ac_failures must match structural prefixes at START-of-string",
    "pytest: tests/test_enhanced_verification.py",
]

REGULAR_ACS = [
    "File exists: src/bob3/periodic_resume_scan.py",
    "pytest: tests/test_periodic_resume_scan.py",
    "Function defined: bob3.periodic_resume_scan.resume_scan",
]


# ---------------------------------------------------------------------------
# Primary test (named to match AC pytest path)
# ---------------------------------------------------------------------------


def test_pending_successor_verify_auto_defer_verifier_self_extension():
    """Core integration test: function is importable and callable, returns correct types."""
    from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
        pending_successor_verify_auto_defer_verifier_self_extension,
    )

    # Should return True (defer) for a feature with behavior ACs targeting verifier internals
    result = pending_successor_verify_auto_defer_verifier_self_extension(
        feature_id="d0b94fd0-0000-0000-0000-000000000001",
        feature_name=FEATURE_NAME_VERIFIER,
        acceptance_criteria=VERIFIER_BEHAVIOR_ACS,
    )
    assert isinstance(result, bool)
    assert result is True

    # Should return False (no defer) for a regular feature with no verifier self-extension ACs
    result_regular = pending_successor_verify_auto_defer_verifier_self_extension(
        feature_id="a1b2c3d4-0000-0000-0000-000000000002",
        feature_name=FEATURE_NAME_REGULAR,
        acceptance_criteria=REGULAR_ACS,
    )
    assert isinstance(result_regular, bool)
    assert result_regular is False


# ---------------------------------------------------------------------------
# File and module existence
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_module_file_exists(self):
        import bob3.pending_successor_verify_auto_defer_verifier_self_extension as mod
        p = Path(mod.__file__)
        assert p.exists()
        assert p.name == "pending_successor_verify_auto_defer_verifier_self_extension.py"

    def test_module_importable(self):
        importlib.import_module(
            "bob3.pending_successor_verify_auto_defer_verifier_self_extension"
        )

    def test_function_defined(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        assert callable(pending_successor_verify_auto_defer_verifier_self_extension)


# ---------------------------------------------------------------------------
# Behavior: defer when behavior AC references verifier internals
# ---------------------------------------------------------------------------


class TestDeferOnVerifierInternalBehaviorAC:
    def test_defers_on_enhanced_verification_in_behavior_ac(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = ["behavior: enhanced_verification._check_criterion_with_details MUST demote"]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-001", "Feature with verifier AC", acs
        )
        assert result is True

    def test_defers_on_check_criterion_in_behavior_ac(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = ["behavior: _check_criterion must never fail silently"]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-002", "Some feature", acs
        )
        assert result is True

    def test_defers_on_demote_keyword_in_behavior_ac(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = ["behavior: _demote_prose_ac_failures must match at START-of-string"]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-003", "Some feature", acs
        )
        assert result is True

    def test_defers_on_verifier_keyword_in_behavior_ac(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = ["behavior: verifier must reject features with missing artifact files"]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-004", "Some feature", acs
        )
        assert result is True

    def test_defers_even_when_mixed_acs(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = [
            "File exists: src/bob3/mymod.py",
            "behavior: enhanced_verification._check_criterion_with_details MUST demote",
            "pytest: tests/test_mymod.py",
        ]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-005", "Some verifier feature", acs
        )
        assert result is True


# ---------------------------------------------------------------------------
# Behavior: do NOT defer regular (non-verifier-self-extension) features
# ---------------------------------------------------------------------------


class TestNoDefer:
    def test_no_defer_for_regular_feature(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-010", FEATURE_NAME_REGULAR, REGULAR_ACS
        )
        assert result is False

    def test_no_defer_when_no_behavior_acs(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = [
            "File exists: src/bob3/enhanced_verification.py",
            "pytest: tests/test_enhanced_verification.py",
        ]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-011", "some feature", acs
        )
        assert result is False

    def test_no_defer_when_behavior_ac_has_no_verifier_keywords(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = [
            "behavior: when the command runs, output is printed to stdout",
            "pytest: tests/test_cmd.py",
        ]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-012", "CLI output feature", acs
        )
        assert result is False

    def test_no_defer_for_empty_acs(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-013", "Empty ACs feature", []
        )
        assert result is False

    def test_no_defer_for_none_acs(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-014", "None ACs feature", None
        )
        assert result is False

    def test_no_defer_when_verifier_keyword_only_in_structural_ac(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = [
            "File exists: src/bob3/enhanced_verification.py",
            "Function defined: bob3.enhanced_verification.new_fn",
        ]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-015", "some feature", acs
        )
        # No behavior ACs, so no defer
        assert result is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_handles_json_encoded_acs(self):
        import json
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs_json = json.dumps([
            "behavior: enhanced_verification must demote pure-prose AC failures to warnings",
        ])
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-020", "some feature", acs_json
        )
        assert result is True

    def test_handles_json_regular_acs(self):
        import json
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs_json = json.dumps(REGULAR_ACS)
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-021", FEATURE_NAME_REGULAR, acs_json
        )
        assert result is False

    def test_returns_false_on_invalid_json_input(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-022", "some feature", "not-json{"
        )
        assert result is False

    def test_case_insensitive_behavior_prefix(self):
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        acs = ["Behavior: enhanced_verification must not silently ignore errors"]
        result = pending_successor_verify_auto_defer_verifier_self_extension(
            "feat-023", "some feature", acs
        )
        assert result is True

    def test_all_three_v27_failed_features_would_be_deferred(self):
        """Reproduce the three v.27 failed features from the spec — all should defer."""
        from bob3.pending_successor_verify_auto_defer_verifier_self_extension import (
            pending_successor_verify_auto_defer_verifier_self_extension,
        )
        # d0b94fd0: AC artifact-existence verifier
        r1 = pending_successor_verify_auto_defer_verifier_self_extension(
            "d0b94fd0-0000-0000-0000-000000000001",
            "AC artifact-existence verifier — refuse to pass AC when referenced files are missing",
            ["behavior: verifier MUST refuse to pass an AC when the file it references does not exist",
             "behavior: _check_criterion emits 'missing artifact' and marks the AC as failed"],
        )
        assert r1 is True

        # d5879353: enhanced_verification._check_criterion_with_details demotion
        r2 = pending_successor_verify_auto_defer_verifier_self_extension(
            "d5879353-0000-0000-0000-000000000002",
            "enhanced_verification._check_criterion_with_details MUST demote pure-prose AC failures",
            ["behavior: _check_criterion_with_details must demote pure-prose failures to warning",
             "behavior: enhanced_verification must not hard-fail on prose-only ACs"],
        )
        assert r2 is True

        # 899825df: Prose-AC and integration-AC demoters must match at START-of-string
        r3 = pending_successor_verify_auto_defer_verifier_self_extension(
            "899825df-0000-0000-0000-000000000003",
            "Prose-AC and integration-AC demoters MUST match structural prefixes at START-of-string",
            ["behavior: _demote_prose_ac_failures must only trigger at START-of-string prefix",
             "behavior: _demote_ handler must reject mid-string prefix occurrences"],
        )
        assert r3 is True
