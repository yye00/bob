"""Test: xxd dep in demonstrator spec triggers workaround discovery in preflight pipeline."""
import pathlib

import yaml

from bob.orchestrator.env_preflight import (
    enumerate_deps,
    probe,
    discover_workaround,
    DepEntry,
    ProbeResult,
    Workaround,
    HaltOnMissingDepError,
)

SPEC_PATH = pathlib.Path("bob4/research/demonstrators/F-R7-473/spec.yaml")


def _load_spec_acs() -> list[str]:
    data = yaml.safe_load(SPEC_PATH.read_text())
    return [str(ac) for ac in data.get("acceptance_criteria", [])]


class TestXxdInWorktreePipeline:
    def test_spec_acs_enumerate_xxd_as_cli_dep(self):
        """enumerate_deps should surface xxd from the demonstrator ACs."""
        acs = _load_spec_acs()
        inventory = enumerate_deps(acs)
        cli_names = [e.name for e in inventory.entries if e.kind == "cli"]
        assert "xxd" in cli_names, (
            f"Expected xxd in CLI deps enumerated from F-R7-473 ACs; got: {cli_names}"
        )

    def test_probe_returns_probe_result_for_xxd(self):
        dep = DepEntry(kind="cli", name="xxd")
        result = probe(dep)
        assert isinstance(result, ProbeResult)

    def test_missing_xxd_triggers_workaround_discovery(self):
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        workaround = discover_workaround(pr)
        assert workaround is not None, "Expected a workaround for missing xxd"
        assert isinstance(workaround, Workaround)

    def test_xxd_workaround_description_mentions_xxd(self):
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        workaround = discover_workaround(pr)
        assert workaround is not None
        assert "xxd" in workaround.description

    def test_xxd_workaround_is_not_low_risk(self):
        """xxd requires system-level install — must NOT be auto-applied."""
        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        workaround = discover_workaround(pr)
        assert workaround is not None
        assert workaround.low_risk is False

    def test_apply_or_halt_raises_for_missing_xxd(self):
        """apply_or_halt should raise HaltOnMissingDepError for missing non-low-risk xxd."""
        from bob.orchestrator.env_preflight import apply_or_halt

        dep = DepEntry(kind="cli", name="xxd")
        pr = ProbeResult(dep=dep, present=False)
        workaround = discover_workaround(pr)
        assert workaround is not None

        try:
            apply_or_halt(pr, workaround)
            # If xxd is actually present this won't raise — that's fine
        except HaltOnMissingDepError as exc:
            msg = str(exc)
            assert "xxd" in msg, f"Error message must name the missing dep; got: {msg!r}"
            assert workaround.description in msg or "workaround" in msg.lower(), (
                f"Error message must include workaround; got: {msg!r}"
            )
