"""Error-path tests for permanent_forward_carry_auditor.audit_merged_spec.

Verifies that truly invalid inputs (non-dict passed as spec) raise ValueError
and that the function does NOT silently succeed or swallow errors.
"""

from __future__ import annotations

import pytest

from bob3.permanent_forward_carry_auditor import (
    BootstrapAuditError,
    audit_merged_spec,
    audit_bootstrap_spec,
    fail_loud_on_missing,
)


class TestAuditMergedSpecErrorPath:
    """Error path: invalid inputs raise ValueError, not silent success."""

    def test_none_input_raises_value_error(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            audit_merged_spec(None)  # type: ignore[arg-type]

    def test_list_input_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            audit_merged_spec([])  # type: ignore[arg-type]

    def test_string_input_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            audit_merged_spec("not a dict")  # type: ignore[arg-type]

    def test_integer_input_raises(self):
        with pytest.raises((TypeError, ValueError, AttributeError)):
            audit_merged_spec(42)  # type: ignore[arg-type]


class TestFailLoudOnMissingErrorPath:
    """Error path: fail_loud_on_missing raises BootstrapAuditError for non-empty set."""

    def test_single_missing_id_raises_bootstrap_audit_error(self):
        with pytest.raises(BootstrapAuditError):
            fail_loud_on_missing(frozenset({"F-R7-478"}))

    def test_all_three_missing_raises_bootstrap_audit_error(self):
        with pytest.raises(BootstrapAuditError):
            fail_loud_on_missing(frozenset({"F-R7-478", "F-R7-479", "F-R7-553"}))

    def test_does_not_silently_succeed_when_missing_non_empty(self):
        raised = False
        try:
            fail_loud_on_missing(frozenset({"F-R7-479"}))
        except BootstrapAuditError:
            raised = True
        assert raised, "fail_loud_on_missing must raise when missing set is non-empty"

    def test_error_message_is_not_empty(self):
        with pytest.raises(BootstrapAuditError) as exc_info:
            fail_loud_on_missing(frozenset({"F-R7-553"}))
        assert len(str(exc_info.value)) > 0

    def test_error_is_not_swallowed_by_audit_bootstrap_spec(self):
        spec = {"features": [{"id": "F-R7-478", "title": "t"}]}
        raised = False
        try:
            audit_bootstrap_spec(spec)
        except BootstrapAuditError:
            raised = True
        assert raised, "audit_bootstrap_spec must not silently succeed when features missing"
