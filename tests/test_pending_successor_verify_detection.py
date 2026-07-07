"""Detection tests for the broadened pending_successor_verify detector (F-R7-596).

Feature 52f56c50: broaden verifier-self-extension detection to a target-file
scan (not just AC body wording). Exercises the two public entry points exposed
on :mod:`bob.enhanced_verification`:

- ``scan_ac_for_verifier_tokens(acceptance_criteria)`` — return True when any AC
  body contains a verifier path-token (``enhanced_verification``,
  ``*_verification.py``, ``*_verifier.py``).
- ``mark_pending_successor_verify(feature_id, feature_name, acceptance_criteria)``
  — pre-dispatch gate that defers a verifier-targeting feature to the successor
  generation via a DB status update.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# scan_ac_for_verifier_tokens — positive detection
# ---------------------------------------------------------------------------


def test_scan_detects_enhanced_verification_token():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    acs = ["behavior: enhanced_verification must reject missing artifacts"]
    assert scan_ac_for_verifier_tokens(acs) is True


def test_scan_detects_verification_py_suffix_path():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    acs = ["File exists: src/bob/ac_artifact_verification.py"]
    assert scan_ac_for_verifier_tokens(acs) is True


def test_scan_detects_verifier_py_suffix_path():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    acs = ["File exists: src/bob/ac_artifact_verifier.py"]
    assert scan_ac_for_verifier_tokens(acs) is True


def test_scan_detects_full_enhanced_verification_path():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    acs = ["Function defined: src/bob/enhanced_verification.py::foo"]
    assert scan_ac_for_verifier_tokens(acs) is True


def test_scan_accepts_json_encoded_list():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    acs = '["behavior: extend enhanced_verification with new pattern"]'
    assert scan_ac_for_verifier_tokens(acs) is True


# ---------------------------------------------------------------------------
# scan_ac_for_verifier_tokens — negative detection
# ---------------------------------------------------------------------------


def test_scan_ignores_non_verifier_acs():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    acs = [
        "File exists: src/bob/some_module.py",
        "behavior: when the user runs the command, output goes to stdout",
    ]
    assert scan_ac_for_verifier_tokens(acs) is False


def test_scan_none_returns_false():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    assert scan_ac_for_verifier_tokens(None) is False


def test_scan_empty_list_returns_false():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    assert scan_ac_for_verifier_tokens([]) is False


def test_scan_returns_bool_type():
    from bob.enhanced_verification import scan_ac_for_verifier_tokens
    result = scan_ac_for_verifier_tokens(["behavior: enhanced_verification"])
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# mark_pending_successor_verify — DB gate
# ---------------------------------------------------------------------------


def test_mark_returns_false_for_non_verifier_feature(monkeypatch):
    """A feature that does not target the verifier must NOT be deferred."""
    import bob.pending_successor_verify as psv

    called = {"updated": False}

    def _fake_update(feature_id, **kwargs):
        called["updated"] = True

    monkeypatch.setattr(psv.db, "update_feature", _fake_update)

    from bob.enhanced_verification import mark_pending_successor_verify
    result = mark_pending_successor_verify(
        "feat-1",
        "Add a plain CLI flag",
        ["File exists: src/bob/cli.py"],
    )
    assert result is False
    assert called["updated"] is False


def test_mark_defers_verifier_feature_and_updates_db(monkeypatch):
    """A verifier-targeting feature must be marked pending_successor_verify."""
    import bob.pending_successor_verify as psv

    captured = {}

    def _fake_update(feature_id, **kwargs):
        captured["feature_id"] = feature_id
        captured["status"] = kwargs.get("status")

    monkeypatch.setattr(psv.db, "update_feature", _fake_update)

    from bob.enhanced_verification import mark_pending_successor_verify
    result = mark_pending_successor_verify(
        "feat-2",
        "AC artifact-existence verifier",
        ["behavior: enhanced_verification must refuse to pass when files missing"],
    )
    assert result is True
    assert captured["feature_id"] == "feat-2"
    assert captured["status"] == "pending_successor_verify"


def test_mark_returns_false_on_db_error(monkeypatch):
    """A DB error during the deferral update must return False, not raise."""
    import bob.pending_successor_verify as psv

    def _boom(feature_id, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(psv.db, "update_feature", _boom)

    from bob.enhanced_verification import mark_pending_successor_verify
    result = mark_pending_successor_verify(
        "feat-3",
        "AC artifact-existence verifier",
        ["behavior: enhanced_verification must refuse to pass"],
    )
    assert result is False


# ---------------------------------------------------------------------------
# integration: module importable and API surface present
# ---------------------------------------------------------------------------


def test_integration_enhanced_verification_exposes_api():
    import bob.enhanced_verification as ev

    assert hasattr(ev, "scan_ac_for_verifier_tokens")
    assert hasattr(ev, "mark_pending_successor_verify")
    assert callable(ev.scan_ac_for_verifier_tokens)
    assert callable(ev.mark_pending_successor_verify)
