"""Error-path tests: invalid input to parse_depends_on raises ValueError and
the function does not silently succeed."""
from __future__ import annotations

import pytest

from bob.extract_from_peas import parse_depends_on


class TestParseDependsOnErrors:
    def test_integer_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_depends_on(42)  # type: ignore[arg-type]

    def test_list_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_depends_on(["Depends on F-HP-009."])  # type: ignore[arg-type]

    def test_dict_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_depends_on({"description": "Depends on F-HP-009."})  # type: ignore[arg-type]

    def test_bytes_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_depends_on(b"Depends on F-HP-009.")  # type: ignore[arg-type]

    def test_invalid_input_does_not_silently_succeed(self):
        raised = False
        try:
            parse_depends_on(3.14)  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, "parse_depends_on must raise ValueError for non-str input"

    def test_error_message_is_informative(self):
        with pytest.raises(ValueError, match=r"(?i)str|description"):
            parse_depends_on(object())  # type: ignore[arg-type]
