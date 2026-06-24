"""F-R7-478: classify_exit — mid-work crash is 'mid_work_crash', not transient."""

from bob.orchestrator.spawn_retry import classify_exit


def test_work_events_nonzero_is_mid_work_crash():
    result = classify_exit(
        exit_code=1,
        stderr="Fatal error in message reader",
        work_events=5,
        duration_ms=45000,
    )
    assert result == "mid_work_crash"


def test_work_events_with_shutdown_marker():
    result = classify_exit(
        exit_code=1,
        stderr="Fatal error in message reader: stream closed",
        work_events=3,
        duration_ms=12000,
    )
    assert result == "mid_work_crash"


def test_shutdown_marker_without_work_events_is_mid_work_crash():
    """MessageReader in stderr without work events still suggests mid-work."""
    result = classify_exit(
        exit_code=1,
        stderr="messagereader crashed unexpectedly",
        work_events=0,
        duration_ms=5000,
    )
    assert result == "mid_work_crash"


def test_duration_ms_zero_with_work_events_is_transient():
    """AC: work_events>0 AND duration_ms==0 → JSONL serialisation race → transient."""
    result = classify_exit(
        exit_code=1,
        stderr="",
        work_events=3,
        duration_ms=0,
    )
    assert result == "transient"
