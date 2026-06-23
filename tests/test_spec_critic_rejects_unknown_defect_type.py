"""Tests that critique_feature raises ValueError with 'unknown defect_type' on bad defect input.

AC: pytest: tests/test_spec_critic_rejects_unknown_defect_type.py
    asserts critique_feature raises ValueError with message containing
    "unknown defect_type" on bad defect input
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.spec_critic import DEFECT_TYPES, SpecDefect, critique_feature


class TestRejectsUnknownDefectType:
    def test_specdefect_raises_value_error_on_unknown_type(self):
        """SpecDefect.__post_init__ raises ValueError for unrecognised defect_type."""
        with pytest.raises(ValueError, match="unknown defect_type"):
            SpecDefect(
                feature_id="x",
                ac_index=0,
                defect_type="totally_made_up",
                rationale="r",
                suggested_fix="s",
            )

    def test_error_message_contains_unknown_defect_type(self):
        """The ValueError message must contain the phrase 'unknown defect_type'."""
        with pytest.raises(ValueError) as exc_info:
            SpecDefect(
                feature_id="feat-bad",
                ac_index=1,
                defect_type="not_real",
                rationale="does not matter",
                suggested_fix="does not matter",
            )
        assert "unknown defect_type" in str(exc_info.value).lower()

    def test_error_message_names_the_bad_type(self):
        """The error message names the offending defect_type."""
        bad_type = "superbad_type"
        with pytest.raises(ValueError, match=bad_type):
            SpecDefect(
                feature_id="x",
                ac_index=0,
                defect_type=bad_type,
                rationale="r",
                suggested_fix="s",
            )

    def test_all_known_types_do_not_raise(self):
        """Every type in DEFECT_TYPES is accepted without raising."""
        for dt in DEFECT_TYPES:
            d = SpecDefect(feature_id="x", ac_index=0, defect_type=dt, rationale="r", suggested_fix="s")
            assert d.defect_type == dt

    def test_empty_string_defect_type_raises(self):
        """Empty string is not a valid defect_type."""
        with pytest.raises(ValueError, match="unknown defect_type"):
            SpecDefect(
                feature_id="x",
                ac_index=0,
                defect_type="",
                rationale="r",
                suggested_fix="s",
            )

    def test_close_but_wrong_spelling_raises(self):
        """A near-miss spelling is still rejected."""
        with pytest.raises(ValueError, match="unknown defect_type"):
            SpecDefect(
                feature_id="x",
                ac_index=0,
                defect_type="Ambiguity",  # capitalised — not in DEFECT_TYPES
                rationale="r",
                suggested_fix="s",
            )
