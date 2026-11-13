"""The Python calculator server against responses captured from the Java server.

``tests/golden/calculator-mcp-server.jsonl`` was recorded from the Java jar (commit 6794f98) by
``tests/golden/capture.py``. Every captured call must produce the same result or JSON-RPC error,
with two documented exceptions:

* ``exponent`` may differ by one ulp: Java's ``Math.pow`` and C's ``pow`` round differently in
  rare cases, and the Java spec itself only promises 1 ulp (``StrictMath.pow`` disagrees with
  ``Math.pow`` on some of the same inputs).
* ``tools/list`` annotations: the port marks every tool read-only (a decision for the port).
"""

import json
import math
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.exceptions import MCPError

from simple_mcp_calculator.calculator_server.tools import SPEC
from simple_mcp_calculator.common.tool_server import Limits, call_tool, tools_by_name
from tests.rpc import RawSession

GOLDEN = Path(__file__).parent / "golden" / "calculator-mcp-server.jsonl"
_lines = GOLDEN.read_text().splitlines()
META: dict[str, Any] = json.loads(_lines[0])
CASES: list[dict[str, Any]] = [json.loads(line) for line in _lines[1:]]

READ_ONLY_ANNOTATIONS = {
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
    "readOnlyHint": True,
    "title": "",
}
ULP_TOLERANT_TOOLS = {"exponent"}


def _ulps_apart(java_text: str, python_text: str) -> float:
    a, b = float(java_text), float(python_text)
    if a == b:
        return 0
    return abs(a - b) / math.ulp(max(abs(a), abs(b)))


def _differs(case: dict[str, Any], reply: dict[str, Any]) -> bool:
    """Whether the Python reply differs from Java's beyond the documented tolerance."""
    expected = {k: case[k] for k in ("result", "error") if k in case}
    if reply == expected:
        return False
    if case["tool"] not in ULP_TOLERANT_TOOLS or "result" not in case or "result" not in reply:
        return True
    java, python = case["result"], reply["result"]
    if java["isError"] or python["isError"]:
        return True
    return _ulps_apart(java["content"][0]["text"], python["content"][0]["text"]) > 1


def _in_process(tool: str, arguments_json: str) -> dict[str, Any]:
    tools = tools_by_name(SPEC.tools)
    limits = Limits(rate=1e9, burst=1_000_000, max_concurrent=1_000)
    try:
        result = call_tool(tools, limits, tool, json.loads(arguments_json))
    except MCPError as e:
        return {"error": e.error.model_dump(exclude_none=True)}
    dumped = result.model_dump(by_alias=True, exclude_unset=True, exclude_none=True, mode="json")
    return {"result": dumped}


def test_golden_file_is_complete() -> None:
    assert len(CASES) > 6000
    assert {c["tool"] for c in CASES} >= {t.name for t in SPEC.tools}


def test_every_captured_call_matches_java() -> None:
    mismatches = [
        (c["tool"], c["arguments"], c.get("result", c.get("error")), reply)
        for c in CASES
        if _differs(c, reply := _in_process(c["tool"], c["arguments"]))
    ]
    assert mismatches == []


def test_ulp_tolerance_covers_exactly_the_known_pow_results() -> None:
    """Keep the tolerance honest: a new pow divergence must be looked at, not absorbed."""
    tolerated = [
        c for c in CASES
        if c["tool"] in ULP_TOLERANT_TOOLS
        and _in_process(c["tool"], c["arguments"]) != {"result": c.get("result")}
    ]  # fmt: skip
    assert [c["arguments"] for c in tolerated] == ['{"a":9,"b":17}', '{"a":1e21,"b":10}']


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RawSession]:
    log = tmp_path_factory.mktemp("logs") / "server.log"
    command = [sys.executable, "-m", "simple_mcp_calculator.calculator_server"]
    with RawSession([*command, f"--logging.file.name={log}"]) as session:
        yield session
        assert session.close() == ""


def test_initialize_matches_java(server: RawSession) -> None:
    assert server.initialize_result == META["initialize"]


def test_tools_list_matches_java_except_read_only_annotations(server: RawSession) -> None:
    expected = [{**tool, "annotations": READ_ONLY_ANNOTATIONS} for tool in META["tools"]["tools"]]
    assert server.request("tools/list")["result"] == {"tools": expected}


def test_sample_over_stdio_matches_java(server: RawSession) -> None:
    """Every 20th captured call, sent over the real transport as the raw JSON Java received."""
    sample = (
        CASES[::20] + [c for c in CASES if c["tool"] not in {"add", "subtract", "multiply"}][-25:]
    )
    mismatches = []
    for c in sample:
        reply = server.request_raw(
            "tools/call", f'{{"name":"{c["tool"]}","arguments":{c["arguments"]}}}'
        )
        reply = {k: reply[k] for k in ("result", "error") if k in reply}
        if _differs(c, reply):
            mismatches.append((c["tool"], c["arguments"], reply))
    assert mismatches == []
    assert len(sample) < 400  # inside the default burst, so no call is rate-limited
