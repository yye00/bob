"""Regression test for c09e9e64: Pattern 8 prose-integration AC demotion.

The exact criterion that repeatedly blocked feature c09e9e64 across 3 attempts:
  "integration: all spec_findings.yaml writes in bob.reviews route through
   atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"

Legacy Pattern 8 (first-token extraction) captured "all" — which is not a
module — and hard-failed.  The resolver MUST demote this to warning, and MUST
emit an INTEGRATION_AC_PROSE_DEMOTED log entry.
"""
from __future__ import annotations

import json
import logging
import pathlib

import pytest

from bob.verification.integration_ac_resolver import resolve_integration_ac

REGRESSION_CRITERION = (
    "integration: all spec_findings.yaml writes in bob.reviews route through "
    "atomic_write_yaml; no direct open(path, 'w') + yaml.dump remains"
)


@pytest.fixture()
def empty_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace with no relevant module wired (so no dotted target resolves)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "placeholder.py").write_text("# placeholder\n")
    return tmp_path


def test_c09e9e64_criterion_demotes_to_warning(empty_workspace: pathlib.Path) -> None:
    """The c09e9e64 regression criterion must return (True, '...demoted...') — not False."""
    passed, reason = resolve_integration_ac(REGRESSION_CRITERION, empty_workspace)
    assert passed is True, (
        f"resolve_integration_ac must not hard-fail the c09e9e64 prose criterion; "
        f"got passed={passed!r}, reason={reason!r}"
    )
    assert "demoted" in reason.lower(), (
        f"reason must contain 'demoted' to indicate a prose-demotion, got: {reason!r}"
    )


def test_c09e9e64_criterion_emits_prose_demoted_log(
    empty_workspace: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Demotion must emit an INTEGRATION_AC_PROSE_DEMOTED structured log entry."""
    with caplog.at_level(logging.INFO, logger="bob.verification.integration_demotion"):
        resolve_integration_ac(REGRESSION_CRITERION, empty_workspace)

    demoted_records = [
        r for r in caplog.records
        if r.name == "bob.verification.integration_demotion"
    ]
    assert demoted_records, (
        "Expected at least one log record from 'bob.verification.integration_demotion'"
    )
    payload = json.loads(demoted_records[0].getMessage())
    assert payload["event"] == "INTEGRATION_AC_PROSE_DEMOTED", (
        f"Expected event='INTEGRATION_AC_PROSE_DEMOTED', got {payload['event']!r}"
    )
    assert payload["criterion"] == REGRESSION_CRITERION
    assert isinstance(payload["scanned_candidates"], list)


def test_c09e9e64_extract_finds_bob_reviews() -> None:
    """extract_integration_targets must return 'bob.reviews' for the regression criterion."""
    from bob.verification.integration_ac_resolver import extract_integration_targets

    targets = extract_integration_targets(REGRESSION_CRITERION)
    assert "bob.reviews" in targets, (
        f"Expected 'bob.reviews' in extracted targets, got {targets!r}"
    )
