"""Error-path tests: invalid input raises ValueError and the function does
not silently succeed (feature 5420e867)."""

import pytest

from hippy.checks.backend_required_call_site import (
    has_real_call_site,
    has_simulation_marker,
)


@pytest.mark.parametrize("bad", [None, 123, 4.5, ["src"], {"a": 1}, object()])
def test_has_real_call_site_rejects_non_str(bad):
    with pytest.raises(ValueError):
        has_real_call_site(bad)


@pytest.mark.parametrize("bad", [None, 123, 4.5, ["src"], {"a": 1}, object()])
def test_has_simulation_marker_rejects_non_str(bad):
    with pytest.raises(ValueError):
        has_simulation_marker(bad)


def test_bytes_input_rejected():
    with pytest.raises(ValueError):
        has_real_call_site(b"hipblasSgemm(a, b)")
    with pytest.raises(ValueError):
        has_simulation_marker(b"simulate hip")
