"""Tests that the verification prompt warns subagents not to run the full test suite.

Feature: 9901139e-bde3-4f3d-b648-f83d2494f98d
AC: pytest: tests/test_verification_prompt_warns_against_full_suite.py
"""

from __future__ import annotations

from bob.superpowers import VERIFICATION_PROMPT_SECTION, get_verification_prompt


class TestVerificationPromptWarnsAgainstFullSuite:
    def test_base_section_warns_do_not_run_full_suite(self):
        assert "Do NOT run the full test suite" in VERIFICATION_PROMPT_SECTION

    def test_base_section_mentions_30_min_cost(self):
        assert "30 min" in VERIFICATION_PROMPT_SECTION or "30 minutes" in VERIFICATION_PROMPT_SECTION

    def test_base_section_mentions_orchestrator_runs_full_suite(self):
        assert "orchestrator" in VERIFICATION_PROMPT_SECTION.lower()

    def test_base_prompt_warns_max_turns_cancel(self):
        assert "cancelled" in VERIFICATION_PROMPT_SECTION or "max_turns" in VERIFICATION_PROMPT_SECTION

    def test_scoped_prompt_repeats_do_not_run_warning(self):
        acs = ["pytest: tests/test_x.py"]
        prompt = get_verification_prompt(acs)
        assert "Do NOT run" in prompt

    def test_scoped_prompt_explicit_do_not_run_full_suite_command(self):
        acs = ["pytest: tests/test_x.py"]
        prompt = get_verification_prompt(acs)
        assert "python -m pytest tests/ -v" in prompt or "Do NOT run" in prompt

    def test_base_section_does_not_instruct_full_suite_in_checklist_item_4(self):
        lines = VERIFICATION_PROMPT_SECTION.splitlines()
        item4_lines = [l for l in lines if l.strip().startswith("4.") and "Tests pass" in l]
        for line in item4_lines:
            assert "tests/ -v" not in line, (
                "Checklist item 4 still says 'python -m pytest tests/ -v' — "
                "it should instruct subagents to use the scoped command"
            )
