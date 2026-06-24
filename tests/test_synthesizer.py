"""Tests for bob3.spec_synthesizer.emit_file_exists_acs and
tools.spec_quality_score.filter_api_surfaces.

Covers:
- emit_file_exists_acs emits File-exists ACs for .py paths named in description
- emit_file_exists_acs does not double-add already-covered paths
- emit_file_exists_acs is a no-op when description names no concrete paths
- filter_api_surfaces keeps code-shaped tokens and drops prose words
- Integration: contract_completeness is not zeroed by prose words
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# emit_file_exists_acs
# ---------------------------------------------------------------------------

class TestEmitFileExistsAcs:
    """Function defined: synthesizer.emit_file_exists_acs"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from bob3.spec_synthesizer import emit_file_exists_acs
        self.fn = emit_file_exists_acs

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_emits_ac_for_concrete_py_path(self):
        """When description names src/bob3/brownfield/survey.py, emit File exists AC."""
        description = "Implement the survey in src/bob3/brownfield/survey.py."
        result = self.fn([], description)
        assert any("File exists: src/bob3/brownfield/survey.py" in ac for ac in result), (
            f"Expected File-exists AC for survey.py, got: {result}"
        )

    def test_emits_ac_for_tools_path(self):
        """When description names tools/spec_quality_score.py, emit File exists AC."""
        description = "The scorer lives in tools/spec_quality_score.py."
        result = self.fn([], description)
        assert any("File exists: tools/spec_quality_score.py" in ac for ac in result)

    def test_does_not_double_add_already_covered_path(self):
        """Paths already covered by an AC are not emitted again."""
        description = "Implement src/bob3/brownfield/survey.py."
        existing = ["File exists: src/bob3/brownfield/survey.py"]
        result = self.fn(existing, description)
        count = sum(1 for ac in result if "survey.py" in ac)
        assert count == 1, f"Path should not be duplicated; got {result}"

    def test_no_op_when_no_concrete_paths(self):
        """Description with no concrete .py paths returns criteria unchanged."""
        description = "A feature that does something useful."
        existing = ["pytest: tests/test_foo.py"]
        result = self.fn(existing, description)
        assert result == existing

    def test_bare_filename_without_dir_is_skipped(self):
        """Bare foo.py (no directory) is ambiguous and must not generate an AC."""
        description = "The file foo.py handles this."
        result = self.fn([], description)
        assert not any("File exists: foo.py" in ac for ac in result)

    def test_empty_description_returns_criteria_unchanged(self):
        """Empty description is a no-op."""
        existing = ["pytest: tests/test_foo.py"]
        result = self.fn(existing, "")
        assert result == existing

    def test_none_description_returns_criteria_unchanged(self):
        """None description is a no-op."""
        existing = ["pytest: tests/test_foo.py"]
        result = self.fn(existing, None)
        assert result == existing

    def test_multiple_paths_all_emitted(self):
        """All distinct concrete paths in description get File-exists ACs."""
        description = (
            "Implement src/bob3/brownfield/survey.py "
            "and also tools/spec_quality_score.py."
        )
        result = self.fn([], description)
        assert any("src/bob3/brownfield/survey.py" in ac for ac in result)
        assert any("tools/spec_quality_score.py" in ac for ac in result)

    def test_empty_criteria_and_description_returns_empty(self):
        """Empty criteria + empty description → empty list."""
        result = self.fn([], "")
        assert result == []

    def test_preserves_existing_criteria(self):
        """Existing ACs are not lost when new File-exists ACs are added."""
        description = "Implement src/bob3/brownfield/survey.py."
        existing = ["pytest: tests/test_survey.py", "Function defined: survey.run_survey"]
        result = self.fn(existing, description)
        assert "pytest: tests/test_survey.py" in result
        assert "Function defined: survey.run_survey" in result


# ---------------------------------------------------------------------------
# filter_api_surfaces
# ---------------------------------------------------------------------------

class TestFilterApiSurfaces:
    """Function defined: spec_quality_score.filter_api_surfaces"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.spec_quality_score import filter_api_surfaces
        self.fn = filter_api_surfaces

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_keeps_underscore_tokens(self):
        result = self.fn(["extract_py_paths", "compute_score"])
        assert "extract_py_paths" in result
        assert "compute_score" in result

    def test_keeps_dotted_tokens(self):
        result = self.fn(["tools.spec_quality_score", "bob3.spec_synthesizer"])
        assert "tools.spec_quality_score" in result

    def test_keeps_py_extension_tokens(self):
        result = self.fn(["foo.py", "tools/bar.py"])
        assert "foo.py" in result

    def test_keeps_camel_case_tokens(self):
        result = self.fn(["CompositeScore", "RetryCounter"])
        assert "CompositeScore" in result
        assert "RetryCounter" in result

    def test_drops_plain_english_words(self):
        result = self.fn(["name", "gate", "correctly", "returns", "failures"])
        assert result == []

    def test_drops_stopwords(self):
        result = self.fn(["defined", "implemented", "declared"])
        assert result == []

    def test_drops_all_uppercase_tokens(self):
        result = self.fn(["TODO", "FOO", "NAME", "API"])
        assert result == []

    def test_drops_pluralised_acronyms(self):
        result = self.fn(["ACs", "IDs"])
        assert result == []

    def test_drops_empty_string(self):
        result = self.fn([""])
        assert result == []

    def test_empty_input_returns_empty(self):
        assert self.fn([]) == []

    def test_preserves_order(self):
        tokens = ["extract_py_paths", "CompositeScore", "filter_api_surfaces"]
        result = self.fn(tokens)
        assert result == tokens

    def test_mixed_input(self):
        tokens = ["extract_py_paths", "name", "CompositeScore", "defined", "tools.score"]
        result = self.fn(tokens)
        assert "extract_py_paths" in result
        assert "CompositeScore" in result
        assert "tools.score" in result
        assert "name" not in result
        assert "defined" not in result


# ---------------------------------------------------------------------------
# Integration: contract_completeness not zeroed by prose words
# ---------------------------------------------------------------------------

class TestIntegrationSpecQualityScore:
    """Integration: spec_quality.score"""

    def test_prose_words_do_not_zero_contract_completeness(self):
        """Scorer MUST NOT treat non-code English words as uncovered API surfaces."""
        from tools.spec_quality_score import compute
        description = (
            "A function defined: my_func() — it returns results correctly and "
            "handles failures. The gate name is checked."
        )
        acs = [
            "Function defined: spec_quality_score.my_func",
            "pytest: tests/test_my_feature.py",
            "pytest: tests/test_my_feature_boundary.py — boundary",
            "pytest: tests/test_my_feature_error.py — error",
        ]
        result = compute(name="Test feature", description=description, acceptance_criteria=acs)
        assert result.contract_completeness > 0.0, (
            f"contract_completeness should not be zeroed by prose words like "
            f"'defined', 'name', 'gate', 'correctly', 'returns', 'failures'; "
            f"got {result.contract_completeness}"
        )

    def test_described_py_path_covered_by_file_exists_ac(self):
        """When description names a .py path, scorer treats it covered if File-exists AC exists."""
        from tools.spec_quality_score import compute
        description = "Implement src/bob3/brownfield/survey.py to scan the codebase."
        acs = [
            "File exists: src/bob3/brownfield/survey.py",
            "pytest: tests/test_survey_boundary.py — boundary",
            "pytest: tests/test_survey_error.py — error",
        ]
        result = compute(name="Survey feature", description=description, acceptance_criteria=acs)
        assert result.contract_completeness > 0.0, (
            f"survey.py is covered by File-exists AC; contract_completeness={result.contract_completeness}"
        )

    def test_emit_file_exists_acs_prevents_contract_zero(self):
        """emit_file_exists_acs on a description with a named .py path raises contract_completeness."""
        from tools.spec_quality_score import compute
        from bob3.spec_synthesizer import emit_file_exists_acs
        description = "Implement src/bob3/brownfield/survey.py to scan the codebase."
        base_acs = [
            "pytest: tests/test_survey.py",
            "pytest: tests/test_survey_boundary.py — boundary",
            "pytest: tests/test_survey_error.py — error",
        ]
        augmented = emit_file_exists_acs(base_acs, description)
        result = compute(name="Survey feature", description=description, acceptance_criteria=augmented)
        assert result.contract_completeness > 0.0, (
            f"emit_file_exists_acs should fix contract_completeness; got {result.contract_completeness}. "
            f"augmented ACs: {augmented}"
        )


# ---------------------------------------------------------------------------
# parse_criteria_response — object-format parsing
# ---------------------------------------------------------------------------

def test_parse_object_format_criteria():
    """parse_criteria_response handles list-of-objects from LLM, not just flat strings.

    The model frequently returns [{"id":1,"criterion":"...","description":"..."}].
    str(dict) produces a Python-repr string that is not a verifiable AC and scores
    ~0.  parse_criteria_response must extract the criterion text from known keys.
    """
    from bob3.synthesizer import parse_criteria_response

    # Object format with "criterion" key
    response = '```json\n[{"id":1,"criterion":"File exists: src/bob3/foo.py","description":"The module"}]\n```'
    result = parse_criteria_response(response)
    assert result is not None, "Should parse object-format LLM response"
    assert len(result) == 1
    assert result[0] == "File exists: src/bob3/foo.py", f"Expected criterion text, got: {result[0]}"

    # Object format with "ac" key
    response2 = '```json\n[{"ac":"pytest: tests/test_bar.py","description":"runs tests"}]\n```'
    result2 = parse_criteria_response(response2)
    assert result2 is not None
    assert result2[0] == "pytest: tests/test_bar.py"

    # Mixed: flat strings and objects
    response3 = '```json\n["Function defined: bob3.foo.bar",{"criterion":"integration: bob3.orchestrator"}]\n```'
    result3 = parse_criteria_response(response3)
    assert result3 is not None
    assert len(result3) == 2
    assert "Function defined: bob3.foo.bar" in result3
    assert "integration: bob3.orchestrator" in result3

    # str(dict) Python-repr must NOT appear in results
    assert not any(r.startswith("{'") or r.startswith('{"') for r in (result or [])), (
        "parse_criteria_response must not return raw dict repr strings"
    )


# ---------------------------------------------------------------------------
# inject_boundary_and_error_acs — coverage injection
# ---------------------------------------------------------------------------

def test_inject_boundary_error_acs_coverage():
    """inject_boundary_and_error_acs adds boundary and error ACs when missing.

    When LLM produces only structural ACs (File exists / Function defined /
    pytest-without-boundary-keyword), the composite geometric mean is 0.0
    because boundary_coverage=0 AND error_path_coverage=0.  The injector must
    add one boundary AC and one error AC to fix this.
    """
    from bob3.synthesizer import inject_boundary_and_error_acs

    structural_only = [
        "File exists: src/bob3/synthesizer.py",
        "Function defined: bob3.synthesizer.parse_criteria_response",
        "pytest: tests/test_synthesizer.py",
        "integration: bob3.orchestrator",
    ]
    result = inject_boundary_and_error_acs(structural_only, title="My Feature")
    assert isinstance(result, list)
    assert len(result) > len(structural_only), "Should have injected at least one AC"

    joined = " ".join(result).lower()
    # boundary coverage keywords
    boundary_tokens = ("empty", "null", "zero", "maximum", "minimum", "boundary", "limit")
    assert any(tok in joined for tok in boundary_tokens), (
        f"Expected boundary keyword in injected ACs, got: {result}"
    )
    # error coverage keywords
    error_tokens = ("error", "exception", "fail", "invalid", "reject", "raise", "does not", "must not")
    assert any(tok in joined for tok in error_tokens), (
        f"Expected error keyword in injected ACs, got: {result}"
    )

    # If criteria already have boundary and error ACs, must NOT double-inject
    already_covered = [
        "pytest: tests/test_my_feature_boundary.py — empty input returns None (boundary case)",
        "pytest: tests/test_my_feature_error.py — invalid input raises ValueError (error path)",
    ]
    result2 = inject_boundary_and_error_acs(already_covered, title="My Feature")
    boundary_count = sum(
        1 for ac in result2
        if any(tok in ac.lower() for tok in boundary_tokens)
    )
    error_count = sum(
        1 for ac in result2
        if any(tok in ac.lower() for tok in error_tokens)
    )
    assert boundary_count == 1, f"Should not double-inject boundary AC, got count={boundary_count}: {result2}"
    assert error_count == 1, f"Should not double-inject error AC, got count={error_count}: {result2}"


# ---------------------------------------------------------------------------
# composite score is non-zero after injection
# ---------------------------------------------------------------------------

def test_composite_score_nonzero_with_injected_acs():
    """After inject_boundary_and_error_acs, the composite spec_quality_score is > 0.

    A 4-AC structural-only spec has composite=0.0 because boundary_coverage=0
    and error_path_coverage=0 force the geometric mean to 0.  Injecting the
    boundary/error ACs must bring the composite above 0.0.
    """
    from bob3.synthesizer import inject_boundary_and_error_acs
    from tools.spec_quality_score import compute

    name = "Synthesizer boundary error coverage"
    description = (
        "Synthesizer MUST guarantee boundary and error-path AC coverage so that "
        "the composite spec_quality_score geometric mean is non-zero."
    )
    structural_only = [
        "File exists: src/bob3/synthesizer.py",
        "Function defined: bob3.synthesizer.parse_criteria_response",
        "Function defined: bob3.synthesizer.inject_boundary_and_error_acs",
        "integration: bob3.orchestrator",
    ]
    augmented = inject_boundary_and_error_acs(structural_only, title=name)
    result = compute(name=name, description=description, acceptance_criteria=augmented)
    assert result.composite > 0.0, (
        f"composite should be > 0.0 after injection; got {result.composite}. "
        f"boundary_coverage={getattr(result, 'boundary_coverage', 'N/A')}, "
        f"error_path_coverage={getattr(result, 'error_path_coverage', 'N/A')}. "
        f"ACs: {augmented}"
    )


# ---------------------------------------------------------------------------
# AC-named test aliases required by feature b3382744-2654-4ff9-95f2-def246beae2a
# ---------------------------------------------------------------------------

def test_inject_boundary_coverage():
    """inject_boundary_and_error_acs injects a boundary-condition AC when missing.

    Alias for the AC 'pytest: tests/test_synthesizer.py::test_inject_boundary_coverage'.
    Structural-only criteria (File exists / Function defined / pytest / integration)
    lack boundary keywords; the injector must add an AC that contains a boundary
    token (empty, zero, minimum, boundary, etc.).
    """
    from bob3.synthesizer import inject_boundary_and_error_acs

    structural_only = [
        "File exists: src/bob3/synthesizer.py",
        "Function defined: bob3.synthesizer.parse_criteria_response",
        "pytest: tests/test_synthesizer.py",
        "integration: bob3.orchestrator",
    ]
    result = inject_boundary_and_error_acs(structural_only, title="Boundary feature")
    assert len(result) > len(structural_only), "Should have injected at least one AC"
    joined = " ".join(result).lower()
    boundary_tokens = ("empty", "null", "zero", "maximum", "minimum", "boundary", "limit")
    assert any(tok in joined for tok in boundary_tokens), (
        f"Expected boundary keyword in injected ACs, got: {result}"
    )


def test_inject_error_path_coverage():
    """inject_boundary_and_error_acs injects an error-path AC when missing.

    Alias for the AC 'pytest: tests/test_synthesizer.py::test_inject_error_path_coverage'.
    Structural-only criteria lack error tokens; the injector must add an AC that
    contains an error token (error, exception, fail, invalid, reject, raise, etc.).
    """
    from bob3.synthesizer import inject_boundary_and_error_acs

    structural_only = [
        "File exists: src/bob3/synthesizer.py",
        "Function defined: bob3.synthesizer.inject_boundary_and_error_acs",
        "pytest: tests/test_synthesizer.py",
        "integration: bob3.orchestrator",
    ]
    result = inject_boundary_and_error_acs(structural_only, title="Error path feature")
    assert len(result) > len(structural_only), "Should have injected at least one AC"
    joined = " ".join(result).lower()
    error_tokens = ("error", "exception", "fail", "invalid", "reject", "raise", "does not", "must not")
    assert any(tok in joined for tok in error_tokens), (
        f"Expected error keyword in injected ACs, got: {result}"
    )


def test_no_duplicate_boundary_error_injection():
    """inject_boundary_and_error_acs must NOT double-inject when coverage already exists.

    Alias for 'pytest: tests/test_synthesizer.py::test_no_duplicate_boundary_error_injection'.
    If a criterion already contains a boundary or error keyword, the injector must
    not add a second one.
    """
    from bob3.synthesizer import inject_boundary_and_error_acs

    boundary_tokens = ("empty", "null", "zero", "maximum", "minimum", "boundary", "limit")
    error_tokens = ("error", "exception", "fail", "invalid", "reject", "raise", "does not", "must not")

    already_covered = [
        "pytest: tests/test_my_feature_boundary.py — empty input returns None (boundary case)",
        "pytest: tests/test_my_feature_error.py — invalid input raises ValueError (error path)",
    ]
    result = inject_boundary_and_error_acs(already_covered, title="My Feature")
    boundary_count = sum(
        1 for ac in result if any(tok in ac.lower() for tok in boundary_tokens)
    )
    error_count = sum(
        1 for ac in result if any(tok in ac.lower() for tok in error_tokens)
    )
    assert boundary_count == 1, (
        f"Should not double-inject boundary AC; got count={boundary_count}: {result}"
    )
    assert error_count == 1, (
        f"Should not double-inject error AC; got count={error_count}: {result}"
    )


def test_composite_score_gate_pass_with_injected_criteria():
    """Composite spec_quality_score passes gate after boundary/error injection.

    Alias for 'pytest: tests/test_synthesizer.py::test_composite_score_gate_pass_with_injected_criteria'.
    A 4-AC structural-only spec has composite=0.0 (geometric mean driven to 0 by
    zero boundary/error coverage); after injection the composite must exceed 0.0
    so the feature can clear the 0.85 gate in subsequent attempts.
    """
    from bob3.synthesizer import inject_boundary_and_error_acs
    from tools.spec_quality_score import compute

    name = "Synthesizer MUST guarantee boundary + error-path AC coverage"
    description = (
        "Synthesizer MUST guarantee boundary and error-path AC coverage AND parse "
        "object-format LLM output — else composite geometric-mean is 0.0 and every "
        "feature falls back."
    )
    structural_only = [
        "File exists: src/bob3/synthesizer.py",
        "Function defined: bob3.synthesizer.parse_criteria_response",
        "Function defined: bob3.synthesizer.inject_boundary_error_criteria",
        "integration: bob3.orchestrator",
    ]
    augmented = inject_boundary_and_error_acs(structural_only, title=name)
    result = compute(name=name, description=description, acceptance_criteria=augmented)
    assert result.composite > 0.0, (
        f"composite must be > 0 after inject_boundary_and_error_acs; "
        f"got {result.composite}. ACs: {augmented}"
    )
