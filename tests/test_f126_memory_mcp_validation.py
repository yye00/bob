"""Tests for F126: memory_id validation in the memory MCP server.

Qdrant uses UUIDs as point IDs. The memory MCP tools previously accepted
any string for ``memory_id``, which caused malformed strings to surface
as opaque internal exceptions that were swallowed and returned as
``{"success": False}`` with no explanation.

These tests verify that the tools now:
- Accept a valid UUID memory_id and forward it to the backend.
- Reject malformed memory_ids (empty string, "abc", SQL-injection-like
  strings, path-like strings) with a structured error dict and without
  ever invoking the backend.
- Never raise on malformed input.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Stub backend
# ---------------------------------------------------------------------------


class _StubBackend:
    """A stub BobMemory replacement that records every call.

    The real BobMemory hits Qdrant; in these tests we only care that the
    MCP wrapper validates ``memory_id`` before forwarding to the backend
    and short-circuits with a clean error otherwise.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def get(self, memory_id: str) -> dict[str, Any]:
        self.calls.append(("get", (memory_id,)))
        return {"id": memory_id, "content": "", "pool": "facts", "metadata": {}}

    def add(
        self,
        content: str,
        pool: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("add", (content, pool, metadata)))
        return {"success": True, "id": "stub-id"}

    def record_feedback(self, memory_id: str, success: bool) -> bool:
        self.calls.append(("record_feedback", (memory_id, success)))
        return True

    def archive(self, memory_id: str) -> bool:
        self.calls.append(("archive", (memory_id,)))
        return True

    def demote(self, memory_id: str) -> bool:
        self.calls.append(("demote", (memory_id,)))
        return True

    def delete(self, memory_id: str) -> bool:
        self.calls.append(("delete", (memory_id,)))
        return True


@pytest.fixture
def stub_backend(monkeypatch) -> _StubBackend:
    """Install a stub backend in place of the lazy-initialized BobMemory."""
    from bob3 import memory_mcp

    backend = _StubBackend()
    monkeypatch.setattr(memory_mcp, "_memory", backend, raising=False)
    return backend


# ---------------------------------------------------------------------------
# _validate_memory_id helper
# ---------------------------------------------------------------------------


class TestValidateMemoryIdHelper:
    """The internal helper should reject anything that isn't a UUID."""

    def test_returns_canonical_uuid_for_valid_input(self):
        from bob3.memory_mcp import _validate_memory_id

        valid = str(uuid.uuid4())
        assert _validate_memory_id(valid) == valid

    def test_accepts_uppercase_uuid_and_normalizes(self):
        from bob3.memory_mcp import _validate_memory_id

        original = uuid.uuid4()
        result = _validate_memory_id(str(original).upper())
        assert result == str(original)

    def test_accepts_uuid_without_hyphens(self):
        from bob3.memory_mcp import _validate_memory_id

        original = uuid.uuid4()
        result = _validate_memory_id(original.hex)
        assert result == str(original)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "abc",
            "not-a-uuid",
            "' OR 1=1 --",
            "../../etc/passwd",
            "/tmp/foo",
            "12345",
            "stub-1",  # legacy placeholder shape used in older stubs
        ],
    )
    def test_returns_none_for_malformed(self, bad: str):
        from bob3.memory_mcp import _validate_memory_id

        assert _validate_memory_id(bad) is None

    def test_returns_none_for_non_string(self):
        from bob3.memory_mcp import _validate_memory_id

        assert _validate_memory_id(None) is None  # type: ignore[arg-type]
        assert _validate_memory_id(123) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Per-tool malformed-id tests
# ---------------------------------------------------------------------------


MALFORMED_IDS = [
    "",
    "abc",
    "' OR 1=1 --",
    "../../etc/passwd",
]


def _resolve(tool_name: str):
    """Return the underlying Python function for a FastMCP-decorated tool.

    The ``@app.tool()`` decorator wraps the function in a FunctionTool object,
    so we attribute-walk to find the real callable.
    """
    from bob3 import memory_mcp

    fn = getattr(memory_mcp, tool_name)
    # FastMCP exposes the wrapped callable on .fn / .func depending on version.
    for attr in ("fn", "func", "__wrapped__", "callable"):
        inner = getattr(fn, attr, None)
        if callable(inner):
            return inner
    if callable(fn):
        return fn
    raise AssertionError(f"Could not resolve callable for {tool_name}")


class TestMemoryGetValidation:
    @pytest.mark.parametrize("bad", MALFORMED_IDS)
    def test_returns_clean_error_dict(self, bad: str, stub_backend: _StubBackend):
        memory_get = _resolve("memory_get")
        result = memory_get(bad)
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "invalid memory_id" in result.get("error", "")
        assert stub_backend.calls == []

    def test_valid_uuid_is_forwarded(self, stub_backend: _StubBackend):
        memory_get = _resolve("memory_get")
        valid = str(uuid.uuid4())
        memory_get(valid)
        assert stub_backend.calls == [("get", (valid,))]


class TestMemoryRecordFeedbackValidation:
    @pytest.mark.parametrize("bad", MALFORMED_IDS)
    def test_returns_clean_error_dict(self, bad: str, stub_backend: _StubBackend):
        memory_record_feedback = _resolve("memory_record_feedback")
        result = memory_record_feedback(bad, True)
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "invalid memory_id" in result.get("error", "")
        assert stub_backend.calls == []

    def test_valid_uuid_is_forwarded(self, stub_backend: _StubBackend):
        memory_record_feedback = _resolve("memory_record_feedback")
        valid = str(uuid.uuid4())
        result = memory_record_feedback(valid, False)
        assert result == {"success": True}
        assert stub_backend.calls == [("record_feedback", (valid, False))]


class TestMemoryArchiveValidation:
    @pytest.mark.parametrize("bad", MALFORMED_IDS)
    def test_returns_clean_error_dict(self, bad: str, stub_backend: _StubBackend):
        memory_archive = _resolve("memory_archive")
        result = memory_archive(bad)
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "invalid memory_id" in result.get("error", "")
        assert stub_backend.calls == []

    def test_valid_uuid_is_forwarded(self, stub_backend: _StubBackend):
        memory_archive = _resolve("memory_archive")
        valid = str(uuid.uuid4())
        result = memory_archive(valid)
        assert result == {"success": True}
        assert stub_backend.calls == [("archive", (valid,))]


class TestMemoryDemoteValidation:
    @pytest.mark.parametrize("bad", MALFORMED_IDS)
    def test_returns_clean_error_dict(self, bad: str, stub_backend: _StubBackend):
        memory_demote = _resolve("memory_demote")
        result = memory_demote(bad)
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "invalid memory_id" in result.get("error", "")
        assert stub_backend.calls == []

    def test_valid_uuid_is_forwarded(self, stub_backend: _StubBackend):
        memory_demote = _resolve("memory_demote")
        valid = str(uuid.uuid4())
        result = memory_demote(valid)
        assert result == {"success": True}
        assert stub_backend.calls == [("demote", (valid,))]


class TestMemoryDeleteValidation:
    @pytest.mark.parametrize("bad", MALFORMED_IDS)
    def test_returns_clean_error_dict(self, bad: str, stub_backend: _StubBackend):
        memory_delete = _resolve("memory_delete")
        result = memory_delete(bad)
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "invalid memory_id" in result.get("error", "")
        assert stub_backend.calls == []

    def test_valid_uuid_is_forwarded(self, stub_backend: _StubBackend):
        memory_delete = _resolve("memory_delete")
        valid = str(uuid.uuid4())
        result = memory_delete(valid)
        assert result == {"success": True}
        assert stub_backend.calls == [("delete", (valid,))]


class TestMemoryAddContentSizeCap:
    """``memory_add`` enforces a hard cap on ``content`` size (R5-005).

    Without a cap, a sub-agent could ``memory_add(content="X" * 10**8, ...)``
    to OOM the embedder, fill the Qdrant index disk, or spam many
    manipulative entries to poison future-search ranking. The cap is
    8000 UTF-8 bytes by default, configurable via the
    ``BOB3_MAX_MEMORY_CONTENT_BYTES`` env var.
    """

    def test_content_at_or_below_cap_is_forwarded(self, stub_backend: _StubBackend):
        """Content exactly at the cap is accepted.

        We pin 8000 bytes specifically: that's the documented default.
        """
        memory_add = _resolve("memory_add")
        content = "X" * 8000
        result = memory_add(content, pool="facts")
        # Backend was called.
        assert stub_backend.calls and stub_backend.calls[0][0] == "add"
        assert result.get("success") is True

    def test_content_above_cap_is_refused(self, stub_backend: _StubBackend):
        """A 10000-byte content is refused with structured error.

        The backend MUST NOT be called — this is the DoS the cap exists
        to prevent.
        """
        memory_add = _resolve("memory_add")
        result = memory_add("X" * 10000, pool="facts")
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "exceeds maximum length" in result.get("error", "")
        assert "8000" in result.get("error", "")
        assert stub_backend.calls == [], (
            "backend was invoked despite oversize content — DoS guard "
            "is being bypassed"
        )

    def test_content_just_over_cap_is_refused(self, stub_backend: _StubBackend):
        """A single byte over the cap is enough to be refused.

        Pins the boundary so future loosenings (e.g. an off-by-one) get
        flagged immediately.
        """
        memory_add = _resolve("memory_add")
        result = memory_add("X" * 8001, pool="facts")
        assert result.get("success") is False
        assert "exceeds maximum length" in result.get("error", "")
        assert stub_backend.calls == []

    def test_cap_counts_utf8_bytes_not_codepoints(
        self, stub_backend: _StubBackend
    ):
        """The cap is on UTF-8 BYTES, not Python str codepoints.

        A 4000-codepoint string of a 4-byte UTF-8 character is 16000
        bytes on the wire — well over the 8000-byte cap. Counting
        codepoints would let an attacker smuggle 4x the budget through.
        """
        memory_add = _resolve("memory_add")
        # U+1F600 (grinning face) is 4 bytes in UTF-8.
        content = "\U0001f600" * 4000  # 4000 codepoints, 16000 UTF-8 bytes
        assert len(content) == 4000
        assert len(content.encode("utf-8")) == 16000

        result = memory_add(content, pool="facts")
        assert result.get("success") is False
        assert "exceeds maximum length" in result.get("error", "")
        assert stub_backend.calls == []

    def test_cap_is_configurable_via_env(
        self, stub_backend: _StubBackend, monkeypatch
    ):
        """``BOB3_MAX_MEMORY_CONTENT_BYTES`` overrides the default.

        Lower the cap to 50 bytes; a 100-byte content must now be refused.
        """
        monkeypatch.setenv("BOB3_MAX_MEMORY_CONTENT_BYTES", "50")
        memory_add = _resolve("memory_add")
        result = memory_add("X" * 100, pool="facts")
        assert result.get("success") is False
        assert "50 bytes" in result.get("error", "")
        assert stub_backend.calls == []

    def test_invalid_env_falls_back_to_default(
        self, stub_backend: _StubBackend, monkeypatch
    ):
        """A junk env value falls back to the documented default cap.

        Important so a typo in the env doesn't silently disable the cap.
        """
        monkeypatch.setenv("BOB3_MAX_MEMORY_CONTENT_BYTES", "not-a-number")
        memory_add = _resolve("memory_add")
        # Default 8000-byte cap should still apply.
        result = memory_add("X" * 10000, pool="facts")
        assert result.get("success") is False
        assert "8000" in result.get("error", "")

    def test_non_string_content_is_refused(self, stub_backend: _StubBackend):
        """Defense in depth: non-string content is refused with a clean error.

        FastMCP normally enforces the type at the schema layer, but the
        function itself should not crash on the bare callable path used
        in tests / direct calls.
        """
        memory_add = _resolve("memory_add")
        result = memory_add(12345, pool="facts")  # type: ignore[arg-type]
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert stub_backend.calls == []


class TestNoExceptionsLeakOut:
    """Sanity: the MCP tools must never raise on malformed input, even when
    the backend is the real BobMemory. We patch ``_mem`` to force-raise to
    prove the validation short-circuits *before* the backend is touched."""

    @pytest.mark.parametrize(
        "tool_name, args",
        [
            ("memory_get", ("",)),
            ("memory_record_feedback", ("abc", True)),
            ("memory_archive", ("../../etc/passwd",)),
            ("memory_demote", ("' OR 1=1 --",)),
            ("memory_delete", ("not-a-uuid",)),
        ],
    )
    def test_validation_short_circuits_before_backend(
        self, tool_name: str, args: tuple[Any, ...], monkeypatch
    ):
        from bob3 import memory_mcp

        def boom() -> Any:
            raise AssertionError(
                "_mem() must not be invoked when memory_id is invalid"
            )

        monkeypatch.setattr(memory_mcp, "_mem", boom)

        tool = _resolve(tool_name)
        result = tool(*args)
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert "invalid memory_id" in result.get("error", "")
