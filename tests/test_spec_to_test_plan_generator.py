"""Tests for bob3.spec_to_test_plan_generator.

Verifies that the generator produces a human-readable test plan from a feature
spec, covering test scenarios, expected inputs/outputs, edge cases, and
acceptance criteria mapping.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from bob3.spec_to_test_plan_generator import (
    TestScenario,
    TestPlan,
    generate_test_plan,
    parse_acceptance_criteria,
    format_test_plan_markdown,
)


# ---------------------------------------------------------------------------
# parse_acceptance_criteria tests
# ---------------------------------------------------------------------------


class TestParseAcceptanceCriteria:
    def test_parse_json_list_string(self):
        ac = '["File exists: src/bob3/foo.py", "pytest: tests/test_foo.py"]'
        result = parse_acceptance_criteria(ac)
        assert len(result) == 2
        assert "File exists: src/bob3/foo.py" in result
        assert "pytest: tests/test_foo.py" in result

    def test_parse_plain_list(self):
        ac = ["File exists: src/bob3/bar.py", "Function defined: bob3.bar.baz"]
        result = parse_acceptance_criteria(ac)
        assert len(result) == 2
        assert result[0] == "File exists: src/bob3/bar.py"

    def test_parse_single_string(self):
        ac = "File exists: src/bob3/foo.py"
        result = parse_acceptance_criteria(ac)
        assert len(result) == 1
        assert result[0] == "File exists: src/bob3/foo.py"

    def test_parse_none_returns_empty(self):
        result = parse_acceptance_criteria(None)
        assert result == []

    def test_parse_empty_string_returns_empty(self):
        result = parse_acceptance_criteria("")
        assert result == []

    def test_parse_empty_list_returns_empty(self):
        result = parse_acceptance_criteria([])
        assert result == []

    def test_parse_strips_whitespace(self):
        ac = '["  File exists: src/bob3/foo.py  ", "  pytest: tests/test_foo.py  "]'
        result = parse_acceptance_criteria(ac)
        assert result[0] == "File exists: src/bob3/foo.py"
        assert result[1] == "pytest: tests/test_foo.py"


# ---------------------------------------------------------------------------
# TestScenario dataclass tests
# ---------------------------------------------------------------------------


class TestTestScenarioModel:
    def test_basic_construction(self):
        scenario = TestScenario(
            name="Happy path: file exists",
            description="Verify the target file is created at the expected path",
            inputs=["feature with File exists AC"],
            expected_outputs=["File src/bob3/foo.py present"],
            edge_cases=[],
            covers_criteria=["File exists: src/bob3/foo.py"],
        )
        assert scenario.name == "Happy path: file exists"
        assert len(scenario.covers_criteria) == 1
        assert scenario.edge_cases == []

    def test_edge_cases_populated(self):
        scenario = TestScenario(
            name="Edge: empty description",
            description="Feature with no description text",
            inputs=["feature with empty description"],
            expected_outputs=["Still generates a test plan"],
            edge_cases=["description is None", "description is empty string"],
            covers_criteria=[],
        )
        assert len(scenario.edge_cases) == 2

    def test_covers_multiple_criteria(self):
        scenario = TestScenario(
            name="Multi-AC scenario",
            description="Covers both file and pytest criteria",
            inputs=["feature with two ACs"],
            expected_outputs=["file created", "test passes"],
            edge_cases=[],
            covers_criteria=[
                "File exists: src/bob3/foo.py",
                "pytest: tests/test_foo.py",
            ],
        )
        assert len(scenario.covers_criteria) == 2


# ---------------------------------------------------------------------------
# TestPlan dataclass tests
# ---------------------------------------------------------------------------


class TestTestPlanModel:
    def _make_scenario(self, name: str = "Test scenario") -> TestScenario:
        return TestScenario(
            name=name,
            description="A test scenario",
            inputs=["some input"],
            expected_outputs=["some output"],
            edge_cases=[],
            covers_criteria=["File exists: src/bob3/foo.py"],
        )

    def test_basic_construction(self):
        plan = TestPlan(
            feature_name="My feature",
            feature_description="Does something useful",
            acceptance_criteria=["File exists: src/bob3/foo.py"],
            scenarios=[self._make_scenario()],
        )
        assert plan.feature_name == "My feature"
        assert len(plan.scenarios) == 1
        assert len(plan.acceptance_criteria) == 1

    def test_empty_scenarios_allowed(self):
        plan = TestPlan(
            feature_name="Empty feature",
            feature_description="No scenarios",
            acceptance_criteria=[],
            scenarios=[],
        )
        assert plan.scenarios == []

    def test_multiple_scenarios(self):
        scenarios = [self._make_scenario(f"Scenario {i}") for i in range(3)]
        plan = TestPlan(
            feature_name="Multi-scenario feature",
            feature_description="Has many scenarios",
            acceptance_criteria=["File exists: src/bob3/foo.py"],
            scenarios=scenarios,
        )
        assert len(plan.scenarios) == 3


# ---------------------------------------------------------------------------
# generate_test_plan tests
# ---------------------------------------------------------------------------


class TestGenerateTestPlan:
    def _make_feature(self, **kwargs) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "name": "Add utility function",
            "description": "Add a helper function foo() to src/bob3/util.py that returns True.",
            "acceptance_criteria": '["File exists: src/bob3/util.py", "pytest: tests/test_util.py"]',
        }
        defaults.update(kwargs)
        return defaults

    def test_returns_test_plan_object(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        assert isinstance(plan, TestPlan)

    def test_plan_has_feature_name(self):
        feature = self._make_feature(name="My Special Feature")
        plan = generate_test_plan(feature)
        assert plan.feature_name == "My Special Feature"

    def test_plan_has_feature_description(self):
        feature = self._make_feature(description="Does something very specific")
        plan = generate_test_plan(feature)
        assert plan.feature_description == "Does something very specific"

    def test_plan_has_parsed_acceptance_criteria(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        assert len(plan.acceptance_criteria) == 2
        assert "File exists: src/bob3/util.py" in plan.acceptance_criteria
        assert "pytest: tests/test_util.py" in plan.acceptance_criteria

    def test_plan_has_at_least_one_scenario(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        assert len(plan.scenarios) >= 1

    def test_scenarios_have_names(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        for scenario in plan.scenarios:
            assert scenario.name
            assert len(scenario.name) > 0

    def test_scenarios_have_descriptions(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        for scenario in plan.scenarios:
            assert scenario.description
            assert len(scenario.description) > 0

    def test_scenarios_have_inputs(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        for scenario in plan.scenarios:
            assert isinstance(scenario.inputs, list)
            assert len(scenario.inputs) >= 1

    def test_scenarios_have_expected_outputs(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        for scenario in plan.scenarios:
            assert isinstance(scenario.expected_outputs, list)
            assert len(scenario.expected_outputs) >= 1

    def test_scenarios_cover_criteria(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        covered = set()
        for scenario in plan.scenarios:
            covered.update(scenario.covers_criteria)
        # At least one criterion should be covered
        assert len(covered) >= 1

    def test_all_criteria_covered_across_scenarios(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        covered = set()
        for scenario in plan.scenarios:
            covered.update(scenario.covers_criteria)
        for criterion in plan.acceptance_criteria:
            assert criterion in covered, f"Criterion not covered: {criterion}"

    def test_edge_case_no_description(self):
        feature = self._make_feature(description=None)
        plan = generate_test_plan(feature)
        assert isinstance(plan, TestPlan)
        assert len(plan.scenarios) >= 1

    def test_edge_case_empty_acceptance_criteria(self):
        feature = self._make_feature(acceptance_criteria=None)
        plan = generate_test_plan(feature)
        assert isinstance(plan, TestPlan)
        assert plan.acceptance_criteria == []

    def test_edge_case_plain_list_criteria(self):
        feature = self._make_feature(
            acceptance_criteria=["File exists: src/bob3/foo.py", "pytest: tests/test_foo.py"]
        )
        plan = generate_test_plan(feature)
        assert len(plan.acceptance_criteria) == 2

    def test_scenarios_include_edge_cases_field(self):
        feature = self._make_feature()
        plan = generate_test_plan(feature)
        for scenario in plan.scenarios:
            assert isinstance(scenario.edge_cases, list)

    def test_file_exists_criterion_generates_scenario(self):
        feature = self._make_feature(
            acceptance_criteria='["File exists: src/bob3/mymodule.py"]'
        )
        plan = generate_test_plan(feature)
        scenario_names = [s.name.lower() for s in plan.scenarios]
        # Should have scenario related to file existence
        assert any("file" in name or "exist" in name or "mymodule" in name for name in scenario_names)

    def test_pytest_criterion_generates_scenario(self):
        feature = self._make_feature(
            acceptance_criteria='["pytest: tests/test_mymodule.py"]'
        )
        plan = generate_test_plan(feature)
        scenario_names = [s.name.lower() for s in plan.scenarios]
        assert any("test" in name or "pytest" in name or "mymodule" in name for name in scenario_names)

    def test_function_defined_criterion_generates_scenario(self):
        feature = self._make_feature(
            acceptance_criteria='["Function defined: bob3.mymodule.my_func"]'
        )
        plan = generate_test_plan(feature)
        covered = set()
        for scenario in plan.scenarios:
            covered.update(scenario.covers_criteria)
        assert "Function defined: bob3.mymodule.my_func" in covered

    def test_multiple_criteria_generate_multiple_scenarios(self):
        feature = self._make_feature(
            acceptance_criteria='["File exists: src/bob3/a.py", "pytest: tests/test_a.py", "Function defined: bob3.a.foo"]'
        )
        plan = generate_test_plan(feature)
        # 3 criteria should produce at least 2 scenarios (possibly merged)
        assert len(plan.scenarios) >= 2


# ---------------------------------------------------------------------------
# format_test_plan_markdown tests
# ---------------------------------------------------------------------------


class TestFormatTestPlanMarkdown:
    def _make_plan(self) -> TestPlan:
        scenario = TestScenario(
            name="Happy path: create file",
            description="Verify the module file is created",
            inputs=["Feature with File exists AC"],
            expected_outputs=["src/bob3/foo.py exists on disk"],
            edge_cases=["File already exists (idempotent)", "Parent dir missing"],
            covers_criteria=["File exists: src/bob3/foo.py"],
        )
        return TestPlan(
            feature_name="Add foo module",
            feature_description="Creates src/bob3/foo.py with helper functions",
            acceptance_criteria=["File exists: src/bob3/foo.py", "pytest: tests/test_foo.py"],
            scenarios=[scenario],
        )

    def test_returns_string(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert isinstance(md, str)

    def test_contains_feature_name(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "Add foo module" in md

    def test_contains_feature_description(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "Creates src/bob3/foo.py" in md

    def test_contains_acceptance_criteria(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "File exists: src/bob3/foo.py" in md
        assert "pytest: tests/test_foo.py" in md

    def test_contains_scenario_name(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "Happy path: create file" in md

    def test_contains_scenario_description(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "Verify the module file is created" in md

    def test_contains_expected_outputs(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "src/bob3/foo.py exists on disk" in md

    def test_contains_edge_cases(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "File already exists" in md

    def test_contains_covers_criteria(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        # The scenario coverage mapping should appear
        assert "File exists: src/bob3/foo.py" in md

    def test_markdown_has_headers(self):
        plan = self._make_plan()
        md = format_test_plan_markdown(plan)
        assert "#" in md

    def test_empty_plan_returns_string(self):
        plan = TestPlan(
            feature_name="Empty",
            feature_description="",
            acceptance_criteria=[],
            scenarios=[],
        )
        md = format_test_plan_markdown(plan)
        assert isinstance(md, str)
        assert "Empty" in md
