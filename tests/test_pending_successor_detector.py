"""Tests for bob.pending_successor_detector.detect_pending_successor_verify (F-R7-596).

Covers:
- AC body scan: verifier path-tokens in AC bodies trigger deferral
- Target-file scan: files referenced by 'File exists:' ACs are scanned
- Title-fallback: feature name contains 'verifier' + behavior: AC with keywords
- Safe defaults: invalid/empty/None input handled gracefully or raises
- Integration path: detect_pending_successor_verify is importable from bob.run_loop
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from bob.pending_successor_detector import detect_pending_successor_verify


# ---------------------------------------------------------------------------
# AC body scan — path-token matches
# ---------------------------------------------------------------------------


def test_ac_body_with_enhanced_verification_returns_true():
    """AC body containing 'enhanced_verification' must return True."""
    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/enhanced_verification.py"],
    )
    assert result is True


def test_ac_body_with_full_path_token_returns_true():
    """AC body containing the full path 'src/bob/enhanced_verification.py' returns True."""
    result = detect_pending_successor_verify(
        "my feature",
        ["File exists: src/bob/enhanced_verification.py"],
    )
    assert result is True


def test_ac_body_with_verification_suffix_returns_true():
    """AC body with a path ending in '_verification.py' returns True."""
    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/my_verification.py"],
    )
    assert result is True


def test_ac_body_with_verifier_suffix_returns_true():
    """AC body with a path ending in '_verifier.py' returns True."""
    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/ac_verifier.py"],
    )
    assert result is True


def test_ac_body_without_tokens_returns_false():
    """AC body with no verifier tokens returns False."""
    result = detect_pending_successor_verify(
        "my feature",
        ["File exists: src/bob/dispatch.py", "Function defined: bob.dispatch.run"],
    )
    assert result is False


def test_ac_body_scan_short_circuits_on_first_match():
    """Detection short-circuits on first matching AC — rest of list irrelevant."""
    result = detect_pending_successor_verify(
        "my feature",
        [
            "enhanced_verification must handle pattern X",
            "File exists: src/bob/unrelated.py",
        ],
    )
    assert result is True


def test_multiple_acs_none_match_returns_false():
    """Multiple ACs with no tokens returns False."""
    result = detect_pending_successor_verify(
        "my feature",
        [
            "File exists: src/bob/run_loop.py",
            "Function defined: bob.run_loop.start",
            "pytest: tests/test_run_loop.py",
        ],
    )
    assert result is False


# ---------------------------------------------------------------------------
# Target-file scan
# ---------------------------------------------------------------------------


def test_target_file_scan_detects_verifier_import(tmp_path):
    """A file referenced via 'File exists:' that imports enhanced_verification triggers deferral."""
    target_file = tmp_path / "src" / "bob" / "some_handler.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("from bob import enhanced_verification\n", encoding="utf-8")

    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/some_handler.py"],
        workspace=str(tmp_path),
    )
    assert result is True


def test_target_file_scan_negative_when_no_token(tmp_path):
    """A referenced file without verifier tokens does not trigger deferral."""
    target_file = tmp_path / "src" / "bob" / "plain.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("def run(): pass\n", encoding="utf-8")

    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/plain.py"],
        workspace=str(tmp_path),
    )
    assert result is False


def test_target_file_scan_skipped_when_no_workspace():
    """When workspace is None, target-file scan is skipped entirely (no I/O)."""
    # The AC references a file that doesn't exist in cwd; no exception should occur.
    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/nonexistent_module.py"],
        workspace=None,
    )
    # Without workspace, no target-file scan; AC body "nonexistent_module.py" has no token.
    assert result is False


def test_target_file_missing_does_not_raise(tmp_path):
    """A referenced file that doesn't exist returns False without raising."""
    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/does_not_exist.py"],
        workspace=str(tmp_path),
    )
    assert result is False


def test_target_file_with_suffix_verifier_token(tmp_path):
    """File containing 'my_verifier.py' path reference triggers deferral."""
    target_file = tmp_path / "src" / "bob" / "some_module.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("# loads from ac_verifier.py\n", encoding="utf-8")

    result = detect_pending_successor_verify(
        "some feature",
        ["File exists: src/bob/some_module.py"],
        workspace=str(tmp_path),
    )
    assert result is True


# ---------------------------------------------------------------------------
# Title-fallback
# ---------------------------------------------------------------------------


def test_title_with_verifier_and_behavior_ac_returns_true():
    """Feature name containing 'verifier' + behavior: AC with semantics keywords triggers."""
    result = detect_pending_successor_verify(
        "AC artifact-existence verifier",
        [
            "File exists: src/bob/ac_artifact_verifier.py",
            "behavior: when referenced files are missing, refuse to pass the AC",
        ],
    )
    assert result is True


def test_title_with_verifier_no_behavior_acs_returns_false():
    """Feature name with 'verifier' but no behavior: ACs does not trigger title-fallback."""
    result = detect_pending_successor_verify(
        "AC artifact-existence verifier",
        ["File exists: src/bob/some_unrelated.py"],
    )
    assert result is False


def test_title_without_verifier_with_behavior_keywords_returns_false():
    """Feature name without 'verifier' and behavior: with keywords does not trigger."""
    result = detect_pending_successor_verify(
        "my plain feature",
        ["behavior: must verify that criterion is satisfied"],
    )
    assert result is False


def test_title_fallback_case_insensitive():
    """Title-fallback check for 'verifier' is case-insensitive."""
    result = detect_pending_successor_verify(
        "AC Artifact-Existence VERIFIER",
        ["behavior: refuse to pass the AC when files are missing"],
    )
    assert result is True


def test_title_fallback_does_not_trigger_without_semantics_keywords():
    """Title contains 'verifier' but behavior: AC has no semantics keywords."""
    result = detect_pending_successor_verify(
        "my verifier feature",
        ["behavior: when user runs, output is printed to stdout"],
    )
    assert result is False


# ---------------------------------------------------------------------------
# JSON-encoded AC lists
# ---------------------------------------------------------------------------


def test_json_encoded_ac_list_with_token_returns_true():
    """JSON-encoded AC list with enhanced_verification token returns True."""
    ac_json = json.dumps(["File exists: src/bob/enhanced_verification.py"])
    result = detect_pending_successor_verify("my feature", ac_json)
    assert result is True


def test_json_encoded_ac_list_without_token_returns_false():
    """JSON-encoded AC list without tokens returns False."""
    ac_json = json.dumps(["File exists: src/bob/run_loop.py"])
    result = detect_pending_successor_verify("my feature", ac_json)
    assert result is False


def test_malformed_json_returns_false():
    """Malformed JSON AC string returns False without raising."""
    result = detect_pending_successor_verify("my feature", "not-valid-json{{{")
    assert result is False


# ---------------------------------------------------------------------------
# None and empty input
# ---------------------------------------------------------------------------


def test_none_acceptance_criteria_returns_false():
    """None acceptance_criteria returns False (safe default)."""
    result = detect_pending_successor_verify("some feature", None)
    assert result is False


def test_empty_list_returns_false():
    """Empty AC list returns False."""
    result = detect_pending_successor_verify("some feature", [])
    assert result is False


def test_empty_string_ac_returns_false():
    """Empty string AC list returns False."""
    result = detect_pending_successor_verify("some feature", "")
    assert result is False


def test_whitespace_only_acs_return_false():
    """Whitespace-only ACs return False."""
    result = detect_pending_successor_verify("some feature", ["  ", "\t", "\n"])
    assert result is False


# ---------------------------------------------------------------------------
# Return type is always bool
# ---------------------------------------------------------------------------


def test_returns_bool_on_true_path():
    """Returns exactly bool True, not a truthy value."""
    result = detect_pending_successor_verify(
        "my feature",
        ["enhanced_verification keyword here"],
    )
    assert result is True
    assert isinstance(result, bool)


def test_returns_bool_on_false_path():
    """Returns exactly bool False, not a falsy value."""
    result = detect_pending_successor_verify("my feature", [])
    assert result is False
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Integration: callable from bob.run_loop
# ---------------------------------------------------------------------------


def test_importable_from_run_loop():
    """detect_pending_successor_verify must be importable from bob.run_loop."""
    from bob.run_loop import detect_pending_successor_verify as run_loop_fn
    assert callable(run_loop_fn)


def test_run_loop_delegate_matches_detector():
    """bob.run_loop.detect_pending_successor_verify delegates to the detector."""
    from bob.run_loop import detect_pending_successor_verify as run_loop_fn

    acs = ["File exists: src/bob/enhanced_verification.py"]
    detector_result = detect_pending_successor_verify("my feature", acs)
    run_loop_result = run_loop_fn("my feature", acs)
    assert detector_result == run_loop_result is True
