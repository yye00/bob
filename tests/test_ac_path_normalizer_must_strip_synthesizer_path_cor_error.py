"""Error-path tests for the AC path-normalizer (feature d482fa32).

Invalid input raises ValueError; the function does not silently succeed.
"""

import pytest

from bob.ac_path_normalizer import normalize_path_ac, normalize_path_acs


def test_none_ac_raises_value_error():
    with pytest.raises(ValueError):
        normalize_path_ac(None)


def test_non_string_ac_raises_value_error():
    with pytest.raises(ValueError):
        normalize_path_ac(123)


def test_list_input_to_single_normalizer_raises_value_error():
    with pytest.raises(ValueError):
        normalize_path_ac(["File exists: src/bob/foo.py"])


def test_normalize_path_acs_rejects_non_list():
    with pytest.raises(ValueError):
        normalize_path_acs("File exists: src/bob/foo.py")


def test_normalize_path_acs_rejects_none():
    with pytest.raises(ValueError):
        normalize_path_acs(None)


def test_normalize_path_acs_rejects_non_string_element():
    with pytest.raises(ValueError):
        normalize_path_acs(["File exists: src/bob/foo.py", 42])
