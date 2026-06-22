"""Tests for apply_or_halt — error path must name dep AND workaround verbatim."""
import pytest

from bob3.orchestrator.env_preflight import (
    DepEntry,
    HaltOnMissingDepError,
    ProbeResult,
    SilentSkipForbiddenError,
    Workaround,
    apply_or_halt,
    reject_silent_skip,
)


class TestApplyOrHaltErrorPath:
    def test_raises_halt_error_for_missing_high_risk_dep(self):
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        workaround = Workaround(
            dep_name="xxd",
            description="sudo apt-get install -y xxd",
            low_risk=False,
            commands=["sudo apt-get install -y xxd"],
        )
        with pytest.raises(HaltOnMissingDepError):
            apply_or_halt(pr, workaround)

    def test_halt_message_names_missing_dep(self):
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        workaround = Workaround(
            dep_name="xxd",
            description="sudo apt-get install -y xxd",
            low_risk=False,
            commands=[],
        )
        with pytest.raises(HaltOnMissingDepError) as exc_info:
            apply_or_halt(pr, workaround)
        assert "xxd" in str(exc_info.value), (
            f"Error must name the missing dep; got: {exc_info.value!r}"
        )

    def test_halt_message_contains_workaround_text(self):
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        description = "sudo apt-get install -y xxd"
        workaround = Workaround(
            dep_name="xxd",
            description=description,
            low_risk=False,
            commands=[],
        )
        with pytest.raises(HaltOnMissingDepError) as exc_info:
            apply_or_halt(pr, workaround)
        msg = str(exc_info.value)
        assert description in msg or "workaround" in msg.lower(), (
            f"Error must include workaround; got: {msg!r}"
        )

    def test_no_workaround_raises_halt_error(self):
        dep = DepEntry(kind="cli", name="missing_tool")
        pr = ProbeResult(dep=dep, present=False)
        with pytest.raises(HaltOnMissingDepError):
            apply_or_halt(pr, None)

    def test_no_workaround_names_dep(self):
        dep = DepEntry(kind="cli", name="missing_tool")
        pr = ProbeResult(dep=dep, present=False)
        with pytest.raises(HaltOnMissingDepError) as exc_info:
            apply_or_halt(pr, None)
        assert "missing_tool" in str(exc_info.value)

    def test_present_dep_does_not_raise(self):
        dep = DepEntry(kind="cli", name="python3")
        pr = ProbeResult(dep=dep, present=True, path="/usr/bin/python3")
        workaround = Workaround(
            dep_name="python3",
            description="install python3",
            low_risk=True,
            commands=[],
        )
        apply_or_halt(pr, workaround)  # must not raise

    def test_low_risk_missing_dep_does_not_raise(self):
        dep = DepEntry(kind="python", name="sqlite3")
        pr = ProbeResult(dep=dep, present=False)
        workaround = Workaround(
            dep_name="sqlite3",
            description="stdlib module; rebuild python",
            low_risk=True,
            commands=[],
        )
        apply_or_halt(pr, workaround)  # low_risk=True → auto-apply, no raise


class TestRejectSilentSkip:
    def test_raises_when_dep_not_in_message(self):
        with pytest.raises(SilentSkipForbiddenError):
            reject_silent_skip("Something went wrong.", "xxd")

    def test_no_raise_when_dep_in_message(self):
        reject_silent_skip("Missing dep: xxd; please install it.", "xxd")

    def test_partial_match_sufficient(self):
        reject_silent_skip("The dep xxd is unavailable.", "xxd")

    def test_raises_with_different_dep_name(self):
        with pytest.raises(SilentSkipForbiddenError):
            reject_silent_skip("Please install the required tool.", "jq")

    def test_error_message_reports_dep_name(self):
        with pytest.raises(SilentSkipForbiddenError) as exc_info:
            reject_silent_skip("Something went wrong.", "my_dep")
        assert "my_dep" in str(exc_info.value)
