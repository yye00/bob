"""AC artifact-existence verifier — handles unknown prefix gracefully."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bob.verification.ac_artifact_check import (
    handle_unknown_prefix,
    verify_ac_artifacts,
    ArtifactMiss,
    recognized_ac_prefixes,
)


def test_handle_unknown_prefix_returns_artifact_miss():
    """handle_unknown_prefix("some random ac text") returns ArtifactMiss with kind='unknown_prefix'."""
    miss = handle_unknown_prefix("some random ac text")
    assert isinstance(miss, ArtifactMiss)
    assert miss.kind == "unknown_prefix"
    assert miss.ac_text == "some random ac text"


def test_handle_unknown_prefix_preserves_ac_text():
    """handle_unknown_prefix stores the original AC text in ac_text field."""
    ac = "some_weird_prefix: /path/to/something"
    miss = handle_unknown_prefix(ac)
    assert miss.ac_text == ac


def test_handle_unknown_prefix_empty_expected_path():
    """handle_unknown_prefix sets expected_path to empty string."""
    miss = handle_unknown_prefix("some random ac text")
    assert miss.expected_path == ""


def test_verify_ac_artifacts_includes_unknown_prefix_as_miss(tmp_path):
    """verify_ac_artifacts returns ArtifactMiss with kind=unknown_prefix for unknown prefixes."""
    acs = ["some random ac text"]
    misses = verify_ac_artifacts(acs, workspace=tmp_path)
    assert len(misses) == 1
    assert misses[0].kind == "unknown_prefix"
    assert misses[0].ac_text == "some random ac text"


def test_verify_ac_artifacts_flags_integration_prefix_as_unknown(tmp_path):
    """verify_ac_artifacts returns ArtifactMiss with kind=unknown_prefix for integration: prefix."""
    acs = ["integration: bob.verification.verifier"]
    misses = verify_ac_artifacts(acs, workspace=tmp_path)
    assert len(misses) == 1
    assert misses[0].kind == "unknown_prefix"


def test_verify_ac_artifacts_multiple_unknown_prefixes(tmp_path):
    """verify_ac_artifacts includes all unknown-prefix ACs as misses."""
    acs = [
        "some random ac text",
        "another unknown: prefix here",
    ]
    misses = verify_ac_artifacts(acs, workspace=tmp_path)
    assert len(misses) == 2
    assert all(m.kind == "unknown_prefix" for m in misses)


def test_recognized_ac_prefixes_returns_tuple():
    """recognized_ac_prefixes() returns a tuple (not a list)."""
    prefixes = recognized_ac_prefixes()
    assert isinstance(prefixes, tuple), f"Expected tuple, got {type(prefixes)}"


def test_recognized_ac_prefixes_contains_all_five_expected_values():
    """recognized_ac_prefixes() includes all 5 required prefix strings."""
    prefixes = recognized_ac_prefixes()
    assert "pytest:" in prefixes
    assert "File exists:" in prefixes
    assert "File modified:" in prefixes
    assert "File modified or created:" in prefixes
    assert "Function defined:" in prefixes


def test_recognized_ac_prefixes_has_exactly_five_entries():
    """recognized_ac_prefixes() returns exactly 5 entries."""
    prefixes = recognized_ac_prefixes()
    assert len(prefixes) == 5


def test_integration_prefix_is_unknown(tmp_path):
    """The 'integration:' prefix is not recognized, so it maps to unknown_prefix."""
    acs = ["integration: bob.some.module"]
    misses = verify_ac_artifacts(acs, workspace=tmp_path)
    assert misses
    assert all(m.kind == "unknown_prefix" for m in misses), (
        f"All misses for integration: prefix should be unknown_prefix, got: {[m.kind for m in misses]}"
    )
