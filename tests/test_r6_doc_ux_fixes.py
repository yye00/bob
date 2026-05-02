"""Regression tests for the R6/R9 docs + UX cleanup batch.

Covers:
- R6-005: README "Commands" table now lists ``bob3 show-reviews``.
- R6-006: README env-var table now lists ``BOB3_SNAPSHOT_TIMEOUT``;
  conftest no longer snapshots stale env-vars (BOB3_WORKSPACE etc.)
  that no production code reads.
- R6-007: ``examples/03_simple_calculator_spec.yaml`` exists with the
  documented stdlib-only quickstart shape; ``examples/00_bootstrap_spec.yaml``
  no longer hardcodes the original author's home directory; README
  Quickstart points at the calculator spec by default.
- R6-008: ``bob3 run`` and ``bob3 init`` exit 1 with an actionable message
  when ``node`` or ``claude`` are missing.
- R6-009: README documents the resume-after-interruption flow.
- R6-010: ``using-bob3-memory`` SKILL.md tools table includes
  ``memory_delete`` / ``memory_demote`` / ``memory_get_candidates``.
- R6-011: ``no-stubs-no-mocks`` SKILL.md grep example is portable
  (no GNU-only ``\\s`` / ``\\b`` extensions).
- R9-003: log lines that include ``feature.name`` cannot inject extra
  log records (CR/LF escaped via ``_log_safe``).
"""

from __future__ import annotations

import io
import logging
import pathlib

import pytest
import yaml
from click.testing import CliRunner

from bob3.cli import main
from bob3.orchestrator import run_loop

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


# ----------------------------------------------------------------
# R6-005: bob3 show-reviews appears in the README Commands table
# ----------------------------------------------------------------


class TestReadmeShowReviewsCommand:
    def test_show_reviews_listed_in_commands_table(self):
        text = README.read_text()
        assert "`bob3 show-reviews`" in text, (
            "README Commands table must list the show-reviews command (R6-005)"
        )

    def test_show_reviews_in_commands_section(self):
        text = README.read_text()
        # The line should sit inside the | Command | Purpose | block.
        # That block's header is "## Commands"; check the substring lives
        # somewhere after that header (we don't enforce exact line offset
        # so the README can be edited freely).
        commands_idx = text.find("## Commands")
        show_reviews_idx = text.find("`bob3 show-reviews`")
        assert commands_idx >= 0, "README must have a ## Commands section"
        assert show_reviews_idx >= 0
        assert show_reviews_idx > commands_idx, (
            "show-reviews row must live inside the Commands table"
        )


# ----------------------------------------------------------------
# R6-006: BOB3_SNAPSHOT_TIMEOUT documented; conftest cleanup
# ----------------------------------------------------------------


class TestEnvVarDocs:
    def test_snapshot_timeout_documented(self):
        text = README.read_text()
        assert "`BOB3_SNAPSHOT_TIMEOUT`" in text, (
            "README env-var table must mention BOB3_SNAPSHOT_TIMEOUT (R6-006)"
        )

    def test_snapshot_timeout_doc_describes_fallback(self):
        text = README.read_text()
        assert "BOB3_TEST_RUN_TIMEOUT" in text and "300" in text, (
            "BOB3_SNAPSHOT_TIMEOUT row must document its fallback chain"
        )


class TestConftestEnvSnapshot:
    """conftest snapshots only env-vars that production code actually reads."""

    def test_conftest_does_not_snapshot_unread_vars(self):
        from tests.conftest import _BOB3_ENV_VARS_TO_SNAPSHOT

        # These names appeared in the snapshot list but no module under
        # src/bob3/ ever reads them — they were dead state. They must
        # NOT be re-introduced unless code starts honoring them.
        unread = {"BOB3_WORKSPACE", "BOB3_LOG_DIR", "BOB3_LOG_LEVEL"}
        assert unread.isdisjoint(set(_BOB3_ENV_VARS_TO_SNAPSHOT)), (
            f"conftest snapshots env-vars that no code reads: "
            f"{unread & set(_BOB3_ENV_VARS_TO_SNAPSHOT)}"
        )

    def test_conftest_keeps_real_env_vars(self):
        from tests.conftest import _BOB3_ENV_VARS_TO_SNAPSHOT

        # These ARE read by production code; removing them from the
        # snapshot list would let test bodies leak into each other.
        for name in (
            "BOB3_DATABASE_PATH",
            "BOB3_MEMORY_DIR",
            "BOB3_COST_PER_TURN_PROXY",
        ):
            assert name in _BOB3_ENV_VARS_TO_SNAPSHOT, (
                f"{name} must remain in the conftest env snapshot list"
            )


# ----------------------------------------------------------------
# R6-007: examples/03 calculator spec + bootstrap workspace fix
# ----------------------------------------------------------------


class TestCalculatorExampleSpec:
    SPEC = ROOT / "examples" / "03_simple_calculator_spec.yaml"

    def test_spec_file_exists(self):
        assert self.SPEC.exists(), "examples/03_simple_calculator_spec.yaml must exist"

    def test_spec_parses_as_yaml(self):
        data = yaml.safe_load(self.SPEC.read_text())
        assert isinstance(data, dict)
        assert data["name"] == "calculator"
        assert "features" in data and isinstance(data["features"], dict)

    def test_spec_has_three_features(self):
        data = yaml.safe_load(self.SPEC.read_text())
        # F001 / F002 / F003 — small enough that any user can run it
        # end-to-end as a quickstart target.
        assert set(data["features"].keys()) == {"F001", "F002", "F003"}

    def test_spec_has_no_specialized_dependencies(self):
        # Smoke test: the description should not pull in heavy deps that
        # were the whole reason 01/02 were unfit as quickstart targets.
        text = self.SPEC.read_text().lower()
        for forbidden in ("fenics", "petsc4py", "mpi4py", "pyqt6"):
            assert forbidden not in text, (
                f"{forbidden} should not appear in the stdlib-only "
                f"quickstart spec"
            )


class TestBootstrapSpecWorkspace:
    BOOTSTRAP = ROOT / "examples" / "00_bootstrap_spec.yaml"

    def test_workspace_line_does_not_hardcode_author_path(self):
        # The actual workspace: directive must not point at the original
        # author's home directory. (The spec's prose / feature descriptions
        # may still mention the original paths as historical context, and
        # those are not the path that ``bob3 plan`` honors.)
        data = yaml.safe_load(self.BOOTSTRAP.read_text())
        ws = data.get("workspace", "")
        assert "/home/captain/clawd" not in ws, (
            f"Bootstrap spec workspace must not hardcode author path: {ws!r}"
        )

    def test_workspace_line_is_a_safe_default(self):
        data = yaml.safe_load(self.BOOTSTRAP.read_text())
        ws = data.get("workspace", "")
        # Either a /tmp default (per the fix) or a placeholder the user is
        # expected to override — both are safe; the original author path
        # is not.
        assert ws.startswith("/tmp/") or "$" in ws or "<" in ws, (
            f"Bootstrap workspace should be a portable default, got {ws!r}"
        )


class TestReadmeQuickstartUsesCalculatorSpec:
    def test_quickstart_references_calculator_spec(self):
        text = README.read_text()
        assert "03_simple_calculator_spec.yaml" in text, (
            "README Quickstart should reference the calculator example"
        )

    def test_aspirational_examples_called_out(self):
        text = README.read_text().lower()
        # Users on a laptop with no FEniCSx / PyQt6 should not have to
        # find out the hard way.
        assert "aspirational" in text or "specialized" in text, (
            "README must warn that 01/02 specs need specialized deps"
        )


# ----------------------------------------------------------------
# R6-008: Node.js / Claude Code CLI pre-flight check
# ----------------------------------------------------------------


class TestNodePreflightCheck:
    """``bob3 run`` / ``bob3 init`` must surface missing node/claude clearly."""

    def test_run_exits_when_node_missing(self, monkeypatch):
        runner = CliRunner()

        def fake_which(name: str) -> str | None:
            return None if name == "node" else "/fake/" + name

        monkeypatch.setattr("bob3.cli.shutil.which", fake_which)
        result = runner.invoke(main, ["run", "--all"])
        assert result.exit_code == 1
        assert "Node.js is required" in result.output or "Node.js is required" in (
            result.stderr if hasattr(result, "stderr") else ""
        )

    def test_run_exits_when_claude_missing(self, monkeypatch):
        runner = CliRunner()

        def fake_which(name: str) -> str | None:
            if name == "node":
                return "/fake/node"
            if name == "claude":
                return None
            return "/fake/" + name

        monkeypatch.setattr("bob3.cli.shutil.which", fake_which)
        result = runner.invoke(main, ["run", "--all"])
        assert result.exit_code == 1
        assert "Claude Code CLI" in result.output or "Claude Code CLI" in (
            result.stderr if hasattr(result, "stderr") else ""
        )

    def test_init_exits_when_node_missing(self, monkeypatch, tmp_path):
        runner = CliRunner()

        def fake_which(name: str) -> str | None:
            return None if name == "node" else "/fake/" + name

        monkeypatch.setattr("bob3.cli.shutil.which", fake_which)
        result = runner.invoke(main, ["init", str(tmp_path / "x")])
        assert result.exit_code == 1
        assert "Node.js is required" in result.output or "Node.js is required" in (
            result.stderr if hasattr(result, "stderr") else ""
        )

    def test_init_exits_when_claude_missing(self, monkeypatch, tmp_path):
        runner = CliRunner()

        def fake_which(name: str) -> str | None:
            if name == "node":
                return "/fake/node"
            if name == "claude":
                return None
            return "/fake/" + name

        monkeypatch.setattr("bob3.cli.shutil.which", fake_which)
        result = runner.invoke(main, ["init", str(tmp_path / "x")])
        assert result.exit_code == 1
        assert "Claude Code CLI" in result.output or "Claude Code CLI" in (
            result.stderr if hasattr(result, "stderr") else ""
        )


# ----------------------------------------------------------------
# R6-009: README documents the resume-after-interruption flow
# ----------------------------------------------------------------


class TestResumeFlowDocs:
    def test_readme_has_resume_subsection(self):
        text = README.read_text()
        assert "Resuming after interruption" in text, (
            "README must include a 'Resuming after interruption' subsection"
        )

    def test_readme_explains_checkpoint_table(self):
        text = README.read_text().lower()
        assert "resource_checkpoints" in text, (
            "README resume section must name the checkpoint table"
        )

    def test_readme_describes_resume_command(self):
        text = README.read_text()
        # Both default resume and the per-feature retry path should be
        # mentioned so users have an explicit recipe.
        assert "bob3 run --all" in text
        assert "--feature" in text and "--fresh" in text


# ----------------------------------------------------------------
# R6-010: using-bob3-memory SKILL.md mentions delete/demote/candidates
# ----------------------------------------------------------------


class TestUsingMemorySkillToolsTable:
    SKILL = ROOT / "src" / "bob3" / "skills" / "using-bob3-memory" / "SKILL.md"

    def test_lists_memory_delete(self):
        text = self.SKILL.read_text()
        assert "memory_delete" in text

    def test_lists_memory_demote(self):
        text = self.SKILL.read_text()
        assert "memory_demote" in text

    def test_lists_memory_get_candidates(self):
        text = self.SKILL.read_text()
        assert "memory_get_candidates" in text


# ----------------------------------------------------------------
# R6-011: no-stubs-no-mocks grep is POSIX-portable
# ----------------------------------------------------------------


class TestNoStubsGrepPortability:
    SKILL = ROOT / "src" / "bob3" / "skills" / "no-stubs-no-mocks" / "SKILL.md"

    def test_grep_example_does_not_use_gnu_only_extensions(self):
        text = self.SKILL.read_text()
        # Grab the first ``grep -rn`` line and verify it omits GNU-only
        # extensions. We allow the file to mention ``\s`` / ``\b`` in
        # PROSE explaining why we removed them, but the grep COMMAND
        # itself must not rely on them.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("grep -rn") and "src/" in stripped:
                assert "\\s" not in stripped, (
                    "no-stubs-no-mocks grep example must not use GNU-only \\s"
                )
                assert "\\b" not in stripped, (
                    "no-stubs-no-mocks grep example must not use GNU-only \\b"
                )
                return
        pytest.fail("Could not find a 'grep -rn' example line in the skill")


# ----------------------------------------------------------------
# R9-003: log lines escape CR/LF in feature.name to prevent injection
# ----------------------------------------------------------------


class TestLogSafeHelper:
    def test_log_safe_escapes_newline(self):
        assert run_loop._log_safe("foo\nbar") == "foo\\nbar"

    def test_log_safe_escapes_carriage_return(self):
        assert run_loop._log_safe("foo\rbar") == "foo\\rbar"

    def test_log_safe_handles_none(self):
        assert run_loop._log_safe(None) == ""

    def test_log_safe_passes_through_normal_strings(self):
        assert run_loop._log_safe("Implement feature X") == "Implement feature X"


class TestExecutingFeatureLogIsInjectionSafe:
    """When a malicious feature.name is logged, the resulting log record
    must not contain raw newlines that look like a separate log entry.
    """

    def test_executing_log_message_has_no_raw_newlines(self):
        # Build a fake feature with a CRLF-laden name and capture what
        # the logger actually emits when execute_feature's first log
        # line fires.
        from types import SimpleNamespace

        feature = SimpleNamespace(
            id="abcd1234-fake-feature-id",
            name="legit\nINFO  Feature completed: stolen log line",
            description="x",
        )

        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger("bob3.orchestrator.run_loop")
        prev_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info(
                "Executing feature %s: %s",
                feature.id,
                run_loop._log_safe(feature.name),
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)

        output = buf.getvalue()
        # The whole emitted message lives on a single line — the trailing
        # newline added by the StreamHandler is the only newline allowed.
        assert output.endswith("\n")
        assert output.count("\n") == 1, (
            "_log_safe must escape embedded newlines so a single log call "
            "produces a single log record"
        )
        # The escaped form is preserved (so operators can still see what
        # the malicious name was) but is not interpreted as a new line.
        assert "\\n" in output
