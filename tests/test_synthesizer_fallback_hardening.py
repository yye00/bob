"""F-R6-305: Tests for the hardened spec-synthesizer LLM-fallback path.

The original two-line fallback (file_exists + pytest) emitted by F-R1-011
dropped ``conf_test_adequacy`` below the 0.40 floor and blocked spawning
in Rounds 4-5.  This module pins the post-hardening invariants:

  * The fallback always emits at least 3 acceptance criteria.
  * A ``Function defined: <module>.<symbol>`` criterion is included whenever
    a primary symbol can be inferred from the feature name.
  * An ``integration: <module>`` criterion is included whenever the
    description signals wiring intent ("integrate", "wire into", etc.).
  * The fallback never emits a spec containing only ``file_exists`` +
    ``pytest:`` — that combination is what triggered the original bug.
  * The LLM-parse-failure path actually flows into the new fallback when
    the LLM returns malformed output (verified by mocking the sub-agent
    spawn at the synthesizer boundary).
  * The successful LLM path remains untouched: parsed criteria are
    returned verbatim and the fallback is *not* invoked.
"""
from __future__ import annotations

import asyncio
import keyword
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from bob3 import spec_synthesizer
from bob3.spec_synthesizer import (
    deterministic_fallback,
    deterministic_fallback_spec,
    sanitize_spec_file,
    synthesize_for_feature,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _by_prefix(criteria: list[str], prefix: str) -> list[str]:
    return [c for c in criteria if c.lower().startswith(prefix.lower())]


# ---------------------------------------------------------------------------
# Hardened-fallback core invariants
# ---------------------------------------------------------------------------


class TestFallbackInvariants:
    """The bug: the old fallback emitted only file_exists + pytest, which
    dropped readiness below the spawn gate.  These invariants prevent
    regressing to that state."""

    def test_always_at_least_three_criteria_plain_feature(self):
        criteria = deterministic_fallback(
            "policy gradient trainer",
            "A simple training loop for a small policy network.",
        )
        assert len(criteria) >= 3, criteria

    def test_always_at_least_three_criteria_integration_feature(self):
        criteria = deterministic_fallback(
            "metrics collector",
            "Integrate metrics collector into the orchestrator pipeline.",
        )
        assert len(criteria) >= 3, criteria

    def test_never_only_file_exists_and_pytest(self):
        """The exact regression we are guarding against."""
        criteria = deterministic_fallback("widget", "A small widget.")
        file_and_test_only = {c.split(":", 1)[0].lower() for c in criteria} <= {
            "file exists",
            "pytest",
        }
        assert not file_and_test_only, (
            f"fallback collapsed to file_exists+pytest only: {criteria}"
        )

    def test_never_only_file_exists_and_pytest_for_many_titles(self):
        """Same invariant against a battery of titles — the bug was easy to
        regress when symbol inference returned ``None``."""
        for title in [
            "x",
            "the",
            "a-feature",
            "for the system",
            "module",
            "simple cache",
            "F-R6-999",
        ]:
            criteria = deterministic_fallback(title, "Does a thing.")
            prefixes = {c.split(":", 1)[0].lower() for c in criteria}
            assert prefixes - {"file exists", "pytest"}, (
                f"title {title!r} produced only file/pytest: {criteria}"
            )
            assert len(criteria) >= 3, (title, criteria)


# ---------------------------------------------------------------------------
# Function-defined criterion (symbol inference)
# ---------------------------------------------------------------------------


class TestFunctionDefinedCriterion:
    def test_kebab_case_title_yields_snake_case_symbol(self):
        criteria = deterministic_fallback(
            "policy-gradient-trainer",
            "A simple training loop.",
        )
        fn = _by_prefix(criteria, "Function defined:")
        assert fn, criteria
        assert "policy_gradient_trainer" in fn[0]

    def test_strips_leading_stopwords(self):
        criteria = deterministic_fallback(
            "the budget tracker",
            "A simple budget tracker.",
        )
        fn = _by_prefix(criteria, "Function defined:")
        assert fn, criteria
        # "the" must be stripped from the symbol.
        symbol_part = fn[0].split(":", 1)[1].strip()
        assert not symbol_part.endswith(".the")
        assert "the_budget" not in symbol_part
        assert "budget" in symbol_part

    def test_strips_trailing_noun(self):
        criteria = deterministic_fallback(
            "payment service",
            "A new payment module.",
        )
        fn = _by_prefix(criteria, "Function defined:")
        assert fn, criteria
        symbol_part = fn[0].split(":", 1)[1].strip()
        # "service" trailing noun is stripped, leaving "payment".
        assert symbol_part.endswith(".payment"), symbol_part

    def test_function_defined_format_module_dot_symbol(self):
        criteria = deterministic_fallback("foo bar", "Does foo bar.")
        fn = _by_prefix(criteria, "Function defined:")
        assert fn, criteria
        body = fn[0].split(":", 1)[1].strip()
        # Must contain at least one '.' separating module and symbol.
        assert "." in body, body
        module, _, symbol = body.rpartition(".")
        assert module and symbol


# ---------------------------------------------------------------------------
# Integration criterion (wiring intent)
# ---------------------------------------------------------------------------


class TestIntegrationCriterion:
    def test_integrate_into_named_module_extracts_target(self):
        criteria = deterministic_fallback(
            "audit hook",
            "Integrate the audit hook into bob3.orchestrator.run_loop.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria
        assert "run_loop" in integ[0] or "orchestrator" in integ[0]

    def test_wire_into_keyword_emits_integration(self):
        criteria = deterministic_fallback(
            "trace span emitter",
            "Wire the span emitter into the pipeline.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria

    def test_hook_into_keyword_emits_integration(self):
        criteria = deterministic_fallback(
            "request audit",
            "Hook into the request lifecycle.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria

    def test_register_with_keyword_emits_integration(self):
        criteria = deterministic_fallback(
            "plugin xyz",
            "Register with the plugin registry.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria

    def test_default_target_for_orchestration_intent(self):
        """When wiring is implied but no module is named, an
        orchestration-flavoured description picks the run-loop default."""
        criteria = deterministic_fallback(
            "scheduler hook",
            "Hook into the scheduler so jobs fire on each loop tick.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria
        # Either the parsed scheduler target or the run_loop default.
        assert "run_loop" in integ[0] or "scheduler" in integ[0]

    def test_default_target_for_cli_intent(self):
        criteria = deterministic_fallback(
            "diagnose subcommand",
            "Wire the diagnose command into the CLI entrypoint.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria
        body = integ[0].split(":", 1)[1].strip()
        # When no concrete module is named, default routes to bob3.cli for CLI
        # intent; when "CLI entrypoint" is parsed as a target, that's also OK.
        assert "cli" in body.lower() or "entrypoint" in body.lower()

    def test_no_integration_criterion_without_wiring_keyword(self):
        criteria = deterministic_fallback(
            "result cache",
            "A simple in-memory cache for query results.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert not integ, criteria


# ---------------------------------------------------------------------------
# Non-integration features still get >=3 criteria via function_defined
# ---------------------------------------------------------------------------


class TestNonIntegrationFeature:
    def test_function_defined_criterion_present_for_plain_feature(self):
        criteria = deterministic_fallback(
            "result cache",
            "A simple in-memory cache.",
        )
        fn = _by_prefix(criteria, "Function defined:")
        assert fn, criteria

    def test_plain_feature_no_integration_criterion(self):
        criteria = deterministic_fallback(
            "result cache",
            "A simple in-memory cache.",
        )
        assert not _by_prefix(criteria, "integration:")


# ---------------------------------------------------------------------------
# Dict-returning wrapper
# ---------------------------------------------------------------------------


class TestDeterministicFallbackSpec:
    def test_returns_dict_with_acceptance_criteria(self):
        spec = deterministic_fallback_spec(
            "result cache",
            "A simple in-memory cache.",
        )
        assert isinstance(spec, dict)
        assert "acceptance_criteria" in spec
        assert isinstance(spec["acceptance_criteria"], list)
        assert len(spec["acceptance_criteria"]) >= 3

    def test_dict_wrapper_matches_list_helper(self):
        list_form = deterministic_fallback("foo bar", "Does foo bar.")
        dict_form = deterministic_fallback_spec("foo bar", "Does foo bar.")
        assert dict_form["acceptance_criteria"] == list_form

    def test_dict_wrapper_carries_feature_name(self):
        spec = deterministic_fallback_spec("my widget", "")
        assert spec.get("feature_name") == "my widget"


# ---------------------------------------------------------------------------
# Kwargs acceptance (forward compat)
# ---------------------------------------------------------------------------


class TestSignatureAcceptsKwargs:
    def test_extra_kwargs_are_ignored(self):
        # New callers may pass project_context, workspace, etc.
        criteria = deterministic_fallback(
            "metrics emitter",
            "Wire the metrics emitter into the pipeline.",
            project_context="ignored",
            workspace="/tmp",
        )
        assert len(criteria) >= 3


# ---------------------------------------------------------------------------
# End-to-end: LLM-parse-failure path actually exercises the fallback
# ---------------------------------------------------------------------------


@dataclass
class _FakeExecResult:
    text: str


@dataclass
class _FakeAgentResult:
    execution_result: _FakeExecResult


class TestLLMParseFailureFlowsToFallback:
    """Mock the sub-agent boundary and verify the malformed-LLM path
    actually flows into the hardened fallback inside sanitize_spec_file."""

    @pytest.mark.asyncio
    async def test_malformed_llm_response_triggers_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Build a one-feature spec with a placeholder AC list.
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(
            yaml.safe_dump(
                {
                    "project_id": "test",
                    "features": {
                        "F-TEST-1": {
                            "title": "metrics emitter",
                            "description": (
                                "Wire the metrics emitter into the pipeline "
                                "so each loop tick produces a sample."
                            ),
                            "acceptance_criteria": "TBD: synthesize via F-R1-011",
                        }
                    },
                }
            )
        )

        # Mock the sub-agent to return un-parseable text.
        async def fake_spawn(*args: Any, **kwargs: Any) -> _FakeAgentResult:
            return _FakeAgentResult(_FakeExecResult("this is not json at all"))

        def fake_options(**kwargs: Any) -> dict[str, Any]:
            return {}

        import bob3.orchestrator.claude_executor as ce

        monkeypatch.setattr(ce, "spawn_sub_agent", fake_spawn)
        monkeypatch.setattr(ce, "build_sub_agent_options", fake_options)

        report = await sanitize_spec_file(
            spec_path,
            project_id="test",
            project_context="test",
            workspace=tmp_path,
            dry_run=False,
            use_fallback=True,
            concurrency=1,
        )

        # Fallback was used (LLM output unparseable).
        assert report["fell_back"] == 1, report
        assert report["synthesized"] == 0, report

        # The on-disk spec now carries the hardened fallback criteria.
        rewritten = yaml.safe_load(spec_path.read_text())
        ac = rewritten["features"]["F-TEST-1"]["acceptance_criteria"]
        assert isinstance(ac, list)
        assert len(ac) >= 3, ac
        prefixes = {c.split(":", 1)[0].lower() for c in ac}
        # Must NOT collapse to file_exists+pytest only.
        assert prefixes - {"file exists", "pytest"}, ac
        # Must include the integration criterion (wiring keyword present).
        assert any(c.lower().startswith("integration:") for c in ac), ac

    @pytest.mark.asyncio
    async def test_well_formed_llm_response_skips_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Back-compat: the successful LLM path is unchanged."""
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(
            yaml.safe_dump(
                {
                    "project_id": "test",
                    "features": {
                        "F-TEST-2": {
                            "title": "result cache",
                            "description": "A simple cache.",
                            "acceptance_criteria": "TBD: synthesize via F-R1-011",
                        }
                    },
                }
            )
        )

        well_formed = (
            '```json\n'
            '["File exists: src/bob3/result_cache.py", '
            '"Function defined: bob3.result_cache.ResultCache", '
            '"pytest: tests/test_result_cache.py"]\n'
            '```'
        )

        async def fake_spawn(*args: Any, **kwargs: Any) -> _FakeAgentResult:
            return _FakeAgentResult(_FakeExecResult(well_formed))

        def fake_options(**kwargs: Any) -> dict[str, Any]:
            return {}

        import bob3.orchestrator.claude_executor as ce

        monkeypatch.setattr(ce, "spawn_sub_agent", fake_spawn)
        monkeypatch.setattr(ce, "build_sub_agent_options", fake_options)

        report = await sanitize_spec_file(
            spec_path,
            project_id="test",
            project_context="test",
            workspace=tmp_path,
            dry_run=False,
            use_fallback=True,
            concurrency=1,
        )

        # No fallback — the LLM path succeeded.
        assert report["synthesized"] == 1, report
        assert report["fell_back"] == 0, report

        rewritten = yaml.safe_load(spec_path.read_text())
        ac = rewritten["features"]["F-TEST-2"]["acceptance_criteria"]
        # The criteria are exactly what the (fake) LLM returned — proving the
        # hardened fallback did not intrude on the successful path.
        assert ac == [
            "File exists: src/bob3/result_cache.py",
            "Function defined: bob3.result_cache.ResultCache",
            "pytest: tests/test_result_cache.py",
        ]


# ---------------------------------------------------------------------------
# Direct call to synthesize_for_feature with malformed output returns None,
# which is what triggers the fallback in sanitize_spec_file.
# ---------------------------------------------------------------------------


class TestSynthesizeForFeatureReturnsNoneOnMalformed:
    @pytest.mark.asyncio
    async def test_returns_none_when_llm_text_unparseable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_spawn(*args: Any, **kwargs: Any) -> _FakeAgentResult:
            return _FakeAgentResult(_FakeExecResult("garbage <not json>"))

        def fake_options(**kwargs: Any) -> dict[str, Any]:
            return {}

        import bob3.orchestrator.claude_executor as ce

        monkeypatch.setattr(ce, "spawn_sub_agent", fake_spawn)
        monkeypatch.setattr(ce, "build_sub_agent_options", fake_options)

        result = await synthesize_for_feature(
            project_id="test",
            title="x",
            description="y",
            project_context="",
            workspace=None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Adversarial-review hardening (post-c42fa7d):
#   1. Reserved keywords / numeric / unicode never produce illegal symbols.
#   2. Empty titles refuse rather than emit reward-hackable weak specs.
#   3. Integration targets are always bob3.* qualified.
#   4. File path and function module path agree (single satisfying file).
# ---------------------------------------------------------------------------


def _extract_function_symbol(criteria: list[str]) -> str | None:
    """Return the final dotted-name token from a ``Function defined:`` AC."""
    fn = _by_prefix(criteria, "Function defined:")
    if not fn:
        return None
    body = fn[0].split(":", 1)[1].strip()
    return body.rpartition(".")[2]


class TestReservedKeywordAndDigitTitles:
    """Adversarial review #1: titles that are Python reserved keywords or
    start with a digit must not produce un-importable ``Function defined:``
    criteria like ``bob3.class.class`` or ``bob3.123.123``."""

    @pytest.mark.parametrize("title", ["class", "import", "from", "def", "return"])
    def test_reserved_keyword_title(self, title: str) -> None:
        # Reserved-keyword titles have no valid identifier projection.
        # Either the call refuses (ValueError) or — if it returns — the
        # Function-defined symbol is a real identifier.
        try:
            criteria = deterministic_fallback(title, "Does a thing.")
        except ValueError:
            return  # acceptable: refuses rather than emit illegal symbol
        symbol = _extract_function_symbol(criteria)
        if symbol is not None:
            assert symbol.isidentifier() and not keyword.iskeyword(symbol), (
                f"title {title!r} produced illegal symbol {symbol!r}: {criteria}"
            )

    @pytest.mark.parametrize("title", ["123", "456 789", "9lives"])
    def test_numeric_only_title(self, title: str) -> None:
        # Identifiers cannot start with a digit; a leading-digit symbol would
        # be un-importable and would let an empty stub satisfy the spec.
        try:
            criteria = deterministic_fallback(title, "Does a thing.")
        except ValueError:
            return  # acceptable: refuses rather than emit illegal symbol
        symbol = _extract_function_symbol(criteria)
        if symbol is not None:
            assert not symbol[:1].isdigit(), (
                f"title {title!r} produced digit-leading symbol {symbol!r}: {criteria}"
            )
            assert symbol.isidentifier(), (
                f"title {title!r} produced non-identifier {symbol!r}: {criteria}"
            )


class TestUnicodeTitle:
    """Adversarial review #1 (subcase): unicode characters must be NFKD-folded
    before being stripped, so ``café`` → ``cafe`` not ``caf``."""

    def test_unicode_title_is_folded_not_destroyed(self) -> None:
        criteria = deterministic_fallback("café résumé naïve", "A small thing.")
        symbol = _extract_function_symbol(criteria)
        # The folded form keeps the base letters, not just the consonants.
        # Accept either the full triple or any single stop-word-stripped variant
        # that contains a real word from the folded title.
        assert symbol is not None, criteria
        joined = " ".join(criteria).lower()
        assert "cafe" in joined or "resume" in joined or "naive" in joined, (
            f"unicode title was destroyed rather than folded: {criteria}"
        )
        # No mojibake / raw non-ascii bytes leaked into the slug.
        assert symbol.isascii(), f"non-ascii symbol leaked: {symbol!r}"


class TestEmptyTitleRefusesWeakSpec:
    """Adversarial review #4: empty titles must not emit
    ``[file_exists, pytest, CLI command: feature]`` — that triple is
    trivially satisfied by two empty stub files plus any ``feature``
    substring in ``bob3 --help``."""

    def test_empty_title_does_not_emit_weak_cli_only(self) -> None:
        # The hardened policy is to refuse: raise ValueError so the caller
        # knows the synthesizer cannot produce a meaningful spec.
        with pytest.raises(ValueError):
            deterministic_fallback("", "")

    def test_whitespace_only_title_refuses(self) -> None:
        with pytest.raises(ValueError):
            deterministic_fallback("   \t\n  ", "")

    def test_punctuation_only_title_refuses(self) -> None:
        # Collapses to no usable tokens; must refuse rather than emit
        # a generic 'feature'-slug weak spec.
        with pytest.raises(ValueError):
            deterministic_fallback("---", "")


class TestIntegrationTargetModuleQualified:
    """Adversarial review #3: ``integration:`` targets must always be
    qualified under ``bob3.*`` so a bare-noun target can't be trivially
    satisfied by any substring scan."""

    @pytest.mark.parametrize(
        "title,desc",
        [
            ("trace span", "wire foo into bar"),
            ("plugin", "Hook foo into baz."),
            ("widget", "Integrate the widget into qux."),
        ],
    )
    def test_integration_target_module_qualified(self, title: str, desc: str) -> None:
        criteria = deterministic_fallback(title, desc)
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria
        body = integ[0].split(":", 1)[1].strip()
        assert body.startswith("bob3."), (
            f"integration target {body!r} not qualified under bob3.*: {criteria}"
        )


class TestFileAndFunctionPathsAgree:
    """Adversarial review #2: ``File exists: src/bob3/<module>.py`` and
    ``Function defined: bob3.<module>.<symbol>`` must agree on ``<module>``,
    otherwise a satisfying implementation would need to live at two
    different paths and the verifier would always reject."""

    @pytest.mark.parametrize(
        "title",
        [
            "policy-gradient-trainer",
            "the budget tracker",
            "payment service",
            "Event Bus Hook",
            "audit hook",
            "foo bar",
        ],
    )
    def test_file_and_function_paths_agree(self, title: str) -> None:
        criteria = deterministic_fallback(title, "wire the thing into baz")
        file_acs = _by_prefix(criteria, "File exists:")
        fn_acs = _by_prefix(criteria, "Function defined:")
        assert file_acs and fn_acs, criteria
        # Extract <module> from "File exists: src/bob3/<module>.py"
        file_body = file_acs[0].split(":", 1)[1].strip()
        assert file_body.startswith("src/bob3/") and file_body.endswith(".py"), file_body
        file_module = file_body[len("src/bob3/"):-len(".py")]
        # Extract <module> from "Function defined: bob3.<module>.<symbol>"
        fn_body = fn_acs[0].split(":", 1)[1].strip()
        assert fn_body.startswith("bob3."), fn_body
        # The module is everything between "bob3." and the final ".<symbol>".
        without_pkg = fn_body[len("bob3."):]
        fn_module = without_pkg.rpartition(".")[0]
        assert fn_module == file_module, (
            f"file module {file_module!r} disagrees with function module "
            f"{fn_module!r} in spec: {criteria}"
        )


class TestDefaultIntegrationTargetCLIBranchLive:
    """Cleanup #5: the CLI-hint branch in ``_default_integration_target``
    must not be dead — it has to return ``bob3.cli`` when CLI keywords
    appear and the regex parser found no explicit target."""

    def test_cli_intent_with_no_parsed_target_routes_to_bob3_cli(self) -> None:
        # "Hook into the CLI" has no words between hook & into so the
        # structured regex doesn't fire; falls through to
        # _default_integration_target, which must route to bob3.cli
        # (not bob3.orchestrator.run_loop).
        criteria = deterministic_fallback(
            "diag subcommand",
            "Hook into the CLI.",
        )
        integ = _by_prefix(criteria, "integration:")
        assert integ, criteria
        body = integ[0].split(":", 1)[1].strip()
        assert body == "bob3.cli", (
            f"CLI-hint branch did not route to bob3.cli: {body!r} in {criteria}"
        )
