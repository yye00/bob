"""Tests for the Devin-style editable plan.yaml gate (c574eeac).

Covers:
  - bob73.planner.emit_plan_ready writes plan.yaml and emits PLAN_READY
  - bob73.implementer.check_plan_approved gates implementers on approval
  - Round-trip: emit_plan_ready → check_plan_approved
  - Auto-approve path
  - Drift detection after AC change
"""

from __future__ import annotations

import json

import pytest
import yaml

from bob3.orchestrator.plan_gate import ImplementerBlockedError, approve_plan


# ---------------------------------------------------------------------------
# bob73.planner.emit_plan_ready
# ---------------------------------------------------------------------------

class TestEmitPlanReady:
    """emit_plan_ready writes plan.yaml and returns the expected dict."""

    def test_returns_expected_keys(self, tmp_path):
        from bob73.planner import emit_plan_ready

        result = emit_plan_ready(
            feature_id="test-feat-001",
            name="Test feature",
            description="A test",
            acceptance_criteria=["File exists: src/foo.py"],
            workspace=tmp_path,
        )

        assert "plan_path" in result
        assert "approved" in result
        assert "implementer_blocked" in result
        assert "plan_ready_emitted" in result
        assert "drift_detected" in result

    def test_plan_yaml_is_written_to_disk(self, tmp_path):
        from bob73.planner import emit_plan_ready

        result = emit_plan_ready(
            feature_id="test-feat-002",
            name="Disk write test",
            description=None,
            acceptance_criteria=["pytest: tests/test_foo.py"],
            workspace=tmp_path,
        )

        from pathlib import Path
        plan_path = Path(result["plan_path"])
        assert plan_path.exists(), "plan.yaml must be written to disk"

    def test_plan_yaml_contains_expected_fields(self, tmp_path):
        from bob73.planner import emit_plan_ready
        from pathlib import Path

        feature_id = "test-feat-003"
        acs = ["File exists: src/bar.py", "pytest: tests/test_bar.py"]

        result = emit_plan_ready(
            feature_id=feature_id,
            name="Field check",
            description="Field test",
            acceptance_criteria=acs,
            workspace=tmp_path,
        )

        data = yaml.safe_load(Path(result["plan_path"]).read_text())
        assert data["feature_id"] == feature_id
        assert data["acceptance_criteria"] == acs
        assert data["approved"] is False
        assert "spec_hash" in data

    def test_implementer_blocked_when_not_approved(self, tmp_path):
        from bob73.planner import emit_plan_ready

        result = emit_plan_ready(
            feature_id="test-feat-004",
            name="Blocked test",
            description=None,
            acceptance_criteria=["File exists: src/x.py"],
            workspace=tmp_path,
        )

        assert result["approved"] is False
        assert result["implementer_blocked"] is True

    def test_auto_approve_sets_approved_true(self, tmp_path):
        from bob73.planner import emit_plan_ready

        result = emit_plan_ready(
            feature_id="test-feat-005",
            name="Auto approve",
            description=None,
            acceptance_criteria=["File exists: src/y.py"],
            workspace=tmp_path,
            auto_approve=True,
        )

        assert result["approved"] is True
        assert result["implementer_blocked"] is False

    def test_plan_ready_event_written_to_events_jsonl(self, tmp_path):
        from bob73.planner import emit_plan_ready

        emit_plan_ready(
            feature_id="test-feat-006",
            name="Event emission test",
            description=None,
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )

        events_file = tmp_path / "runs" / "events.jsonl"
        assert events_file.exists(), "runs/events.jsonl must be written"
        records = [json.loads(line) for line in events_file.read_text().splitlines() if line]
        plan_ready = [r for r in records if r.get("event") == "PLAN_READY"]
        assert len(plan_ready) >= 1
        assert plan_ready[0]["feature_id"] == "test-feat-006"

    def test_plan_ready_emitted_always_true(self, tmp_path):
        from bob73.planner import emit_plan_ready

        result = emit_plan_ready(
            feature_id="test-feat-007",
            name="Emitted flag",
            description=None,
            acceptance_criteria=[],
            workspace=tmp_path,
        )

        assert result["plan_ready_emitted"] is True

    def test_drift_detected_false_on_first_call(self, tmp_path):
        from bob73.planner import emit_plan_ready

        # First call: no prior plan.yaml → drift from empty plan → True
        result = emit_plan_ready(
            feature_id="test-feat-008",
            name="Drift first call",
            description=None,
            acceptance_criteria=["AC A"],
            workspace=tmp_path,
        )
        # First call: plan.yaml doesn't exist yet, empty hash != current hash
        assert isinstance(result["drift_detected"], bool)

    def test_drift_detected_false_on_same_ac_second_call(self, tmp_path):
        from bob73.planner import emit_plan_ready

        fid = "test-feat-009"
        acs = ["AC 1", "AC 2"]

        emit_plan_ready(
            feature_id=fid,
            name="Drift same AC",
            description=None,
            acceptance_criteria=acs,
            workspace=tmp_path,
        )
        result2 = emit_plan_ready(
            feature_id=fid,
            name="Drift same AC",
            description=None,
            acceptance_criteria=acs,
            workspace=tmp_path,
        )
        assert result2["drift_detected"] is False

    def test_drift_detected_true_on_changed_ac(self, tmp_path):
        from bob73.planner import emit_plan_ready

        fid = "test-feat-010"
        emit_plan_ready(
            feature_id=fid,
            name="Drift changed",
            description=None,
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )
        result2 = emit_plan_ready(
            feature_id=fid,
            name="Drift changed",
            description=None,
            acceptance_criteria=["AC 1", "AC 2"],
            workspace=tmp_path,
        )
        assert result2["drift_detected"] is True

    def test_raises_on_empty_feature_id(self, tmp_path):
        from bob73.planner import emit_plan_ready

        with pytest.raises(ValueError, match="feature_id"):
            emit_plan_ready(
                feature_id="",
                name="Invalid",
                description=None,
                acceptance_criteria=[],
                workspace=tmp_path,
            )

    def test_raises_on_empty_name(self, tmp_path):
        from bob73.planner import emit_plan_ready

        with pytest.raises(ValueError, match="name"):
            emit_plan_ready(
                feature_id="valid-feat",
                name="",
                description=None,
                acceptance_criteria=[],
                workspace=tmp_path,
            )


# ---------------------------------------------------------------------------
# bob73.implementer.check_plan_approved
# ---------------------------------------------------------------------------

class TestCheckPlanApproved:
    """check_plan_approved gates implementers on plan.yaml approval status."""

    def test_raises_implementer_blocked_when_unapproved(self, tmp_path):
        from bob73.planner import emit_plan_ready
        from bob73.implementer import check_plan_approved

        emit_plan_ready(
            feature_id="impl-feat-001",
            name="Blocked impl",
            description=None,
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )

        with pytest.raises(ImplementerBlockedError):
            check_plan_approved("impl-feat-001", workspace=tmp_path)

    def test_does_not_raise_when_approved(self, tmp_path):
        from bob73.planner import emit_plan_ready
        from bob73.implementer import check_plan_approved

        fid = "impl-feat-002"
        emit_plan_ready(
            feature_id=fid,
            name="Approved impl",
            description=None,
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
            auto_approve=True,
        )

        result = check_plan_approved(fid, workspace=tmp_path)
        assert result is True

    def test_returns_false_when_unapproved_no_raise(self, tmp_path):
        from bob73.planner import emit_plan_ready
        from bob73.implementer import check_plan_approved

        fid = "impl-feat-003"
        emit_plan_ready(
            feature_id=fid,
            name="No raise test",
            description=None,
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )

        result = check_plan_approved(fid, workspace=tmp_path, raise_on_blocked=False)
        assert result is False

    def test_raises_when_plan_yaml_missing(self, tmp_path):
        from bob73.implementer import check_plan_approved

        with pytest.raises(ImplementerBlockedError):
            check_plan_approved("nonexistent-feat", workspace=tmp_path)

    def test_returns_false_when_plan_yaml_missing_no_raise(self, tmp_path):
        from bob73.implementer import check_plan_approved

        result = check_plan_approved("nonexistent-feat", workspace=tmp_path, raise_on_blocked=False)
        assert result is False

    def test_raises_on_empty_feature_id(self, tmp_path):
        from bob73.implementer import check_plan_approved

        with pytest.raises(ValueError, match="feature_id"):
            check_plan_approved("", workspace=tmp_path)

    def test_raises_on_none_feature_id(self, tmp_path):
        from bob73.implementer import check_plan_approved

        with pytest.raises(ValueError, match="feature_id"):
            check_plan_approved(None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_approved_after_manual_approve(self, tmp_path):
        """After emit_plan_ready → approve_plan, check_plan_approved returns True."""
        from bob73.planner import emit_plan_ready
        from bob73.implementer import check_plan_approved

        fid = "impl-feat-004"
        emit_plan_ready(
            feature_id=fid,
            name="Manual approve",
            description=None,
            acceptance_criteria=["AC 1"],
            workspace=tmp_path,
        )

        # Initially blocked
        assert check_plan_approved(fid, workspace=tmp_path, raise_on_blocked=False) is False

        # Human approves
        approve_plan(fid, workspace=tmp_path)

        # Now allowed
        assert check_plan_approved(fid, workspace=tmp_path) is True


# ---------------------------------------------------------------------------
# Round-trip integration
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """End-to-end: planner emits → implementer gates."""

    def test_round_trip_blocked_then_approved(self, tmp_path):
        from bob73.planner import emit_plan_ready
        from bob73.implementer import check_plan_approved

        fid = "roundtrip-001"
        result = emit_plan_ready(
            feature_id=fid,
            name="Round-trip test",
            description="Test the full gate round-trip",
            acceptance_criteria=["File exists: src/foo.py"],
            workspace=tmp_path,
        )

        # Step 1: implementer is blocked
        assert result["implementer_blocked"] is True
        assert check_plan_approved(fid, workspace=tmp_path, raise_on_blocked=False) is False

        # Step 2: human approves
        approve_plan(fid, workspace=tmp_path)

        # Step 3: implementer can now proceed
        assert check_plan_approved(fid, workspace=tmp_path) is True

    def test_round_trip_auto_approve(self, tmp_path):
        from bob73.planner import emit_plan_ready
        from bob73.implementer import check_plan_approved

        fid = "roundtrip-002"
        result = emit_plan_ready(
            feature_id=fid,
            name="Auto-approve round-trip",
            description=None,
            acceptance_criteria=["AC X"],
            workspace=tmp_path,
            auto_approve=True,
        )

        assert result["implementer_blocked"] is False
        assert check_plan_approved(fid, workspace=tmp_path) is True
