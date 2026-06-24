"""F-R7-478: classify_exit — network blip exits are transient."""

from bob.orchestrator.spawn_retry import classify_exit


def test_econnreset_is_transient():
    result = classify_exit(exit_code=1, stderr="Error: ECONNRESET: socket hang up")
    assert result == "transient"


def test_etimedout_is_transient():
    result = classify_exit(exit_code=1, stderr="Error: ETIMEDOUT connect timed out")
    assert result == "transient"


def test_connection_reset_by_peer():
    result = classify_exit(exit_code=1, stderr="Connection reset by peer")
    assert result == "transient"


def test_connection_timed_out():
    result = classify_exit(exit_code=1, stderr="connection timed out after 30000ms")
    assert result == "transient"


def test_econnrefused():
    result = classify_exit(exit_code=1, stderr="ECONNREFUSED 127.0.0.1:8080")
    assert result == "transient"


def test_self_signed_cert():
    result = classify_exit(exit_code=1, stderr="self signed certificate in certificate chain")
    assert result == "transient"


def test_amd_gateway_deprecated_key():
    """F-R6-315: AMD gateway shared-API-key advisory is transient."""
    result = classify_exit(
        exit_code=1,
        stderr="Application 'Claude Code' (Production Restricted) is a shared API key and is being deprecated",
    )
    assert result == "transient"
