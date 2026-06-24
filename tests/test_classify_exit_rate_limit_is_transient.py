"""F-R7-478: classify_exit — HTTP 429 / rate-limit exits are transient."""

from bob.orchestrator.spawn_retry import classify_exit


def test_429_in_stderr():
    result = classify_exit(exit_code=1, stderr="HTTP 429 Too Many Requests")
    assert result == "transient"


def test_rate_limit_error():
    result = classify_exit(exit_code=1, stderr="RateLimitError: you have exceeded your quota")
    assert result == "transient"


def test_rate_limit_lowercase():
    result = classify_exit(exit_code=1, stderr="rate limit exceeded, please wait")
    assert result == "transient"


def test_too_many_requests():
    result = classify_exit(exit_code=1, stderr="Error: too many requests from this IP")
    assert result == "transient"


def test_rate_hyphen_limit():
    result = classify_exit(exit_code=1, stderr="rate-limit hit, backing off")
    assert result == "transient"
