"""Error-path tests for bob72.preflight.

Invalid input raises ValueError and the function does not silently succeed.
"""

import pytest

from bob72.preflight import (
    MissingDependencyError,
    discover_workaround,
    probe_dependencies,
    run_preflight,
)


class TestProbeDependenciesErrorPath:
    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies(None)  # type: ignore[arg-type]

    def test_string_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies("not a list")  # type: ignore[arg-type]

    def test_dict_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies({"key": "value"})  # type: ignore[arg-type]

    def test_integer_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            probe_dependencies(42)  # type: ignore[arg-type]


class TestDiscoverWorkaroundErrorPath:
    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            discover_workaround(None)  # type: ignore[arg-type]

    def test_string_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            discover_workaround("not a dict")  # type: ignore[arg-type]

    def test_list_input_raises_value_error(self):
        with pytest.raises(ValueError, match="probe_result must be a dict"):
            discover_workaround([])  # type: ignore[arg-type]

    def test_missing_present_key_raises_value_error(self):
        with pytest.raises(ValueError, match="must have 'dep' and 'present' keys"):
            discover_workaround({"dep": {"kind": "cli", "name": "git"}})

    def test_missing_dep_key_raises_value_error(self):
        with pytest.raises(ValueError, match="must have 'dep' and 'present' keys"):
            discover_workaround({"present": False})

    def test_empty_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            discover_workaround({})


class TestRunPreflightErrorPath:
    def test_none_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            run_preflight(None)  # type: ignore[arg-type]

    def test_string_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            run_preflight("not a list")  # type: ignore[arg-type]

    def test_integer_input_raises_value_error(self):
        with pytest.raises(ValueError, match="ac_list must be a list"):
            run_preflight(42)  # type: ignore[arg-type]

    def test_missing_high_risk_dep_raises_missing_dep_error(self):
        ac = "command: __nonexistent_cli_guaranteed_absent_xyz987__"
        with pytest.raises(MissingDependencyError):
            run_preflight([ac])

    def test_missing_dep_error_is_value_error_subclass(self):
        ac = "command: __nonexistent_cli_guaranteed_absent_xyz987__"
        with pytest.raises(ValueError):
            run_preflight([ac])

    def test_error_message_names_missing_dep(self):
        dep_name = "__totally_absent_cli_name_xyz_abc_987__"
        ac = f"command: {dep_name}"
        with pytest.raises(MissingDependencyError) as exc_info:
            run_preflight([ac])
        assert dep_name in str(exc_info.value)

    def test_does_not_silently_succeed_on_high_risk_missing(self):
        ac = "command: __nonexistent_cli_xyz987__"
        raised = False
        try:
            run_preflight([ac])
        except MissingDependencyError:
            raised = True
        assert raised, "run_preflight must raise, not silently succeed on high-risk missing dep"
