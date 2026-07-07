"""Tests for bob.synthesizer_boundary_error_injector.

Covers the two root causes of synthesized=0/118 across prior generations:
(1) parse_criteria_response must handle object-format LLM output (fenced AND
    bare), extracting criterion text rather than str(dict) garbage.
(2) inject_boundary_and_error_acs must guarantee a boundary AC and an
    error-path AC so the geometric-mean composite is never forced to 0.0.
"""
import re

import pytest

from bob.synthesizer_boundary_error_injector import (
    extract_criterion_text_from_object_format,
    inject_boundary_and_error_acs,
)
from bob.criteria_parser import parse_criteria_response


_BOUNDARY_RE = re.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|boundary|limit)\b",
    re.IGNORECASE,
)
_ERROR_RE = re.compile(
    r"\b(error|exception|fail|invalid|reject|raise|must not|does not)\b",
    re.IGNORECASE,
)


class TestExtractCriterionText:
    def test_criterion_key(self):
        assert (
            extract_criterion_text_from_object_format({"criterion": "pytest: tests/test_x.py"})
            == "pytest: tests/test_x.py"
        )

    def test_key_priority_criterion_over_description(self):
        obj = {"description": "some prose", "criterion": "File exists: src/x.py"}
        assert extract_criterion_text_from_object_format(obj) == "File exists: src/x.py"

    def test_fallback_to_description(self):
        assert (
            extract_criterion_text_from_object_format({"id": 3, "description": "integration: bob.x"})
            == "integration: bob.x"
        )

    def test_no_known_key_returns_empty(self):
        assert extract_criterion_text_from_object_format({"id": 1, "weight": 2}) == ""

    def test_strips_whitespace(self):
        assert extract_criterion_text_from_object_format({"ac": "  pytest: t.py  "}) == "pytest: t.py"

    def test_non_dict_raises_typeerror(self):
        with pytest.raises(TypeError):
            extract_criterion_text_from_object_format("not a dict")


class TestParseObjectFormat:
    def test_flat_string_array(self):
        assert parse_criteria_response('["File exists: src/x.py"]') == ["File exists: src/x.py"]

    def test_fenced_object_array(self):
        txt = '```json\n[{"id":1,"criterion":"pytest: tests/test_x.py"}]\n```'
        assert parse_criteria_response(txt) == ["pytest: tests/test_x.py"]

    def test_bare_object_array(self):
        # No ```json fence — the real-world failure mode from generation-70.
        txt = '[{"id":1,"criterion":"pytest: tests/test_x.py"},{"criterion":"File exists: src/y.py"}]'
        assert parse_criteria_response(txt) == ["pytest: tests/test_x.py", "File exists: src/y.py"]

    def test_object_array_never_yields_python_repr(self):
        result = parse_criteria_response('[{"criterion":"File exists: src/x.py"}]')
        assert result is not None
        assert all("{" not in c and "'" not in c for c in result)


class TestInjectBoundaryAndError:
    def test_structural_only_gets_both_injected(self):
        criteria = [
            "File exists: src/bob/x.py",
            "Function defined: bob.x.f",
            "pytest: tests/test_x.py",
            "integration: bob.x",
        ]
        out = inject_boundary_and_error_acs(criteria, title="My Feature")
        assert len(out) == len(criteria) + 2
        joined = " ".join(out[len(criteria):])
        assert _BOUNDARY_RE.search(joined)
        assert _ERROR_RE.search(joined)

    def test_no_duplicate_when_both_present(self):
        criteria = [
            "pytest: tests/test_x.py — empty input returns a well-defined result (boundary case)",
            "pytest: tests/test_y.py — invalid input raises ValueError (error path)",
        ]
        out = inject_boundary_and_error_acs(criteria, title="Feat")
        assert out == criteria

    def test_only_error_injected_when_boundary_present(self):
        criteria = [
            "pytest: tests/test_x.py — empty list returns a well-defined result (boundary case)",
        ]
        out = inject_boundary_and_error_acs(criteria, title="Feat")
        assert len(out) == 2
        assert _ERROR_RE.search(out[-1])

    def test_injected_ac_references_slug(self):
        out = inject_boundary_and_error_acs(["File exists: src/x.py"], title="Widget Sync")
        assert any("widget_sync" in c for c in out)

    def test_returns_new_list(self):
        criteria = ["File exists: src/x.py"]
        out = inject_boundary_and_error_acs(criteria, title="F")
        assert out is not criteria
        assert criteria == ["File exists: src/x.py"]

    def test_non_list_raises_typeerror(self):
        with pytest.raises(TypeError):
            inject_boundary_and_error_acs("not a list", title="F")

    def test_non_string_item_raises_valueerror(self):
        with pytest.raises(ValueError):
            inject_boundary_and_error_acs(["ok", 123], title="F")
