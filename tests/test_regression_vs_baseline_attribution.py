"""Tests for regression-vs-baseline attribution.

Feature f9355adb-ea38-46f2-8caa-4cf09b4cd274

Verifies that the regression-vs-baseline gate correctly attributes newly-failing
tests to their originating feature rather than to the currently-verifying feature.
This closes the scapegoating defect where sibling-feature broken stubs gate-blocked
unrelated feature verification.
"""

from __future__ import annotations

import pytest

from tests_pass.regression_vs_baseline import attribute_failures_to_owning_feature
from tests_pass.feature_test_map import build_feature_test_map


# ---------------------------------------------------------------------------
# Core attribution: sibling tests are not counted against current feature
# ---------------------------------------------------------------------------

CURRENT_FEATURE = "aaaaaaaa-0000-0000-0000-000000000001"
SIBLING_FEATURE = "bbbbbbbb-0000-0000-0000-000000000002"
ORPHAN_FEATURE = "cccccccc-0000-0000-0000-000000000003"


def test_own_test_is_attributable():
    """A test in tests/<current_feature_id>/ is attributed to current feature."""
    failing = [f"tests/{CURRENT_FEATURE}/test_feature.py::test_one"]
    attr, non_attr = attribute_failures_to_owning_feature(failing, CURRENT_FEATURE)
    assert attr == failing
    assert non_attr == []


def test_sibling_test_is_non_attributable():
    """A test in tests/<sibling_feature_id>/ is NOT attributed to current feature."""
    failing = [f"tests/{SIBLING_FEATURE}/test_sibling.py::test_broken_stub"]
    attr, non_attr = attribute_failures_to_owning_feature(failing, CURRENT_FEATURE)
    assert attr == []
    assert non_attr == failing


def test_orphan_test_is_non_attributable():
    """A test with no UUID in its path is orphan — not attributed to current feature."""
    failing = ["tests/test_contract_grammar_emits_runnable_decorators.py::test_something"]
    attr, non_attr = attribute_failures_to_owning_feature(failing, CURRENT_FEATURE)
    assert attr == []
    assert non_attr == failing


def test_mixed_failing_tests_split_correctly():
    """Own + sibling + orphan tests are split into attributable and non-attributable."""
    own_test = f"tests/{CURRENT_FEATURE}/test_ac_01.py::test_pass"
    sibling_test = f"tests/{SIBLING_FEATURE}/test_stub.py::test_broken"
    orphan_test = "tests/test_f061_create_lesson_from_bug.py::test_lesson"

    attr, non_attr = attribute_failures_to_owning_feature(
        [own_test, sibling_test, orphan_test],
        CURRENT_FEATURE,
    )
    assert attr == [own_test]
    assert sibling_test in non_attr
    assert orphan_test in non_attr
    assert len(non_attr) == 2


def test_empty_failing_tests_returns_empty_lists():
    """No failing tests → both lists are empty."""
    attr, non_attr = attribute_failures_to_owning_feature([], CURRENT_FEATURE)
    assert attr == []
    assert non_attr == []


def test_all_own_tests_all_attributable():
    """Multiple own tests are all attributable."""
    failing = [
        f"tests/{CURRENT_FEATURE}/test_a.py::test_one",
        f"tests/{CURRENT_FEATURE}/test_b.py::test_two",
    ]
    attr, non_attr = attribute_failures_to_owning_feature(failing, CURRENT_FEATURE)
    assert attr == failing
    assert non_attr == []


def test_all_sibling_tests_all_non_attributable():
    """Multiple sibling tests are all non-attributable."""
    failing = [
        f"tests/{SIBLING_FEATURE}/test_x.py::test_a",
        f"tests/{SIBLING_FEATURE}/test_y.py::test_b",
    ]
    attr, non_attr = attribute_failures_to_owning_feature(failing, CURRENT_FEATURE)
    assert attr == []
    assert non_attr == failing


# ---------------------------------------------------------------------------
# Pytest-prefix AC ownership
# ---------------------------------------------------------------------------

def test_pytest_ac_owned_test_attributed_to_declaring_feature():
    """A test declared via 'pytest:' AC is attributed to that feature."""
    declaring_feature_id = "dddddddd-0000-0000-0000-000000000004"
    features = [
        {
            "id": declaring_feature_id,
            "acceptance_criteria": '["pytest: tests/test_special_ac.py::test_owned"]',
            "status": "executing",
        }
    ]
    failing = ["tests/test_special_ac.py::test_owned"]
    attr, non_attr = attribute_failures_to_owning_feature(
        failing, CURRENT_FEATURE, all_features=features
    )
    assert attr == []
    assert non_attr == failing


def test_pytest_ac_own_feature_declaration_is_attributable():
    """A test the CURRENT feature declares via 'pytest:' AC is attributable."""
    features = [
        {
            "id": CURRENT_FEATURE,
            "acceptance_criteria": '["pytest: tests/test_special_current.py::test_mine"]',
            "status": "executing",
        }
    ]
    failing = ["tests/test_special_current.py::test_mine"]
    attr, non_attr = attribute_failures_to_owning_feature(
        failing, CURRENT_FEATURE, all_features=features
    )
    assert attr == failing
    assert non_attr == []


def test_file_level_pytest_ac_covers_any_test_in_file():
    """A file-level 'pytest:' AC (no ::test_name) covers any test in that file."""
    features = [
        {
            "id": CURRENT_FEATURE,
            "acceptance_criteria": '["pytest: tests/test_whole_file.py"]',
            "status": "executing",
        }
    ]
    failing = [
        "tests/test_whole_file.py::test_one",
        "tests/test_whole_file.py::test_two",
    ]
    attr, non_attr = attribute_failures_to_owning_feature(
        failing, CURRENT_FEATURE, all_features=features
    )
    assert attr == failing
    assert non_attr == []


# ---------------------------------------------------------------------------
# Event emission for non-attributable tests
# ---------------------------------------------------------------------------

def test_sibling_test_emits_reattribution_event():
    """A sibling-owned test triggers a reattribution event, not an orphan event."""
    events = []

    def capture_event(event_type, **kwargs):
        events.append((event_type, kwargs))

    failing = [f"tests/{SIBLING_FEATURE}/test_stub.py::test_broken"]
    attribute_failures_to_owning_feature(
        failing,
        CURRENT_FEATURE,
        _emit_event_fn=capture_event,
    )
    assert len(events) == 1
    event_type, payload = events[0]
    assert event_type == "test_regression_reattributed"
    assert payload.get("test_regression_reattributed_to") == SIBLING_FEATURE


def test_orphan_test_emits_orphan_event():
    """An orphan test (no UUID dir, no AC claim) emits an orphan_test_regression event."""
    events = []

    def capture_event(event_type, **kwargs):
        events.append((event_type, kwargs))

    failing = ["tests/test_no_owner.py::test_x"]
    attribute_failures_to_owning_feature(
        failing,
        CURRENT_FEATURE,
        _emit_event_fn=capture_event,
    )
    assert len(events) == 1
    event_type, _payload = events[0]
    assert event_type == "orphan_test_regression"


def test_own_test_emits_no_event():
    """Own tests do not trigger any event — they are simply counted."""
    events = []

    def capture_event(event_type, **kwargs):
        events.append((event_type, kwargs))

    failing = [f"tests/{CURRENT_FEATURE}/test_mine.py::test_one"]
    attribute_failures_to_owning_feature(
        failing,
        CURRENT_FEATURE,
        _emit_event_fn=capture_event,
    )
    assert events == []


# ---------------------------------------------------------------------------
# build_feature_test_map
# ---------------------------------------------------------------------------

def test_build_feature_test_map_empty_features():
    """Empty feature list yields empty ownership map."""
    result = build_feature_test_map([])
    assert result == {}


def test_build_feature_test_map_single_pytest_ac():
    """A feature with a pytest: AC contributes its path to the map."""
    features = [
        {
            "id": "feat-001",
            "acceptance_criteria": '["pytest: tests/test_foo.py::test_bar"]',
        }
    ]
    result = build_feature_test_map(features)
    assert result.get("tests/test_foo.py::test_bar") == "feat-001"


def test_build_feature_test_map_first_writer_wins():
    """When two features claim the same path, first writer wins."""
    features = [
        {"id": "feat-a", "acceptance_criteria": '["pytest: tests/test_shared.py"]'},
        {"id": "feat-b", "acceptance_criteria": '["pytest: tests/test_shared.py"]'},
    ]
    result = build_feature_test_map(features)
    assert result.get("tests/test_shared.py") == "feat-a"


def test_build_feature_test_map_none_raises():
    """None input raises TypeError."""
    with pytest.raises(TypeError):
        build_feature_test_map(None)


def test_build_feature_test_map_non_pytest_ac_ignored():
    """Non-pytest: ACs are not added to the ownership map."""
    features = [
        {
            "id": "feat-c",
            "acceptance_criteria": '["File exists: src/foo.py", "Function defined: foo.bar"]',
        }
    ]
    result = build_feature_test_map(features)
    assert result == {}


# ---------------------------------------------------------------------------
# Integration: the real-world scenario from the feature description
# ---------------------------------------------------------------------------

def test_9b2e1060_scenario_sibling_stubs_do_not_block_current():
    """Reproduces the 9b2e1060 scenario: 7 sibling tests must not gate-block current."""
    current = "9b2e1060-0000-0000-0000-000000000001"
    sibling = "73879589-0000-0000-0000-000000000002"

    # The 7 tests that caused the original demotion — none are in current's subtree
    sibling_failing = [
        f"tests/{sibling}/test_ac_12_pytest_tests_test_contract_grammar_blame.py::test_blame",
        "tests/test_contract_grammar_emits_runnable_decorators.py::test_emit",
        "tests/test_f061_create_lesson_from_bug.py::test_lesson",
    ]

    attr, non_attr = attribute_failures_to_owning_feature(sibling_failing, current)
    assert attr == [], "Current feature must NOT be gate-blocked by sibling stubs"
    assert len(non_attr) == len(sibling_failing)


def test_regression_attribution_import_path():
    """Confirm the canonical import path: tests_pass.regression_vs_baseline."""
    from tests_pass.regression_vs_baseline import attribute_failures_to_owning_feature as fn
    assert callable(fn)
