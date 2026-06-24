"""Tests for bob.pending_successor_verifier.detect_pending_successor_verify (F-R7-596).

Verifies the broadened pending_successor_verify detection that includes:
- AC body scan for verifier path-tokens
- Target-file scan for referenced files
- Title-fallback detection
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Import verification
# ---------------------------------------------------------------------------


def test_module_importable():
    """The pending_successor_verifier module must be importable."""
    import bob.pending_successor_verifier  # noqa: F401


def test_function_importable():
    """detect_pending_successor_verify must be importable from the module."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    assert callable(detect_pending_successor_verify)


# ---------------------------------------------------------------------------
# AC body scan: verifier path-tokens
# ---------------------------------------------------------------------------


def test_ac_body_with_enhanced_verification_returns_true():
    """AC body containing 'enhanced_verification' must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs = ["File exists: src/bob/enhanced_verification.py"]
    assert detect_pending_successor_verify("some feature", acs) is True


def test_ac_body_with_enhanced_verification_substring_returns_true():
    """AC body containing 'enhanced_verification' as a substring must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs = ["behavior: enhanced_verification must handle this case"]
    assert detect_pending_successor_verify("some feature", acs) is True


def test_ac_body_with_verification_py_suffix_returns_true():
    """AC body referencing a file ending in '_verification.py' must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs = ["File exists: src/bob/custom_verification.py"]
    assert detect_pending_successor_verify("some feature", acs) is True


def test_ac_body_with_verifier_py_suffix_returns_true():
    """AC body referencing a file ending in '_verifier.py' must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs = ["File exists: src/bob/my_verifier.py"]
    assert detect_pending_successor_verify("some feature", acs) is True


def test_ac_body_without_verifier_tokens_returns_false():
    """AC body with no verifier tokens must return False (no title match)."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs = ["File exists: src/bob/my_module.py", "pytest: tests/test_my_module.py"]
    assert detect_pending_successor_verify("generic feature", acs) is False


def test_multiple_acs_one_with_token_returns_true():
    """When one of multiple ACs contains a verifier token, must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs = [
        "File exists: src/bob/some_module.py",
        "File exists: src/bob/enhanced_verification.py",
        "pytest: tests/test_something.py",
    ]
    assert detect_pending_successor_verify("generic feature", acs) is True


# ---------------------------------------------------------------------------
# Target-file scan
# ---------------------------------------------------------------------------


def test_target_file_scan_finds_verifier_import(tmp_path):
    """A 'File exists:' AC pointing to a file that imports enhanced_verification must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    target_file = tmp_path / "src" / "bob" / "my_handler.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        "from bob import enhanced_verification\n\n"
        "def handle(): pass\n",
        encoding="utf-8",
    )

    acs = ["File exists: src/bob/my_handler.py"]
    result = detect_pending_successor_verify("generic feature", acs, workspace=tmp_path)
    assert result is True


def test_target_file_scan_clean_file_returns_false(tmp_path):
    """A 'File exists:' AC pointing to a file without verifier tokens must return False."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    target_file = tmp_path / "src" / "bob" / "my_handler.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        "def handle(): return True\n",
        encoding="utf-8",
    )

    acs = ["File exists: src/bob/my_handler.py"]
    result = detect_pending_successor_verify("generic feature", acs, workspace=tmp_path)
    assert result is False


def test_target_file_scan_missing_file_returns_false(tmp_path):
    """A 'File exists:' AC pointing to a nonexistent file must return False (no exception)."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    acs = ["File exists: src/bob/nonexistent_file.py"]
    result = detect_pending_successor_verify("generic feature", acs, workspace=tmp_path)
    assert result is False


def test_target_file_scan_skipped_when_workspace_none():
    """Target-file scan is skipped when workspace=None."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    # AC references a file, but no workspace — scan is skipped
    acs = ["File exists: src/bob/my_module.py"]
    result = detect_pending_successor_verify("generic feature", acs, workspace=None)
    assert result is False


def test_target_file_scan_with_verifier_py_suffix_in_content(tmp_path):
    """File content referencing another _verifier.py path triggers detection."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    target_file = tmp_path / "src" / "bob" / "my_handler.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        "# delegates to custom_verifier.py\n"
        "import custom_verifier\n",
        encoding="utf-8",
    )

    acs = ["File exists: src/bob/my_handler.py"]
    result = detect_pending_successor_verify("generic feature", acs, workspace=tmp_path)
    assert result is True


# ---------------------------------------------------------------------------
# Title-fallback
# ---------------------------------------------------------------------------


def test_title_fallback_verifier_title_with_behavior_ac():
    """Feature title containing 'verifier' with behavior: AC referencing verification must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    acs = [
        "File exists: src/bob/my_checker.py",
        "behavior: when criteria are checked, the verifier must accept the result",
    ]
    result = detect_pending_successor_verify(
        "my_verifier feature", acs
    )
    assert result is True


def test_title_fallback_no_verifier_in_title_returns_false():
    """Feature title without 'verifier' must NOT trigger title-fallback."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    acs = [
        "behavior: when criteria are checked, the result must be accepted",
    ]
    result = detect_pending_successor_verify("my_checker feature", acs)
    assert result is False


def test_title_fallback_verifier_title_no_behavior_ac_returns_false():
    """Title with 'verifier' but no behavior: AC with semantics must return False."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    acs = ["File exists: src/bob/my_checker.py", "pytest: tests/test_checker.py"]
    result = detect_pending_successor_verify("my_verifier feature", acs)
    assert result is False


def test_title_fallback_case_insensitive():
    """Title containing 'Verifier' (uppercase V) must also trigger fallback."""
    from bob.pending_successor_verifier import detect_pending_successor_verify

    acs = [
        "behavior: the criterion must be verified and the artifact accepted",
    ]
    result = detect_pending_successor_verify("AC Verifier Extension", acs)
    assert result is True


# ---------------------------------------------------------------------------
# AC list parsing
# ---------------------------------------------------------------------------


def test_none_acceptance_criteria_returns_false():
    """None must return False, not raise."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    result = detect_pending_successor_verify("some feature", None)
    assert result is False


def test_empty_list_returns_false():
    """Empty list must return False, not raise."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    result = detect_pending_successor_verify("some feature", [])
    assert result is False


def test_json_encoded_list_with_token_returns_true():
    """JSON-encoded list containing a verifier token must return True."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs_json = json.dumps(["File exists: src/bob/enhanced_verification.py"])
    result = detect_pending_successor_verify("some feature", acs_json)
    assert result is True


def test_json_encoded_empty_list_returns_false():
    """JSON-encoded empty list must return False."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    result = detect_pending_successor_verify("some feature", "[]")
    assert result is False


def test_invalid_type_raises_value_error():
    """Non-list/str/None type must raise ValueError."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    with pytest.raises(ValueError, match="int"):
        detect_pending_successor_verify("some feature", 42)  # type: ignore[arg-type]


def test_dict_type_raises_value_error():
    """Dict type must raise ValueError."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    with pytest.raises(ValueError, match="dict"):
        detect_pending_successor_verify("some feature", {"key": "value"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


def test_returns_bool_true():
    """Function must return exactly bool True when triggered."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    acs = ["behavior: enhanced_verification must be extended"]
    result = detect_pending_successor_verify("some feature", acs)
    assert result is True
    assert isinstance(result, bool)


def test_returns_bool_false():
    """Function must return exactly bool False when not triggered."""
    from bob.pending_successor_verifier import detect_pending_successor_verify
    result = detect_pending_successor_verify("some feature", [])
    assert result is False
    assert isinstance(result, bool)
