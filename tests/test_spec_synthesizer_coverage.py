"""Coverage tests for bob.spec_synthesizer.

Verifies the two format-bug fixes that caused synthesized=0/118 across bob66-70:

(1) parse_criteria_response must extract criterion text from OBJECT-format LLM
    output (list of dicts), not str(dict) into an unverifiable Python-repr.
(2) inject_boundary_and_error_acs must guarantee at least one boundary-condition
    AC and one error-path AC so the weighted-geometric-mean composite score is
    not driven to 0.0 by a zero boundary/error sub-metric.
"""
import re

import pytest

from bob.spec_synthesizer import (
    parse_criteria_response,
    inject_boundary_and_error_acs,
)

_BOUNDARY_RE = re.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|boundary|"
    r"edge case|corner case|overflow|underflow|limit|threshold|floor|ceiling)\b",
    re.IGNORECASE,
)
_ERROR_RE = re.compile(
    r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|block|"
    r"does not|cannot|must not|shall not|ValueError|KeyError|TypeError|RuntimeError)\b",
    re.IGNORECASE,
)


class TestParseCriteriaResponseStrings:
    def test_flat_string_array(self):
        resp = '```json\n["File exists: src/foo.py", "pytest: tests/test_foo.py"]\n```'
        result = parse_criteria_response(resp)
        assert result == ["File exists: src/foo.py", "pytest: tests/test_foo.py"]

    def test_bare_inline_array_without_fence(self):
        resp = 'Here you go: ["pytest: tests/test_bar.py"] end'
        result = parse_criteria_response(resp)
        assert result == ["pytest: tests/test_bar.py"]

    def test_malformed_json_returns_none(self):
        assert parse_criteria_response("```json\n[not valid json\n```") is None

    def test_no_json_returns_none(self):
        assert parse_criteria_response("just prose, no array here") is None


class TestParseCriteriaResponseObjects:
    def test_object_with_criterion_key(self):
        resp = (
            '```json\n[{"id": 1, "criterion": "File exists: src/x.py", '
            '"description": "the module"}]\n```'
        )
        result = parse_criteria_response(resp)
        assert result == ["File exists: src/x.py"]

    def test_object_never_yields_python_repr(self):
        resp = '```json\n[{"id": 1, "criterion": "pytest: tests/test_x.py"}]\n```'
        result = parse_criteria_response(resp)
        assert result is not None
        for item in result:
            assert not item.startswith("{"), f"object leaked as repr: {item!r}"
            assert "'id'" not in item

    def test_object_alternate_keys(self):
        for key in ("ac", "acceptance_criterion", "text", "criteria", "value", "description"):
            resp = f'```json\n[{{"{key}": "Function defined: mod.fn"}}]\n```'
            result = parse_criteria_response(resp)
            assert result == ["Function defined: mod.fn"], f"key={key} failed"

    def test_mixed_strings_and_objects(self):
        resp = (
            '```json\n["File exists: src/a.py", '
            '{"criterion": "pytest: tests/test_a.py"}]\n```'
        )
        result = parse_criteria_response(resp)
        assert result == ["File exists: src/a.py", "pytest: tests/test_a.py"]


class TestInjectBoundaryAndErrorAcs:
    def test_injects_both_when_absent(self):
        criteria = [
            "File exists: src/foo.py",
            "Function defined: foo.bar",
            "pytest: tests/test_foo.py",
            "integration: foo",
        ]
        out = inject_boundary_and_error_acs(criteria, title="my feature")
        probe = " ".join(out)
        assert _BOUNDARY_RE.search(probe), "boundary AC not injected"
        assert _ERROR_RE.search(probe), "error AC not injected"
        assert len(out) == len(criteria) + 2

    def test_preserves_original_criteria(self):
        criteria = ["File exists: src/foo.py"]
        out = inject_boundary_and_error_acs(criteria, title="feat")
        for c in criteria:
            assert c in out

    def test_no_duplicate_when_both_present(self):
        criteria = [
            "pytest: tests/test_x_boundary.py — empty input returns a result",
            "pytest: tests/test_x_error.py — invalid input raises ValueError",
        ]
        out = inject_boundary_and_error_acs(criteria, title="feat")
        assert len(out) == len(criteria)

    def test_injected_ac_references_feature_slug(self):
        out = inject_boundary_and_error_acs(
            ["File exists: src/foo.py"], title="widget synthesizer"
        )
        injected = [c for c in out if c.startswith("pytest:")]
        assert any("widget" in c for c in injected)


class TestParseCriteriaResponseBoundary:
    def test_empty_string_returns_none(self):
        assert parse_criteria_response("") is None

    def test_empty_array_returns_none(self):
        assert parse_criteria_response("```json\n[]\n```") is None


class TestInjectErrorPath:
    def test_non_list_raises(self):
        with pytest.raises(TypeError):
            inject_boundary_and_error_acs("not a list", title="x")  # type: ignore[arg-type]
