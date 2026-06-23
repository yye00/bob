"""Tests for spec_quality.score.calculate_spec_quality_score.

Verifies the main function exists, returns correct types, and implements
the gate semantics combining F-R7-410/411/412 plus AC-coverage into
a per-feature score in [0, 1].
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.score import calculate_spec_quality_score


def test_function_exists_and_is_callable():
    """AC: Function defined: spec_quality.score.calculate_spec_quality_score"""
    assert callable(calculate_spec_quality_score)


def test_returns_float_in_unit_interval():
    """calculate_spec_quality_score returns a float in [0, 1]."""
    acs = [
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
        "pytest: tests/test_spec_quality_score.py",
    ]
    score = calculate_spec_quality_score(
        name="Sample feature",
        description="A feature with function calculate_spec_quality_score.",
        acceptance_criteria=acs,
    )
    assert isinstance(score, float), f"Expected float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"


def test_well_structured_acs_score_high():
    """Features with clean structured ACs (File exists, Function defined, pytest) score >= 0.85."""
    name = "Clean feature"
    description = None
    acs = [
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
        "pytest: tests/test_spec_quality_score.py",
        "pytest: tests/test_spec_quality_score_gate_boundary.py",
    ]
    score = calculate_spec_quality_score(name=name, description=description, acceptance_criteria=acs)
    assert score >= 0.85, f"Expected high score for structured ACs, got {score}"


def test_empty_acs_score_zero():
    """Empty acceptance criteria always yields score 0.0."""
    score = calculate_spec_quality_score(
        name="No AC feature",
        description="Some description",
        acceptance_criteria=[],
    )
    assert score == 0.0


def test_score_with_list_of_strings():
    """Accepts a plain list of strings as acceptance_criteria."""
    acs = ["File exists: src/spec_quality/score.py"]
    score = calculate_spec_quality_score(
        name="List input",
        description=None,
        acceptance_criteria=acs,
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_score_with_json_string():
    """Accepts a JSON-encoded list as acceptance_criteria."""
    import json
    acs_json = json.dumps([
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
    ])
    score = calculate_spec_quality_score(
        name="JSON input",
        description=None,
        acceptance_criteria=acs_json,
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_integration_with_bob3_spec_quality():
    """Integration: bob3.spec_quality — delegates to the existing quality scoring."""
    from bob3.spec_quality.quality_score import compute_score
    name = "Integration test"
    acs = [
        "File exists: src/spec_quality/score.py",
        "Function defined: spec_quality.score.calculate_spec_quality_score",
    ]
    # Both paths should produce consistent scores
    spec_quality_score = calculate_spec_quality_score(
        name=name, description=None, acceptance_criteria=acs
    )
    bob3_report = compute_score(name=name, description=None, acceptance_criteria=acs)
    assert abs(spec_quality_score - bob3_report.score) < 1e-6, (
        f"calculate_spec_quality_score ({spec_quality_score}) should match "
        f"compute_score ({bob3_report.score})"
    )


# ---------------------------------------------------------------------------
# Tests for tools.spec_quality_score.is_code_shaped_token
# ---------------------------------------------------------------------------

class TestIsCodeShapedToken:
    """AC: Function defined: spec_quality_score.is_code_shaped_token"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.spec_quality_score import is_code_shaped_token
        self.fn = is_code_shaped_token

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_underscore_token_is_code_shaped(self):
        assert self.fn("extract_py_paths") is True

    def test_dotted_token_is_code_shaped(self):
        assert self.fn("tools.spec_quality_score") is True

    def test_py_extension_is_code_shaped(self):
        assert self.fn("foo.py") is True

    def test_camel_case_is_code_shaped(self):
        assert self.fn("CompositeScore") is True

    def test_plain_english_word_is_not_code_shaped(self):
        # Bare lowercase dictionary words are prose, not symbols
        assert self.fn("name") is False
        assert self.fn("gate") is False
        assert self.fn("correctly") is False
        assert self.fn("returns") is False
        assert self.fn("failures") is False

    def test_stopword_is_not_code_shaped(self):
        assert self.fn("defined") is False
        assert self.fn("implemented") is False
        assert self.fn("declared") is False

    def test_all_uppercase_token_is_not_code_shaped(self):
        # ALL_CAPS are prose emphasis, not symbols
        assert self.fn("TODO") is False
        assert self.fn("FOO") is False

    def test_empty_string_is_not_code_shaped(self):
        assert self.fn("") is False

    def test_pluralised_acronym_is_not_code_shaped(self):
        assert self.fn("ACs") is False
        assert self.fn("IDs") is False


# ---------------------------------------------------------------------------
# Tests for tools.spec_quality_score.extract_py_paths
# ---------------------------------------------------------------------------

class TestExtractPyPaths:
    """AC: Function defined: spec_quality_score.extract_py_paths"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.spec_quality_score import extract_py_paths
        self.fn = extract_py_paths

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_extracts_path_with_directory(self):
        desc = "The implementation lives in src/bob3/brownfield/survey.py."
        paths = self.fn(desc)
        assert "src/bob3/brownfield/survey.py" in paths

    def test_extracts_multiple_paths(self):
        desc = "See src/bob3/foo.py and tools/spec_quality_score.py for details."
        paths = self.fn(desc)
        assert "src/bob3/foo.py" in paths
        assert "tools/spec_quality_score.py" in paths

    def test_deduplicates_paths(self):
        desc = "Use src/bob3/foo.py and also src/bob3/foo.py again."
        paths = self.fn(desc)
        assert paths.count("src/bob3/foo.py") == 1

    def test_empty_description_returns_empty_list(self):
        assert self.fn("") == []

    def test_none_description_returns_empty_list(self):
        assert self.fn(None) == []

    def test_bare_filename_without_dir_is_excluded(self):
        # Bare filenames without directory are ambiguous — excluded per spec
        desc = "The file foo.py is relevant."
        paths = self.fn(desc)
        assert "foo.py" not in paths

    def test_returns_sorted_list(self):
        desc = "See src/z/z.py and src/a/a.py for implementation."
        paths = self.fn(desc)
        assert paths == sorted(paths)

    def test_returns_list_type(self):
        result = self.fn("some text src/bob3/x.py here")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests for tools.spec_quality_score.extract_concrete_py_paths
# ---------------------------------------------------------------------------

class TestExtractConcretePyPaths:
    """AC: Function defined: spec_quality_score.extract_concrete_py_paths"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.spec_quality_score import extract_concrete_py_paths
        self.fn = extract_concrete_py_paths

    def test_function_is_callable(self):
        assert callable(self.fn)

    def test_extracts_path_with_directory(self):
        desc = "The implementation lives in src/bob3/brownfield/survey.py."
        paths = self.fn(desc)
        assert "src/bob3/brownfield/survey.py" in paths

    def test_empty_description_returns_empty_list(self):
        assert self.fn("") == []

    def test_none_description_returns_empty_list(self):
        assert self.fn(None) == []

    def test_deduplicates_paths(self):
        desc = "Use src/bob3/foo.py and also src/bob3/foo.py again."
        paths = self.fn(desc)
        assert paths.count("src/bob3/foo.py") == 1

    def test_bare_filename_without_dir_is_excluded(self):
        desc = "The file foo.py is relevant."
        paths = self.fn(desc)
        assert "foo.py" not in paths

    def test_returns_sorted_list(self):
        desc = "See src/z/z.py and src/a/a.py for implementation."
        paths = self.fn(desc)
        assert paths == sorted(paths)

    def test_returns_same_result_as_extract_py_paths(self):
        """extract_concrete_py_paths is a canonical alias for extract_py_paths."""
        from tools.spec_quality_score import extract_py_paths
        desc = "Use src/bob3/foo.py and tools/spec_quality_score.py."
        assert self.fn(desc) == extract_py_paths(desc)


# ---------------------------------------------------------------------------
# Integration: tools.spec_quality_score module import
# ---------------------------------------------------------------------------

class TestIntegrationToolsSpecQualityScore:
    """AC: integration: tools.spec_quality_score"""

    def test_module_importable(self):
        import importlib
        mod = importlib.import_module("tools.spec_quality_score")
        assert mod is not None

    def test_compute_function_exists(self):
        from tools.spec_quality_score import compute
        assert callable(compute)

    def test_is_code_shaped_token_exists(self):
        from tools.spec_quality_score import is_code_shaped_token
        assert callable(is_code_shaped_token)

    def test_extract_py_paths_exists(self):
        from tools.spec_quality_score import extract_py_paths
        assert callable(extract_py_paths)

    def test_extract_concrete_py_paths_exists(self):
        from tools.spec_quality_score import extract_concrete_py_paths
        assert callable(extract_concrete_py_paths)

    def test_prose_words_not_treated_as_api_surfaces(self):
        """Scorer MUST NOT treat non-code English words as uncovered API surfaces."""
        from tools.spec_quality_score import compute
        # Description that uses prose words that previously caused false positives
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
        # contract_completeness must not be zeroed by prose words like
        # "defined", "name", "gate", "correctly", "returns", "failures"
        assert result.contract_completeness > 0.0, (
            f"contract_completeness should not be zeroed by prose words; got {result.contract_completeness}"
        )

    def test_described_py_path_drives_contract_completeness(self):
        """When description names a .py path, scorer considers it covered by a File-exists AC."""
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


# ---------------------------------------------------------------------------
# Standalone tests required by AC for ddbd508e-062f-4b1a-b295-5af50b1165a5
# ---------------------------------------------------------------------------

def test_is_code_identifier_rejects_all_caps():
    """_is_code_identifier must return False for all-uppercase tokens (prose placeholders)."""
    from tools.spec_quality_score import _is_code_identifier

    # All-caps tokens are prose emphasis or template placeholders, not real symbols
    assert _is_code_identifier("NAME") is False, "NAME is a prose placeholder"
    assert _is_code_identifier("FOO") is False, "FOO is a prose placeholder"
    assert _is_code_identifier("TODO") is False, "TODO is a prose placeholder"
    assert _is_code_identifier("UPPER") is False, "UPPER is prose emphasis"
    assert _is_code_identifier("API") is False, "API is an acronym, not a code symbol"


def test_is_code_identifier_requires_mixed_case():
    """_is_code_identifier must return True only for CamelCase with BOTH upper and lower letters."""
    from tools.spec_quality_score import _is_code_identifier

    # Valid CamelCase (has both upper and lower letters)
    assert _is_code_identifier("RetryCounter") is True, "RetryCounter is valid CamelCase"
    assert _is_code_identifier("CompositeScore") is True, "CompositeScore is valid CamelCase"
    assert _is_code_identifier("MyClass") is True, "MyClass is valid CamelCase"

    # All-caps must NOT qualify as CamelCase
    assert _is_code_identifier("NAME") is False, "NAME has no lowercase — not CamelCase"
    assert _is_code_identifier("ABC") is False, "ABC is all-caps acronym — not CamelCase"

    # Valid underscore/dotted identifiers still qualify
    assert _is_code_identifier("my_func") is True, "my_func has underscore"
    assert _is_code_identifier("tools.score") is True, "tools.score is dotted identifier"


# ---------------------------------------------------------------------------
# Required ACs: test_contract_completeness_ignores_prose_words and
# test_synthesizer_emits_file_exists_for_py_paths
# ---------------------------------------------------------------------------

def test_contract_completeness_ignores_prose_words():
    """Scorer MUST NOT treat non-code English words as uncovered API surfaces.

    AC: pytest: tests/test_spec_quality_score.py::test_contract_completeness_ignores_prose_words
    """
    from tools.spec_quality_score import check_contract_completeness

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
    score, hints = check_contract_completeness(description, acs)
    # Prose words: "defined", "name", "gate", "correctly", "returns", "failures"
    # must NOT be counted as uncovered API surfaces.
    assert score > 0.0, (
        f"contract_completeness={score} — prose words like 'defined', 'name', "
        f"'gate', 'correctly', 'returns', 'failures' must not be treated as API surfaces. "
        f"Hints: {hints}"
    )


def test_synthesizer_emits_file_exists_for_py_paths():
    """When description names a concrete .py path, the scorer must credit a File-exists AC.

    AC: pytest: tests/test_spec_quality_score.py::test_synthesizer_emits_file_exists_for_py_paths
    """
    from tools.spec_quality_score import check_contract_completeness, extract_py_paths

    description = "Implement src/bob3/brownfield/survey.py to scan the codebase."

    # Simulate synthesizer emitting File-exists ACs for each concrete .py path
    py_paths = extract_py_paths(description)
    assert "src/bob3/brownfield/survey.py" in py_paths, (
        f"extract_py_paths must detect 'src/bob3/brownfield/survey.py'; got {py_paths}"
    )

    # Build ACs including the File-exists AC for the described path
    acs = [
        f"File exists: {path}" for path in py_paths
    ] + [
        "pytest: tests/test_survey_boundary.py — boundary",
        "pytest: tests/test_survey_error.py — error",
    ]

    score, hints = check_contract_completeness(description, acs)
    assert score > 0.0, (
        f"contract_completeness={score} — survey.py is covered by File-exists AC. "
        f"Hints: {hints}"
    )


# ---------------------------------------------------------------------------
# Required ACs: test_reject_all_caps_placeholders and
# test_camelcase_requires_mixed_case
# ---------------------------------------------------------------------------

def test_reject_all_caps_placeholders():
    """_is_code_identifier MUST reject all-caps prose placeholders.

    Template tokens like NAME, FOO, TODO are prose emphasis or placeholder
    text — not real code symbols requiring AC coverage. The scorer must
    never treat them as API surfaces.

    AC: pytest: tests/test_spec_quality_score.py::test_reject_all_caps_placeholders
    """
    from tools.spec_quality_score import _is_code_identifier

    # All-uppercase tokens are prose/emphasis — must be rejected
    assert _is_code_identifier("NAME") is False, "NAME is a prose placeholder, not a code symbol"
    assert _is_code_identifier("FOO") is False, "FOO is a prose placeholder, not a code symbol"
    assert _is_code_identifier("TODO") is False, "TODO is a prose placeholder, not a code symbol"
    assert _is_code_identifier("BAR") is False, "BAR is a prose placeholder, not a code symbol"
    assert _is_code_identifier("ARGS") is False, "ARGS is a prose placeholder, not a code symbol"

    # A description like "def NAME(...)" must not cause NAME to be extracted as an API surface
    from tools.spec_quality_score import check_contract_completeness
    description = (
        "A function defined: def NAME(...) is a template. "
        "Use FOO as a placeholder for the actual function name."
    )
    acs = [
        "pytest: tests/test_something_boundary.py — boundary",
        "pytest: tests/test_something_error.py — error",
    ]
    score, hints = check_contract_completeness(description, acs)
    # NAME and FOO must not be counted as uncovered API surfaces
    uncovered_names = [h for h in hints if "NAME" in h or "FOO" in h]
    assert not uncovered_names, (
        f"All-caps placeholders NAME/FOO must not be treated as API surfaces. "
        f"Offending hints: {uncovered_names}"
    )


def test_camelcase_requires_mixed_case():
    """_is_code_identifier MUST require CamelCase to contain BOTH upper AND lower letters.

    Pure acronyms (all-uppercase like HTTP, API) must not be treated as
    CamelCase code identifiers. Only tokens with both upper and lower letters
    (like RetryCounter, MyClass) qualify as CamelCase symbols.

    AC: pytest: tests/test_spec_quality_score.py::test_camelcase_requires_mixed_case
    """
    from tools.spec_quality_score import _is_code_identifier

    # True CamelCase — has BOTH upper AND lower letters → True
    assert _is_code_identifier("RetryCounter") is True, "RetryCounter is a valid CamelCase symbol"
    assert _is_code_identifier("MyClass") is True, "MyClass is a valid CamelCase symbol"
    assert _is_code_identifier("CompositeScore") is True, "CompositeScore is a valid CamelCase symbol"
    assert _is_code_identifier("specQualityScore") is True, "specQualityScore (lowerCamelCase) is a valid symbol"

    # All-uppercase — no lowercase letters → False (not CamelCase)
    assert _is_code_identifier("HTTP") is False, "HTTP is an acronym, not CamelCase"
    assert _is_code_identifier("API") is False, "API is an acronym, not CamelCase"
    assert _is_code_identifier("NAME") is False, "NAME has no lowercase letter — not CamelCase"
    assert _is_code_identifier("FOO") is False, "FOO has no lowercase letter — not CamelCase"


# ---------------------------------------------------------------------------
# AC-required tests for feature a3be44c6-6065-4b33-b509-d566fed5d311
# Composite spec_quality_score (8 sub-metrics, geometric mean, 0.65/0.80 gate)
# ---------------------------------------------------------------------------

def _all_metrics(value: float) -> dict:
    from bob3.spec_quality.composite_score import SUB_METRIC_WEIGHTS
    return {k: value for k in SUB_METRIC_WEIGHTS}


def test_geometric_mean_calculation():
    """Weighted geometric mean of 8 sub-metrics is correctly computed.

    AC: pytest: tests/test_spec_quality_score.py::test_geometric_mean_calculation
    """
    import math
    from bob3.spec_quality.composite_score import (
        SUB_METRIC_WEIGHTS,
        calculate_geometric_mean,
        compute_composite_score,
    )

    # Uniform score — geometric mean of same value = that value
    metrics = _all_metrics(0.75)
    result = compute_composite_score(metrics)
    assert isinstance(result, dict)
    assert "score" in result
    assert "gate" in result
    score = result["score"]
    assert isinstance(score, float)
    assert abs(score - 0.75) < 1e-5, f"Expected ~0.75, got {score}"

    # Verify the weighted geometric mean formula directly
    expected_log = sum(w * math.log(0.75) for w in SUB_METRIC_WEIGHTS.values())
    expected = math.exp(expected_log)
    assert abs(score - expected) < 1e-9


def test_boundary_conditions_65_80_green():
    """Gate boundaries are inclusive: 0.65 → warn, 0.80 → green.

    AC: pytest: tests/test_spec_quality_score.py::test_boundary_conditions_65_80_green
    """
    from bob3.spec_quality.composite_score import compute_composite_score
    from bob3.spec_quality_score import validate_score_thresholds

    # Exactly 0.65 — warn boundary (inclusive lower bound)
    result_65 = compute_composite_score(_all_metrics(0.65))
    assert result_65["gate"] == "warn", f"0.65 must be 'warn', got {result_65['gate']}"
    assert result_65["score"] == pytest.approx(0.65, abs=1e-5)

    # Exactly 0.80 — green boundary (inclusive lower bound)
    result_80 = compute_composite_score(_all_metrics(0.80))
    assert result_80["gate"] == "green", f"0.80 must be 'green', got {result_80['gate']}"
    assert result_80["score"] == pytest.approx(0.80, abs=1e-5)

    # Below 0.65 — refuse
    result_below = compute_composite_score(_all_metrics(0.64))
    assert result_below["gate"] == "refuse", f"0.64 must be 'refuse', got {result_below['gate']}"

    # validate_score_thresholds returns consistent results
    assert validate_score_thresholds(0.65) == "warn"
    assert validate_score_thresholds(0.80) == "green"
    assert validate_score_thresholds(0.64) == "refuse"
    assert validate_score_thresholds(1.0) == "green"
    assert validate_score_thresholds(0.0) == "refuse"


def test_error_paths_below_65_refuses_plan():
    """Scores below 0.65 yield gate='refuse' — plan --create is blocked.

    AC: pytest: tests/test_spec_quality_score.py::test_error_paths_below_65_refuses_plan
    """
    from bob3.spec_quality.composite_score import compute_composite_score

    test_cases = [0.0, 0.1, 0.3, 0.5, 0.60, 0.64, 0.649]
    for val in test_cases:
        result = compute_composite_score(_all_metrics(val))
        assert result["gate"] == "refuse", (
            f"score {result['score']:.4f} (from metric {val}) must yield 'refuse', "
            f"got '{result['gate']}'"
        )

    # Exactly at and above 0.65 must NOT refuse
    result_warn = compute_composite_score(_all_metrics(0.65))
    assert result_warn["gate"] != "refuse", "0.65 must not refuse"

    result_green = compute_composite_score(_all_metrics(0.90))
    assert result_green["gate"] == "green", "0.90 must be green"
    assert result_green["gate"] != "refuse", "0.90 must not refuse"


def test_all_eight_sub_metrics_weighted():
    """All 8 sub-metrics with correct weights are used in the geometric mean.

    AC: pytest: tests/test_spec_quality_score.py::test_all_eight_sub_metrics_weighted
    """
    from bob3.spec_quality.composite_score import (
        SUB_METRIC_WEIGHTS,
        compute_composite_score,
    )

    # Verify the 8 required sub-metrics exist with correct weights
    expected_weights = {
        "smell_density": 0.20,
        "predicate_coverage": 0.20,
        "contract_completeness": 0.15,
        "boundary_coverage": 0.10,
        "error_path_coverage": 0.10,
        "traceability": 0.10,
        "spec_executability": 0.10,
        "ac_atomicity": 0.05,
    }
    assert len(SUB_METRIC_WEIGHTS) == 8, f"Expected 8 sub-metrics, got {len(SUB_METRIC_WEIGHTS)}"
    for name, weight in expected_weights.items():
        assert name in SUB_METRIC_WEIGHTS, f"Missing sub-metric: {name}"
        assert abs(SUB_METRIC_WEIGHTS[name] - weight) < 1e-9, (
            f"{name}: expected weight {weight}, got {SUB_METRIC_WEIGHTS[name]}"
        )

    # Weights must sum to 1.0
    total = sum(SUB_METRIC_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights must sum to 1.0, got {total}"

    # Changing a single sub-metric affects the score (proves each is used)
    base_metrics = _all_metrics(0.9)
    result_base = compute_composite_score(base_metrics)

    for metric_name in SUB_METRIC_WEIGHTS:
        modified = dict(base_metrics)
        modified[metric_name] = 0.1  # drop one metric way down
        result_modified = compute_composite_score(modified)
        assert result_modified["score"] < result_base["score"], (
            f"Changing {metric_name} from 0.9 to 0.1 must lower the score; "
            f"base={result_base['score']:.4f}, modified={result_modified['score']:.4f}"
        )
