"""Boundary tests for the AC path-normalizer (feature d482fa32).

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from bob.ac_path_normalizer import normalize_path_ac, normalize_path_acs


def test_empty_list_returns_empty_list():
    assert normalize_path_acs([]) == []


def test_non_path_ac_returned_unchanged():
    assert normalize_path_ac("Function defined: bob.foo.bar") == "Function defined: bob.foo.bar"


def test_bare_prefix_with_no_path_returned_unchanged():
    # "File exists:" with nothing after it is a degenerate but non-raising input.
    ac = "File exists:"
    assert normalize_path_ac(ac) == ac


def test_whitespace_only_path_returned_unchanged():
    ac = "File exists:    "
    assert normalize_path_ac(ac) == ac


def test_already_canonical_path_is_idempotent():
    ac = "File exists: src/bob/foo.py"
    once = normalize_path_ac(ac)
    twice = normalize_path_ac(once)
    assert once == twice == ac


def test_single_slash_only_does_not_raise():
    # Degenerate: path is just "/" — strips to empty, well-defined result.
    result = normalize_path_ac("File exists: /")
    assert isinstance(result, str)


def test_list_with_single_clean_ac():
    acs = ["File exists: src/bob/foo.py"]
    assert normalize_path_acs(acs) == acs
