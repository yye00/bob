"""Tests: check_spec must raise an error on invalid input and reject the spec."""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.spec_quality.integration_reachability import (
    UnreachableIntegrationError,
    check_spec,
    raises_on_unreachable,
)


def test_check_spec_rejects_invalid_integration_target(tmp_path):
    """check_spec treats a completely invalid/unreachable module as a failed AC."""
    features = [
        {"name": "MyFeature", "acceptance_criteria": ["integration: invalid.unreachable.xyz123"]}
    ]
    result = check_spec(features, workspace=tmp_path)
    assert result.passed is False
    assert len(result.issues) == 1
    assert result.issues[0].missing_module == "invalid.unreachable.xyz123"


def test_raises_on_unreachable_raises_for_invalid_module(tmp_path):
    """raises_on_unreachable raises UnreachableIntegrationError for invalid modules."""
    with pytest.raises(UnreachableIntegrationError) as exc_info:
        raises_on_unreachable("completely.invalid.module.xyz", workspace=tmp_path)
    err = exc_info.value
    assert err.missing_module == "completely.invalid.module.xyz"
    assert isinstance(err, UnreachableIntegrationError)


def test_check_spec_rejects_spec_with_no_reachable_targets(tmp_path):
    """A spec where ALL integration targets are unreachable is fully rejected."""
    features = [
        {"name": "F1", "acceptance_criteria": ["integration: no.module.here"]},
        {"name": "F2", "acceptance_criteria": ["integration: also.missing"]},
    ]
    result = check_spec(features, workspace=tmp_path)
    assert result.passed is False
    missing = {i.missing_module for i in result.issues}
    assert "no.module.here" in missing
    assert "also.missing" in missing


def test_unreachable_integration_error_is_exception():
    """UnreachableIntegrationError is a proper Exception subclass."""
    err = UnreachableIntegrationError("bad.module")
    assert isinstance(err, Exception)
    assert "bad.module" in str(err)


def test_check_spec_format_report_names_invalid_module(tmp_path):
    """format_report includes the invalid module name in its output."""
    features = [{"name": "F", "acceptance_criteria": ["integration: my.bad.module"]}]
    result = check_spec(features, workspace=tmp_path)
    report = result.format_report()
    assert "my.bad.module" in report
    assert "FAILED" in report
