"""F-R7-478: classify_exit — real implementation failures are 'real_failure'."""

from bob.orchestrator.spawn_retry import classify_exit


def test_clean_exit_is_real_failure_classification():
    """exit_code=0 is classified as real_failure (success path, not retry)."""
    result = classify_exit(exit_code=0, stderr="")
    assert result == "real_failure"


def test_assertion_error_is_real_failure():
    result = classify_exit(
        exit_code=1,
        stderr="AssertionError: expected True but got False",
        work_events=0,
        duration_ms=30000,
    )
    assert result == "real_failure"


def test_import_error_is_real_failure():
    result = classify_exit(
        exit_code=1,
        stderr="ModuleNotFoundError: No module named 'nonexistent_module'",
        work_events=0,
        duration_ms=1000,
    )
    assert result == "real_failure"


def test_syntax_error_is_real_failure():
    result = classify_exit(
        exit_code=1,
        stderr="SyntaxError: invalid syntax at line 42",
        work_events=0,
        duration_ms=500,
    )
    assert result == "real_failure"


def test_empty_stderr_no_work_is_real_failure():
    result = classify_exit(
        exit_code=1,
        stderr="",
        work_events=0,
        duration_ms=5000,
    )
    assert result == "real_failure"
