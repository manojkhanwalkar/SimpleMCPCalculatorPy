"""tool_server: the Spring AI wire contract, the validator, errors and request limits.

Expected values are copied from responses captured from the Java servers (commit 6794f98).
"""

import math
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.exceptions import MCPError

from simple_mcp_calculator.common import tool_server as ts
from tests.demo_server import SPEC
from tests.rpc import RawSession

TOOLS = ts.tools_by_name(SPEC.tools)
DIVIDE = TOOLS["divide"]


def _no_limits() -> ts.Limits:
    return ts.Limits(rate=1e9, burst=1_000_000, max_concurrent=1_000_000)


def _wire(result: Any) -> dict[str, Any]:
    # What the SDK writes on the wire: fields that were set, by their JSON names.
    dumped: dict[str, Any] = result.model_dump(
        by_alias=True, exclude_unset=True, exclude_none=True, mode="json"
    )
    return dumped


def _call(arguments: dict[str, Any] | None, limits: ts.Limits | None = None) -> dict[str, Any]:
    return _wire(ts.call_tool(TOOLS, limits or _no_limits(), "divide", arguments))


# Java: tools/list entry for divide on calculator-mcp-server
JAVA_DIVIDE_LISTING = {
    "annotations": {
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
        "readOnlyHint": False,
        "title": "",
    },
    "description": "Divide the first number by the second: a / b. Fails if b is 0",
    "inputSchema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {
            "a": {"description": "Dividend", "format": "double", "type": "number"},
            "b": {"description": "Divisor (must not be 0)", "format": "double", "type": "number"},
        },
        "required": ["a", "b"],
        "type": "object",
    },
    "name": "divide",
    "title": "divide",
}


def test_listing_matches_spring_ai() -> None:
    assert _wire(DIVIDE.listing()) == JAVA_DIVIDE_LISTING


def test_read_only_hints() -> None:
    tool = ts.Tool("t", "d", (), lambda: 1.0, ts.READ_ONLY)
    assert _wire(tool.listing())["annotations"] == {
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
        "readOnlyHint": True,
        "title": "",
    }


def test_result_is_java_formatted_text() -> None:
    assert _call({"a": 17, "b": 5}) == {
        "content": [{"text": "3.4", "type": "text"}],
        "isError": False,
    }
    assert _call({"a": 1e10, "b": 1})["content"][0]["text"] == "1.0E10"


def test_tool_error_repeats_the_message_on_two_lines() -> None:
    assert _call({"a": 1, "b": 0}) == {
        "content": [{"text": "Division by zero\nDivision by zero", "type": "text"}],
        "isError": True,
    }


def test_extra_arguments_are_ignored() -> None:
    assert _call({"a": 1, "b": 2, "c": 3})["content"][0]["text"] == "0.5"


def test_huge_json_integers_become_doubles() -> None:
    assert _call({"a": 12345678901234567890123, "b": 1})["content"][0]["text"] == (
        "1.2345678901234568E22"
    )
    assert ts.to_double(10**400) == math.inf
    assert ts.to_double(-(10**400)) == -math.inf


PREFIX = "Tool (divide) input validation failed: Validation failed: JSON schema validation errors: "


@pytest.mark.parametrize(
    ("arguments", "errors"),
    [
        ({}, ": required property 'a' not found, : required property 'b' not found"),
        (None, ": required property 'a' not found, : required property 'b' not found"),
        ({"a": 1}, ": required property 'b' not found"),
        ({"a": None, "b": 1}, ": required property 'a' not found"),
        ({"a": "x", "b": 1}, "/a: string found, number expected"),
        (
            {"a": True, "b": False},
            "/a: boolean found, number expected, /b: boolean found, number expected",
        ),
        (
            {"a": [1], "b": {}},
            "/a: array found, number expected, /b: object found, number expected",
        ),
        (
            {"b": "y", "a": "x"},
            "/a: string found, number expected, /b: string found, number expected",
        ),
        ({"a": "x"}, "/a: string found, number expected, : required property 'b' not found"),
        ({"b": "x"}, "/b: string found, number expected, : required property 'a' not found"),
    ],
)
def test_validation_errors_match_java(arguments: dict[str, Any] | None, errors: str) -> None:
    """Each case was sent to the Java server; ``errors`` is its reply."""
    assert _call(arguments) == {
        "content": [{"text": f"{PREFIX}[{errors}]", "type": "text"}],
        "isError": True,
    }


def test_unknown_kind_is_named_unknown() -> None:
    assert ts.validate(DIVIDE, {"a": object(), "b": 1}) == ["/a: unknown found, number expected"]


def test_unknown_tool_is_a_json_rpc_error_like_spring_ai() -> None:
    with pytest.raises(MCPError) as caught:
        ts.call_tool(TOOLS, _no_limits(), "nosuch", {"a": 1})
    assert caught.value.error.code == -32602
    assert caught.value.error.message == "Unknown tool: invalid_tool_name"
    assert caught.value.error.data == "Tool not found: nosuch"


def test_unexpected_exception_hides_internals() -> None:
    def broken(a: float) -> float:
        raise KeyError("secret internal detail")

    tools = {"t": ts.Tool("t", "d", (ts.Param("a", "x"),), broken)}
    result = _wire(ts.call_tool(tools, _no_limits(), "t", {"a": 1}))
    assert result["content"][0]["text"] == "Internal error\nInternal error"
    assert result["isError"] is True


def test_exception_without_message_uses_its_type() -> None:
    def bare(a: float) -> float:
        raise ArithmeticError

    tools = {"t": ts.Tool("t", "d", (ts.Param("a", "x"),), bare)}
    assert _wire(ts.call_tool(tools, _no_limits(), "t", {"a": 1}))["content"][0]["text"] == (
        "ArithmeticError\nArithmeticError"
    )


@pytest.mark.parametrize(
    ("value", "text"),
    [(True, "true"), (False, "false"), (120, "120"), (2.0, "2.0"), ("odd", "odd")],
)
def test_format_value(value: ts.ToolValue, text: str) -> None:
    assert ts.format_value(value) == text


def test_duplicate_tool_names_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate tool name: divide"):
        ts.tools_by_name([DIVIDE, DIVIDE])


# --- limits ---------------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_token_bucket_allows_a_burst_then_refills() -> None:
    clock = FakeClock()
    limits = ts.Limits(rate=10, burst=2, max_concurrent=10, clock=clock)
    assert limits.try_acquire() is None
    limits.release()
    assert limits.try_acquire() is None
    limits.release()
    assert limits.try_acquire() == pytest.approx(0.1)
    clock.now += 0.1
    assert limits.try_acquire() is None


def test_concurrency_cap_rejects_while_full() -> None:
    limits = ts.Limits(rate=1000, burst=1000, max_concurrent=1, clock=FakeClock())
    assert limits.try_acquire() is None
    assert limits.try_acquire() == pytest.approx(0.001)
    limits.release()
    assert limits.try_acquire() is None


def test_over_limit_call_is_a_tool_error_and_runs_nothing() -> None:
    calls: list[float] = []

    def counting(a: float) -> float:
        calls.append(a)
        return a

    tools = {"t": ts.Tool("t", "d", (ts.Param("a", "x"),), counting)}
    limits = ts.Limits(rate=1, burst=1, max_concurrent=5, clock=FakeClock())
    assert _wire(ts.call_tool(tools, limits, "t", {"a": 1}))["isError"] is False
    rejected = _wire(ts.call_tool(tools, limits, "t", {"a": 2}))
    assert rejected["isError"] is True
    assert rejected["content"][0]["text"].startswith("Too many requests; retry after 1.000 s\n")
    assert calls == [1.0]


def test_slot_is_released_after_a_tool_error() -> None:
    limits = ts.Limits(rate=1000, burst=1000, max_concurrent=1, clock=FakeClock())
    ts.call_tool(TOOLS, limits, "divide", {"a": 1, "b": 0})
    assert limits.try_acquire() is None


def test_limits_from_environment() -> None:
    limits = ts.Limits.from_env(
        {
            "CALCULATOR_MCP_RATE": "1",
            "CALCULATOR_MCP_BURST": "1",
            "CALCULATOR_MCP_MAX_CONCURRENT": "1",
        }
    )
    assert limits.try_acquire() is None
    assert limits.try_acquire() is not None
    assert ts.Limits.from_env({}).try_acquire() is None


@pytest.mark.parametrize(("rate", "burst", "cap"), [(0, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_limits_reject_nonsense(rate: float, burst: int, cap: int) -> None:
    with pytest.raises(ValueError, match="rate must be"):
        ts.Limits(rate, burst, cap)


# --- over real stdio ------------------------------------------------------------------------

# Java: initialize result of calculator-mcp-server (instructions replaced by the demo's)
JAVA_INITIALIZE = {
    "capabilities": {"logging": {}, "tools": {"listChanged": True}},
    "instructions": "Demo instructions",
    "protocolVersion": "2025-11-25",
    "serverInfo": {"name": "calculator-mcp-server", "version": "1.0.0"},
}


def test_end_to_end_over_stdio(tmp_path: Path) -> None:
    """Raw JSON-RPC against a real server process, as an MCP host would talk to it."""
    server = Path(__file__).with_name("demo_server.py")
    log = tmp_path / "demo.log"
    with RawSession([sys.executable, str(server), f"--logging.file.name={log}"]) as session:
        assert session.initialize_result == JAVA_INITIALIZE
        assert session.request("tools/list")["result"] == {"tools": [JAVA_DIVIDE_LISTING]}
        # Java advertises the logging capability, so setLevel must succeed.
        assert session.request("logging/setLevel", {"level": "info"})["result"] == {}
        # 1e400 is valid JSON (Python's json module can't write it): it arrives as infinity,
        # as in Java; the demo tool has no finiteness check.
        infinite = session.request_raw(
            "tools/call", '{"name":"divide","arguments":{"a":1e400,"b":2}}'
        )
        assert infinite["result"] == {
            "content": [{"text": "Infinity", "type": "text"}],
            "isError": False,
        }
        assert session.call_tool("divide", {"a": 1, "b": 0})["result"]["content"][0]["text"] == (
            "Division by zero\nDivision by zero"
        )
        assert session.call_tool("nosuch", {})["error"] == {
            "code": -32602,
            "message": "Unknown tool: invalid_tool_name",
            "data": "Tool not found: nosuch",
        }
        assert session.close() == ""
    assert "starting on stdio" in log.read_text()
