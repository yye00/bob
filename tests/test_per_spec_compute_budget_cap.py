"""Tests for per-spec compute-budget cap (feature 20f5bef7-e813-43bf-8c81-22233b22f2ba).

Acceptance criteria:
- File exists: src/bob/per_spec_compute_budget_cap.py
- pytest: tests/test_per_spec_compute_budget_cap.py
"""

from __future__ import annotations

import pathlib

import pytest
import yaml


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

class TestImports:
    def test_module_imports(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        assert SpecBudgetCap is not None
        assert BudgetAction is not None

    def test_budget_action_values(self):
        from bob.per_spec_compute_budget_cap import BudgetAction
        assert BudgetAction.CONTINUE == "continue"
        assert BudgetAction.WARN == "warn"
        assert BudgetAction.ABORT == "abort"
        assert BudgetAction.HUMAN_ALERT == "human_alert"


# ---------------------------------------------------------------------------
# SpecBudgetCap.from_spec
# ---------------------------------------------------------------------------

class TestFromSpec:
    def test_no_max_cost_gives_disabled_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"name": "myproject"})
        assert cap.is_enabled is False
        assert cap.max_cost_usd is None

    def test_max_cost_parsed(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": 10.0})
        assert cap.is_enabled is True
        assert cap.max_cost_usd == pytest.approx(10.0)

    def test_max_cost_as_int(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": 5})
        assert cap.max_cost_usd == pytest.approx(5.0)

    def test_max_cost_as_string_number(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": "7.5"})
        assert cap.max_cost_usd == pytest.approx(7.5)

    def test_max_cost_zero_is_valid(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": 0.0})
        assert cap.is_enabled is True
        assert cap.max_cost_usd == pytest.approx(0.0)

    def test_negative_max_cost_disables_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": -1.0})
        assert cap.is_enabled is False

    def test_invalid_max_cost_string_disables_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": "not-a-number"})
        assert cap.is_enabled is False

    def test_none_max_cost_disables_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": None})
        assert cap.is_enabled is False

    def test_non_dict_spec_gives_disabled_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec(None)  # type: ignore[arg-type]
        assert cap.is_enabled is False

    def test_escalation_mode_abort_is_default(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({"max_cost_usd": 10.0})
        assert cap.escalation_mode == "abort"

    def test_escalation_mode_human_alert(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({
            "max_cost_usd": 10.0,
            "budget_escalation_mode": "human_alert",
        })
        assert cap.escalation_mode == "human_alert"

    def test_unknown_escalation_mode_falls_back_to_abort(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({
            "max_cost_usd": 10.0,
            "budget_escalation_mode": "explode",
        })
        assert cap.escalation_mode == "abort"

    def test_custom_warn_threshold(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({
            "max_cost_usd": 10.0,
            "budget_warn_threshold": 0.5,
        })
        assert cap.warn_threshold_fraction == pytest.approx(0.5)

    def test_out_of_range_warn_threshold_uses_default(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap.from_spec({
            "max_cost_usd": 10.0,
            "budget_warn_threshold": 1.5,
        })
        # Should keep the default 0.80
        assert cap.warn_threshold_fraction == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# SpecBudgetCap.from_yaml_file
# ---------------------------------------------------------------------------

class TestFromYamlFile:
    def test_reads_max_cost_from_file(self, tmp_path):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("max_cost_usd: 25.0\nname: test\n")
        cap = SpecBudgetCap.from_yaml_file(spec_file)
        assert cap.max_cost_usd == pytest.approx(25.0)

    def test_missing_field_gives_disabled_cap(self, tmp_path):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("name: test\n")
        cap = SpecBudgetCap.from_yaml_file(spec_file)
        assert cap.is_enabled is False

    def test_file_not_found_raises(self, tmp_path):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        with pytest.raises(FileNotFoundError):
            SpecBudgetCap.from_yaml_file(tmp_path / "does_not_exist.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        spec_file = tmp_path / "bad.yaml"
        spec_file.write_text("key: [\n")  # malformed YAML
        with pytest.raises(yaml.YAMLError):
            SpecBudgetCap.from_yaml_file(spec_file)

    def test_full_spec_fields_parsed(self, tmp_path):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        content = (
            "name: myproject\n"
            "max_cost_usd: 50.0\n"
            "budget_escalation_mode: human_alert\n"
            "budget_warn_threshold: 0.7\n"
        )
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text(content)
        cap = SpecBudgetCap.from_yaml_file(spec_file)
        assert cap.max_cost_usd == pytest.approx(50.0)
        assert cap.escalation_mode == "human_alert"
        assert cap.warn_threshold_fraction == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# SpecBudgetCap.check — no cap
# ---------------------------------------------------------------------------

class TestCheckNoCap:
    def test_no_cap_always_returns_continue(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap()
        assert cap.check(0.0) == BudgetAction.CONTINUE
        assert cap.check(9999.99) == BudgetAction.CONTINUE

    def test_disabled_cap_is_not_enabled(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap()
        assert cap.is_enabled is False
        assert cap.warn_at_usd is None


# ---------------------------------------------------------------------------
# SpecBudgetCap.check — with cap
# ---------------------------------------------------------------------------

class TestCheckWithCap:
    def test_under_warn_threshold_is_continue(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=10.0)
        assert cap.check(1.0) == BudgetAction.CONTINUE

    def test_at_warn_threshold_is_warn(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=10.0, warn_threshold_fraction=0.8)
        # 8.0 >= 10.0 * 0.8 → WARN
        assert cap.check(8.0) == BudgetAction.WARN

    def test_above_warn_threshold_but_below_cap_is_warn(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=10.0, warn_threshold_fraction=0.8)
        assert cap.check(9.0) == BudgetAction.WARN

    def test_at_cap_is_abort(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=10.0)
        assert cap.check(10.0) == BudgetAction.ABORT

    def test_above_cap_is_abort(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=10.0)
        assert cap.check(15.0) == BudgetAction.ABORT

    def test_escalation_human_alert_at_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=10.0, escalation_mode="human_alert")
        assert cap.check(10.0) == BudgetAction.HUMAN_ALERT

    def test_escalation_human_alert_above_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=10.0, escalation_mode="human_alert")
        assert cap.check(20.0) == BudgetAction.HUMAN_ALERT

    def test_zero_cap_any_spend_aborts(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        cap = SpecBudgetCap(max_cost_usd=0.0)
        assert cap.check(0.0) == BudgetAction.ABORT
        assert cap.check(0.01) == BudgetAction.ABORT

    def test_warn_at_usd_computed_correctly(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap(max_cost_usd=20.0, warn_threshold_fraction=0.75)
        assert cap.warn_at_usd == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# SpecBudgetCap.remaining_usd
# ---------------------------------------------------------------------------

class TestRemainingUsd:
    def test_remaining_no_cap_is_none(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap()
        assert cap.remaining_usd(5.0) is None

    def test_remaining_with_cap(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap(max_cost_usd=10.0)
        assert cap.remaining_usd(3.0) == pytest.approx(7.0)

    def test_remaining_at_cap_is_zero(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap(max_cost_usd=10.0)
        assert cap.remaining_usd(10.0) == pytest.approx(0.0)

    def test_remaining_above_cap_clamped_to_zero(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap(max_cost_usd=10.0)
        assert cap.remaining_usd(15.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# SpecBudgetCap.summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_keys(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap(max_cost_usd=10.0)
        s = cap.summary()
        assert "max_cost_usd" in s
        assert "warn_threshold_fraction" in s
        assert "warn_at_usd" in s
        assert "escalation_mode" in s
        assert "enabled" in s

    def test_summary_enabled_true(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap(max_cost_usd=10.0)
        assert cap.summary()["enabled"] is True

    def test_summary_enabled_false(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap()
        assert cap.summary()["enabled"] is False

    def test_summary_is_json_serialisable(self):
        import json
        from bob.per_spec_compute_budget_cap import SpecBudgetCap
        cap = SpecBudgetCap(max_cost_usd=10.0)
        # Should not raise
        json.dumps(cap.summary())


# ---------------------------------------------------------------------------
# Integration: parse spec YAML with full feature workflow simulation
# ---------------------------------------------------------------------------

class TestSpecYamlIntegration:
    def test_yaml_with_max_cost_triggers_abort(self, tmp_path):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        spec = {
            "name": "integration-test",
            "max_cost_usd": 5.0,
        }
        cap = SpecBudgetCap.from_spec(spec)
        # 1.0 is well below warn threshold (80% of 5.0 = 4.0)
        assert cap.check(1.0) == BudgetAction.CONTINUE
        assert cap.check(5.0) == BudgetAction.ABORT

    def test_yaml_without_max_cost_never_aborts(self):
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        spec = {"name": "integration-test"}
        cap = SpecBudgetCap.from_spec(spec)
        for cost in [0.0, 100.0, 9999.0]:
            assert cap.check(cost) == BudgetAction.CONTINUE

    def test_typical_bootstrap_spec_format(self, tmp_path):
        """Simulate a real spec file like those in examples/."""
        from bob.per_spec_compute_budget_cap import SpecBudgetCap, BudgetAction
        content = (
            "name: Bob\n"
            "version: '0.6.0'\n"
            "max_cost_usd: 100.0\n"
            "budget_escalation_mode: human_alert\n"
            "workspace: /tmp/bob\n"
            "features:\n"
            "  - name: Feature A\n"
            "    description: Some feature\n"
        )
        spec_file = tmp_path / "bootstrap.yaml"
        spec_file.write_text(content)
        cap = SpecBudgetCap.from_yaml_file(spec_file)
        assert cap.max_cost_usd == pytest.approx(100.0)
        assert cap.escalation_mode == "human_alert"
        assert cap.check(50.0) == BudgetAction.CONTINUE
        assert cap.check(80.0) == BudgetAction.WARN
        assert cap.check(100.0) == BudgetAction.HUMAN_ALERT
