"""Shared machinery for comparing a Python server with responses captured from its Java twin.

A golden file (``tests/golden/<server>.jsonl``, written by ``tests/golden/capture.py``) holds the
Java server's ``initialize`` and ``tools/list`` results on its first line and one captured
``tools/call`` per further line, with the arguments as the raw JSON text Java received.
"""

import json
import math
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp.shared.exceptions import MCPError

from simple_mcp_calculator.common.tool_server import (
    Limits,
    ServerSpec,
    call_tool,
    tools_by_name,
)
from tests.rpc import RawSession

GOLDEN_DIR = Path(__file__).parent / "golden"

READ_ONLY_ANNOTATIONS = {
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
    "readOnlyHint": True,
    "title": "",
}


def ulps_apart(java_text: str, python_text: str) -> float:
    """Distance in units of the last place between two printed doubles."""
    a, b = float(java_text), float(python_text)
    if a == b:
        return 0
    return abs(a - b) / math.ulp(max(abs(a), abs(b)))


def _reply_part(reply: dict[str, Any]) -> dict[str, Any]:
    return {k: reply[k] for k in ("result", "error") if k in reply}


@dataclass
class Golden:
    """The captured responses of one Java server, and how to compare a Python server with them.

    ``ulp_limits`` maps a tool to how many ulps its successful numeric results may differ from
    Java's: HotSpot's ``Math.pow``, ``Math.log`` and ``Math.log10`` intrinsics and the C library
    round differently on some inputs.
    """

    spec: ServerSpec
    ulp_limits: Mapping[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(init=False)
    cases: list[dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        lines = (GOLDEN_DIR / f"{self.spec.name}.jsonl").read_text().splitlines()
        self.meta = json.loads(lines[0])
        self.cases = [json.loads(line) for line in lines[1:]]
        self._tools = tools_by_name(self.spec.tools)
        self._limits = Limits(rate=1e9, burst=1_000_000, max_concurrent=1_000)

    def in_process(self, tool: str, arguments_json: str) -> dict[str, Any]:
        """The reply the Python server gives to one captured call, without a transport."""
        try:
            result = call_tool(self._tools, self._limits, tool, json.loads(arguments_json))
        except MCPError as e:
            return {"error": e.error.model_dump(exclude_none=True)}
        return {
            "result": result.model_dump(
                by_alias=True, exclude_unset=True, exclude_none=True, mode="json"
            )
        }

    def differs(self, case: dict[str, Any], reply: dict[str, Any]) -> bool:
        """Whether a Python reply differs from Java's beyond the documented tolerance."""
        expected = _reply_part(case)
        if _reply_part(reply) == expected:
            return False
        limit = self.ulp_limits.get(case["tool"], 0)
        if not limit or "result" not in case or "result" not in reply:
            return True
        java, python = case["result"], reply["result"]
        if java["isError"] or python["isError"]:
            return True
        return ulps_apart(java["content"][0]["text"], python["content"][0]["text"]) > limit

    def in_process_mismatches(self) -> list[tuple[str, str, Any, Any]]:
        return [
            (c["tool"], c["arguments"], _reply_part(c), reply)
            for c in self.cases
            if self.differs(c, reply := self.in_process(c["tool"], c["arguments"]))
        ]

    def tolerated(self) -> list[dict[str, Any]]:
        """Cases that only match thanks to the ulp tolerance."""
        return [
            c
            for c in self.cases
            if c["tool"] in self.ulp_limits
            and _reply_part(self.in_process(c["tool"], c["arguments"])) != _reply_part(c)
        ]

    def listing_with_read_only_annotations(self) -> dict[str, Any]:
        return {
            "tools": [
                {**tool, "annotations": READ_ONLY_ANNOTATIONS}
                for tool in self.meta["tools"]["tools"]
            ]
        }

    def stdio_mismatches(
        self, session: RawSession, cases: list[dict[str, Any]]
    ) -> list[tuple[str, str, Any]]:
        """Send captured calls over a real transport, as the raw JSON Java received."""
        mismatches = []
        for c in cases:
            reply = session.request_raw(
                "tools/call", f'{{"name":"{c["tool"]}","arguments":{c["arguments"]}}}'
            )
            if self.differs(c, reply):
                mismatches.append((c["tool"], c["arguments"], _reply_part(reply)))
        return mismatches


@contextmanager
def server_session(module: str, log_dir: Path) -> Iterator[RawSession]:
    """A raw JSON-RPC session with ``python -m <module>``, logging into ``log_dir``; the server
    must exit cleanly, with nothing on stderr."""
    command = [sys.executable, "-m", module, f"--logging.file.name={log_dir / 'server.log'}"]
    with RawSession(command) as session:
        yield session
        assert session.close() == ""
