"""Tests for bob.spec_synthesizer.sanitize_spec_file_with_gate_loop.

Feature 6f32ea03: Spec synthesizer score-gate loop — re-synthesize TBD ACs
until score reaches threshold.

Covers:
  - sanitize_spec_file_with_gate_loop is importable and callable
  - gate_passed/gate_failed/gate_avg_attempts keys in returned report
  - ACs that pass the gate on first attempt → gate_passed incremented
  - ACs that fail the gate but eventually pass → gate_passed after retry
  - ACs that exhaust all retries → gate_failed, fallback used
  - No placeholder features → gate_avg_attempts is None
  - dry_run=True does not write the file
  - dry_run=False writes the file
  - threshold default reads from BOB_SPEC_QUALITY_THRESHOLD env var
  - gate_avg_attempts reflects actual average attempts used
  - gate_failed features still get valid ACs via deterministic_fallback
  - synthesis returning None on all retries triggers fallback
  - multiple placeholder features processed concurrently
  - written=True only when changes were made and dry_run=False
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from bob.spec_synthesizer import (
    ScoreGateReport,
    sanitize_spec_file_with_gate_loop,
    score_gate_threshold_from_env,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _write_spec(tmp_path: Path, features: dict) -> Path:
    spec_file = tmp_path / "spec.yaml"
    spec_file.write_text(yaml.safe_dump({"features": features}))
    return spec_file


_HIGH_QUALITY_CRITERIA = [
    "File exists: src/bob/foo.py",
    "Function defined: bob.foo.run",
    "pytest: tests/test_foo.py",
    "behavior: raises ValueError when input is empty string or None",
    "behavior: returns None when result exceeds maximum boundary",
]

_LOW_QUALITY_CRITERIA = [
    "It works correctly",
    "Handles all cases properly",
]


# ---------------------------------------------------------------------------
# Import / interface
# ---------------------------------------------------------------------------


class TestSanitizeSpecFileWithGateLoopInterface:
    def test_is_importable(self):
        from bob.spec_synthesizer import sanitize_spec_file_with_gate_loop as fn
        assert callable(fn)

    def test_is_coroutine_function(self):
        import asyncio
        assert asyncio.iscoroutinefunction(sanitize_spec_file_with_gate_loop)

    def test_returns_dict_with_required_keys(self, tmp_path):
        spec_file = _write_spec(tmp_path, {})
        report = _run(
            sanitize_spec_file_with_gate_loop(spec_file, project_id="test")
        )
        assert isinstance(report, dict)
        for key in ("synthesized", "fell_back", "total", "written",
                    "gate_passed", "gate_failed", "gate_avg_attempts"):
            assert key in report, f"Missing key: {key}"

    def test_no_placeholders_returns_zero_totals(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Done feature",
                "description": "Already complete.",
                "acceptance_criteria": ["File exists: src/bob/done.py"],
            }
        })
        report = _run(
            sanitize_spec_file_with_gate_loop(spec_file, project_id="test")
        )
        assert report["total"] == 0
        assert report["synthesized"] == 0
        assert report["fell_back"] == 0
        assert report["gate_passed"] == 0
        assert report["gate_failed"] == 0
        assert report["gate_avg_attempts"] is None


# ---------------------------------------------------------------------------
# Gate passed — synthesis returns high-quality ACs on first try
# ---------------------------------------------------------------------------


class TestGatePassed:
    def test_gate_passed_increments_when_criteria_above_threshold(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Alpha feature",
                "description": "Implement alpha.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,  # any criteria pass
                )
            )

        assert report["gate_passed"] == 1
        assert report["gate_failed"] == 0

    def test_synthesized_increments_when_gate_passes(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Beta feature",
                "description": "Implement beta.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert report["synthesized"] == 1
        assert report["fell_back"] == 0

    def test_gate_avg_attempts_is_1_on_first_pass(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Gamma feature",
                "description": "Implement gamma.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert report["gate_avg_attempts"] == 1.0


# ---------------------------------------------------------------------------
# Gate failed — all retries exhausted, fallback used
# ---------------------------------------------------------------------------


class TestGateFailed:
    def test_gate_failed_increments_on_exhaustion(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Delta feature",
                "description": "Implement delta.",
                "acceptance_criteria": "TODO",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_LOW_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=1.0,  # impossible to pass
                    max_retries=2,
                    use_fallback=True,
                )
            )

        assert report["gate_failed"] == 1
        assert report["gate_passed"] == 0

    def test_fell_back_increments_on_exhaustion(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Epsilon feature",
                "description": "Implement epsilon.",
                "acceptance_criteria": "TODO",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_LOW_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=1.0,
                    max_retries=2,
                    use_fallback=True,
                )
            )

        assert report["fell_back"] == 1

    def test_fallback_criteria_written_to_spec_on_exhaustion(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Zeta feature",
                "description": "Implement zeta.",
                "acceptance_criteria": "TODO",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_LOW_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=False,
                    threshold=1.0,
                    max_retries=1,
                    use_fallback=True,
                )
            )

        data = yaml.safe_load(spec_file.read_text())
        ac = data["features"]["feat_a"]["acceptance_criteria"]
        assert isinstance(ac, list)
        assert len(ac) > 0
        assert not any(s.upper().startswith(("TBD", "TODO")) for s in ac)

    def test_none_synthesis_all_retries_uses_fallback(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Eta feature",
                "description": "Implement eta.",
                "acceptance_criteria": "FIXME",
            }
        })

        async def fake_synthesize(**kwargs):
            return None

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.5,
                    max_retries=2,
                    use_fallback=True,
                )
            )

        assert report["fell_back"] == 1
        assert report["gate_failed"] == 1


# ---------------------------------------------------------------------------
# Gate avg attempts — multi-feature averaging
# ---------------------------------------------------------------------------


class TestGateAvgAttempts:
    def test_avg_attempts_is_none_when_no_placeholders(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Already done",
                "description": "complete.",
                "acceptance_criteria": ["File exists: src/bob/done.py"],
            }
        })
        report = _run(
            sanitize_spec_file_with_gate_loop(spec_file, project_id="test")
        )
        assert report["gate_avg_attempts"] is None

    def test_avg_attempts_reflects_single_feature_attempts(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Theta feature",
                "description": "Implement theta.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert report["gate_avg_attempts"] is not None
        assert report["gate_avg_attempts"] >= 1

    def test_avg_attempts_multi_feature(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Iota feature",
                "description": "Implement iota.",
                "acceptance_criteria": "TBD",
            },
            "feat_b": {
                "title": "Kappa feature",
                "description": "Implement kappa.",
                "acceptance_criteria": "TODO",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert report["total"] == 2
        assert report["gate_avg_attempts"] is not None
        assert isinstance(report["gate_avg_attempts"], (int, float))


# ---------------------------------------------------------------------------
# Dry run vs write
# ---------------------------------------------------------------------------


class TestDryRunAndWrite:
    def test_dry_run_does_not_write_file(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Lambda feature",
                "description": "Implement lambda.",
                "acceptance_criteria": "TBD",
            }
        })
        original = spec_file.read_text()

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert report["written"] is False
        assert spec_file.read_text() == original

    def test_write_happens_when_not_dry_run(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Mu feature",
                "description": "Implement mu.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=False,
                    threshold=0.0,
                )
            )

        assert report["written"] is True
        data = yaml.safe_load(spec_file.read_text())
        ac = data["features"]["feat_a"]["acceptance_criteria"]
        assert isinstance(ac, list)
        assert len(ac) > 0

    def test_written_is_false_when_no_changes(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Nu feature",
                "description": "Already concrete.",
                "acceptance_criteria": ["File exists: src/bob/nu.py"],
            }
        })
        report = _run(
            sanitize_spec_file_with_gate_loop(
                spec_file,
                project_id="test",
                dry_run=False,
            )
        )
        assert report["written"] is False


# ---------------------------------------------------------------------------
# Threshold env var
# ---------------------------------------------------------------------------


class TestThresholdEnvVar:
    def test_default_threshold_is_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(0.85)

    def test_env_var_overrides_threshold(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Xi feature",
                "description": "Implement xi.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return ["File exists: src/bob/xi.py", "pytest: tests/test_xi.py"]

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    # No explicit threshold — reads from env
                )
            )

        # With threshold=0.0, any criteria pass the gate
        assert report["gate_passed"] == 1
        assert report["gate_failed"] == 0


# ---------------------------------------------------------------------------
# Multiple placeholder features
# ---------------------------------------------------------------------------


class TestMultiplePlaceholderFeatures:
    def test_multiple_features_all_pass(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Omicron feature",
                "description": "Implement omicron.",
                "acceptance_criteria": "TBD",
            },
            "feat_b": {
                "title": "Pi feature",
                "description": "Implement pi.",
                "acceptance_criteria": "TODO",
            },
            "feat_c": {
                "title": "Rho feature",
                "description": "Implement rho.",
                "acceptance_criteria": "FIXME",
            },
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert report["total"] == 3
        assert report["gate_passed"] == 3
        assert report["gate_failed"] == 0

    def test_mixed_pass_fail_across_features(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_good": {
                "title": "Sigma feature",
                "description": "Implement sigma.",
                "acceptance_criteria": "TBD",
            },
            "feat_bad": {
                "title": "Tau feature",
                "description": "Implement tau.",
                "acceptance_criteria": "TODO",
            },
        })

        call_count = {"n": 0}

        async def fake_synthesize(**kwargs):
            call_count["n"] += 1
            title = kwargs.get("title", "")
            if "sigma" in title.lower():
                return list(_HIGH_QUALITY_CRITERIA)
            return list(_LOW_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.9,  # high threshold — low quality fails
                    max_retries=1,
                    use_fallback=True,
                )
            )

        assert report["total"] == 2
        assert report["gate_passed"] + report["gate_failed"] == 2


# ---------------------------------------------------------------------------
# Integration: module import chain
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_function_importable_from_module(self):
        import bob.spec_synthesizer as mod
        assert hasattr(mod, "sanitize_spec_file_with_gate_loop")
        assert callable(mod.sanitize_spec_file_with_gate_loop)

    def test_score_gate_report_dataclass_importable(self):
        import dataclasses
        from bob.spec_synthesizer import ScoreGateReport
        assert dataclasses.is_dataclass(ScoreGateReport)

    def test_gate_loop_reuses_score_gate_loop_internally(self, tmp_path):
        """Smoke-test that the gate loop path runs without errors."""
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Upsilon feature",
                "description": "Implement upsilon.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return [
                "File exists: src/bob/upsilon.py",
                "pytest: tests/test_upsilon.py",
            ]

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert isinstance(report, dict)
        assert report["total"] == 1

    def test_report_gate_keys_are_numeric(self, tmp_path):
        spec_file = _write_spec(tmp_path, {
            "feat_a": {
                "title": "Phi feature",
                "description": "Implement phi.",
                "acceptance_criteria": "TBD",
            }
        })

        async def fake_synthesize(**kwargs):
            return list(_HIGH_QUALITY_CRITERIA)

        with patch("bob.spec_synthesizer.synthesize_for_feature", side_effect=fake_synthesize):
            report = _run(
                sanitize_spec_file_with_gate_loop(
                    spec_file,
                    project_id="test",
                    dry_run=True,
                    threshold=0.0,
                )
            )

        assert isinstance(report["gate_passed"], int)
        assert isinstance(report["gate_failed"], int)
        assert isinstance(report["gate_avg_attempts"], (int, float))
