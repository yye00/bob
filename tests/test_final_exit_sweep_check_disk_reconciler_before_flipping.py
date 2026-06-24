"""Tests for bob.final_exit_sweep_check_disk_reconciler_before_flipping (F-R7-598).

Verifies that the canonical entry point
``bob.final_exit_sweep_check_disk_reconciler_before_flipping``
(function ``final_exit_sweep_check_disk_reconciler_before_flipping``)
correctly delegates to disk_reconciler.promote_if_acs_satisfied before
allowing the _final_exit_sweep to flip orphan-executing features to failed.

The fixture below uses an in-memory (tmp_path) workspace with synthetic
artifact files so no real DB calls are needed for the AC-resolution tests.
For DB-integration tests we use unittest.mock patches.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from bob.final_exit_sweep_check_disk_reconciler_before_flipping import (
    final_exit_sweep_check_disk_reconciler_before_flipping,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feature(
    feature_id: str = "feat-0000-0000-0000-000000000001",
    feature_name: str = "Test feature",
    acceptance_criteria: list[str] | None = None,
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id
    f.name = feature_name
    f.acceptance_criteria = json.dumps(acceptance_criteria or [])
    return f


# ---------------------------------------------------------------------------
# Primary AC test (must be named exactly as specified in acceptance_criteria)
# ---------------------------------------------------------------------------

def test_final_exit_sweep_check_disk_reconciler_before_flipping(tmp_path: pathlib.Path) -> None:
    """AC entry point: promoted=1 when disk satisfies all ACs; flipped_failed=0.

    When promote_if_acs_satisfied returns True for an orphan-executing feature,
    the sweep must report it as promoted, not as flipped-to-failed.
    """
    project_id = "proj-sweep-0000-0000-000000000001"
    feat = _feature(
        feature_id="feat-promo-0000-0000-000000000001",
        feature_name="Disk-satisfied feature",
        acceptance_criteria=["File exists: src/bob/my_module.py"],
    )
    features = [feat]

    with patch(
        "bob.final_exit_sweep_check_disk_reconciler_before_flipping.promote_if_acs_satisfied",
        return_value=True,
    ) as mock_promote:
        result = final_exit_sweep_check_disk_reconciler_before_flipping(
            project_id=project_id,
            orphan_executing_features=features,
        )

    mock_promote.assert_called_once_with(
        project_id=project_id,
        feature_id=feat.id,
        feature_name=feat.name,
        acceptance_criteria_json=feat.acceptance_criteria,
    )
    assert result["promoted"] == 1
    assert result["flipped_failed"] == 0


# ---------------------------------------------------------------------------
# promote_if_acs_satisfied returns False → feature must flip to failed
# ---------------------------------------------------------------------------

def test_disk_not_satisfied_falls_through_to_failed(tmp_path: pathlib.Path) -> None:
    """When promote_if_acs_satisfied returns False, the feature is counted as flipped_failed."""
    project_id = "proj-sweep-fail-0000-000000000001"
    feat = _feature(acceptance_criteria=["File exists: src/bob/missing.py"])

    with patch(
        "bob.final_exit_sweep_check_disk_reconciler_before_flipping.promote_if_acs_satisfied",
        return_value=False,
    ):
        result = final_exit_sweep_check_disk_reconciler_before_flipping(
            project_id=project_id,
            orphan_executing_features=[feat],
        )

    assert result["promoted"] == 0
    assert result["flipped_failed"] == 1


# ---------------------------------------------------------------------------
# Multiple features — mix of promoted and flipped
# ---------------------------------------------------------------------------

def test_mixed_promoted_and_flipped() -> None:
    """Multiple features: some promoted by disk-check, some flipped to failed."""
    project_id = "proj-mixed-0000-0000-000000000001"
    feat_a = _feature(feature_id="feat-a-000", acceptance_criteria=["File exists: src/a.py"])
    feat_b = _feature(feature_id="feat-b-000", acceptance_criteria=["File exists: src/b.py"])
    feat_c = _feature(feature_id="feat-c-000", acceptance_criteria=["File exists: src/c.py"])

    # feat_a and feat_c are on disk; feat_b is missing
    def _side_effect(*, project_id, feature_id, feature_name, acceptance_criteria_json):
        return feature_id in ("feat-a-000", "feat-c-000")

    with patch(
        "bob.final_exit_sweep_check_disk_reconciler_before_flipping.promote_if_acs_satisfied",
        side_effect=_side_effect,
    ):
        result = final_exit_sweep_check_disk_reconciler_before_flipping(
            project_id=project_id,
            orphan_executing_features=[feat_a, feat_b, feat_c],
        )

    assert result["promoted"] == 2
    assert result["flipped_failed"] == 1


# ---------------------------------------------------------------------------
# Empty input — no features to sweep
# ---------------------------------------------------------------------------

def test_empty_feature_list() -> None:
    """No orphan-executing features → promoted=0, flipped_failed=0."""
    result = final_exit_sweep_check_disk_reconciler_before_flipping(
        project_id="proj-empty",
        orphan_executing_features=[],
    )
    assert result["promoted"] == 0
    assert result["flipped_failed"] == 0


# ---------------------------------------------------------------------------
# Safety: promote_if_acs_satisfied never silences an error;
# a feature with empty ACs is not promoted
# ---------------------------------------------------------------------------

def test_feature_with_empty_acs_counts_as_flipped() -> None:
    """A feature with no ACs cannot be disk-promoted; it must be flipped to failed."""
    feat = _feature(acceptance_criteria=[])

    with patch(
        "bob.final_exit_sweep_check_disk_reconciler_before_flipping.promote_if_acs_satisfied",
        return_value=False,
    ):
        result = final_exit_sweep_check_disk_reconciler_before_flipping(
            project_id="proj-no-acs",
            orphan_executing_features=[feat],
        )

    assert result["flipped_failed"] == 1
    assert result["promoted"] == 0


# ---------------------------------------------------------------------------
# Summary dict shape
# ---------------------------------------------------------------------------

def test_result_keys_present() -> None:
    """Return value must always have 'promoted' and 'flipped_failed' keys."""
    result = final_exit_sweep_check_disk_reconciler_before_flipping(
        project_id="proj-keys",
        orphan_executing_features=[],
    )
    assert "promoted" in result
    assert "flipped_failed" in result


# ---------------------------------------------------------------------------
# promote_if_acs_satisfied is called for EVERY orphan feature (not short-circuit)
# ---------------------------------------------------------------------------

def test_promote_called_for_each_feature() -> None:
    """promote_if_acs_satisfied must be called once per orphan feature."""
    project_id = "proj-each-call"
    features = [
        _feature(feature_id=f"feat-{i}", acceptance_criteria=["File exists: src/x.py"])
        for i in range(4)
    ]

    with patch(
        "bob.final_exit_sweep_check_disk_reconciler_before_flipping.promote_if_acs_satisfied",
        return_value=False,
    ) as mock_promote:
        final_exit_sweep_check_disk_reconciler_before_flipping(
            project_id=project_id,
            orphan_executing_features=features,
        )

    assert mock_promote.call_count == 4


# ---------------------------------------------------------------------------
# Exception in promote_if_acs_satisfied is handled gracefully (feature → failed)
# ---------------------------------------------------------------------------

def test_exception_in_promote_counts_as_flipped() -> None:
    """If promote_if_acs_satisfied raises, the feature is treated as flipped_failed."""
    feat = _feature(acceptance_criteria=["File exists: src/x.py"])

    with patch(
        "bob.final_exit_sweep_check_disk_reconciler_before_flipping.promote_if_acs_satisfied",
        side_effect=RuntimeError("db offline"),
    ):
        result = final_exit_sweep_check_disk_reconciler_before_flipping(
            project_id="proj-exc",
            orphan_executing_features=[feat],
        )

    assert result["flipped_failed"] == 1
    assert result["promoted"] == 0
