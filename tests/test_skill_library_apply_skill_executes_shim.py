"""Tests for apply_skill — verifies that shim modules are executed correctly."""

import pytest
from bob3.skill_library.registry import (
    add_skill,
    apply_skill,
    search_skills,
    ApplyResult,
    SkillHit,
)


HEX_SHIM_SRC = '''\
"""Shim: hex dump bytes using Python stdlib."""


def apply(context):
    data = context.get("data", b"")
    if isinstance(data, str):
        data = data.encode()
    return " ".join(f"{b:02x}" for b in data)
'''

ADD_SHIM_SRC = '''\
"""Shim: add two numbers from context."""


def apply(context):
    a = context.get("a", 0)
    b = context.get("b", 0)
    return a + b
'''

BROKEN_SHIM_SRC = '''\
"""Shim: raises an error intentionally."""


def apply(context):
    raise RuntimeError("intentional failure")
'''

NO_APPLY_SHIM_SRC = '''\
"""Shim: no apply function defined."""

x = 42
'''

SYNTAX_ERROR_SHIM_SRC = '''\
def apply(context
    return 42
'''


def _make_hit(shim_src, skill_id="test_skill"):
    return SkillHit(
        skill_id=skill_id,
        capability_description="test skill",
        similarity=1.0,
        shim_module_src=shim_src,
    )


def test_apply_skill_executes_hex_shim():
    hit = _make_hit(HEX_SHIM_SRC)
    result = apply_skill(hit, context={"data": b"\xde\xad\xbe\xef"})
    assert result.success is True
    assert result.output == "de ad be ef"


def test_apply_skill_returns_apply_result():
    hit = _make_hit(HEX_SHIM_SRC)
    result = apply_skill(hit)
    assert isinstance(result, ApplyResult)


def test_apply_skill_result_has_correct_skill_id():
    hit = _make_hit(HEX_SHIM_SRC, skill_id="my_skill_123")
    result = apply_skill(hit)
    assert result.skill_id == "my_skill_123"


def test_apply_skill_passes_context_to_shim():
    hit = _make_hit(ADD_SHIM_SRC)
    result = apply_skill(hit, context={"a": 10, "b": 32})
    assert result.success is True
    assert result.output == 42


def test_apply_skill_empty_context_defaults():
    hit = _make_hit(HEX_SHIM_SRC)
    result = apply_skill(hit, context={})
    assert result.success is True
    assert result.output == ""


def test_apply_skill_none_context_uses_empty_dict():
    hit = _make_hit(HEX_SHIM_SRC)
    result = apply_skill(hit, context=None)
    assert result.success is True


def test_apply_skill_shim_raising_error_returns_failure():
    hit = _make_hit(BROKEN_SHIM_SRC)
    result = apply_skill(hit, context={})
    assert result.success is False
    assert result.error is not None
    assert "intentional failure" in result.error


def test_apply_skill_no_apply_function_returns_failure():
    hit = _make_hit(NO_APPLY_SHIM_SRC)
    result = apply_skill(hit, context={})
    assert result.success is False
    assert "apply()" in result.error


def test_apply_skill_syntax_error_returns_failure():
    hit = _make_hit(SYNTAX_ERROR_SHIM_SRC)
    result = apply_skill(hit, context={})
    assert result.success is False
    assert result.error is not None


def test_apply_skill_round_trip_via_library(tmp_path):
    """Full round-trip: add skill to library, search it, apply it."""
    add_skill(
        capability_description="hex dump bytes using Python stdlib",
        shim_module_src=HEX_SHIM_SRC,
        workspace=tmp_path,
    )
    hits = search_skills(
        query="hex dump binary data",
        workspace=tmp_path,
        threshold=0.0,
    )
    assert len(hits) > 0
    result = apply_skill(hits[0], context={"data": b"\x01\x02\x03"})
    assert result.success is True
    assert result.output == "01 02 03"
