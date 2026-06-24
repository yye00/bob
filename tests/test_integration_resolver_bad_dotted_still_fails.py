"""Guard: a single bad dotted target must still hard-fail.

'integration: bob3.does_not_exist_module' is a non-prose form — there are no
connector tokens, no spaces beyond the module path.  The resolver must return
(False, ...) to prevent silently demoting real wiring bugs.
"""
from __future__ import annotations

import pathlib

import pytest

from bob3.verification.integration_ac_resolver import resolve_integration_ac

BAD_DOTTED_CRITERION = "integration: bob3.does_not_exist_module"


@pytest.fixture()
def empty_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """Workspace where bob3.does_not_exist_module does not exist."""
    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    return tmp_path


def test_bad_dotted_target_hard_fails(empty_workspace: pathlib.Path) -> None:
    """Single unresolvable dotted target (non-prose) must return (False, ...)."""
    passed, reason = resolve_integration_ac(BAD_DOTTED_CRITERION, empty_workspace)
    assert passed is False, (
        f"resolve_integration_ac must return False for a single bad dotted target "
        f"that is not wired; got passed={passed!r}, reason={reason!r}"
    )
    assert reason, "reason must be non-empty when returning False"


def test_bad_dotted_target_reason_mentions_body(empty_workspace: pathlib.Path) -> None:
    """The failure reason must reference the criterion body for diagnostics."""
    _, reason = resolve_integration_ac(BAD_DOTTED_CRITERION, empty_workspace)
    assert "bob3.does_not_exist_module" in reason or "no wired" in reason, (
        f"reason should reference body or 'no wired', got: {reason!r}"
    )


def test_bad_dotted_does_not_emit_demotion_log(
    empty_workspace: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A hard-failing non-prose form must NOT emit INTEGRATION_AC_PROSE_DEMOTED."""
    import logging

    with caplog.at_level(logging.INFO, logger="bob3.verification.integration_demotion"):
        resolve_integration_ac(BAD_DOTTED_CRITERION, empty_workspace)

    demoted_records = [
        r for r in caplog.records
        if r.name == "bob3.verification.integration_demotion"
    ]
    assert not demoted_records, (
        f"No demotion log expected for non-prose bad-dotted criterion, "
        f"got {len(demoted_records)} record(s)"
    )
