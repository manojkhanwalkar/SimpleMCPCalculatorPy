"""A raw JSON-RPC session with a stdio MCP server, as an MCP host drives it.

Each request waits for its reply before the next is sent: on end of input the SDK cancels
requests still in flight, so a client must not close stdin with replies outstanding.
"""

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Self

PROTOCOL_VERSION = "2025-11-25"


class RawSession:
    def __init__(self, command: Sequence[str], cwd: Path | None = None) -> None:
        self._proc = subprocess.Popen(  # noqa: S603 - fixed test command
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        self._next_id = 0
        self.initialize_result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )["result"]
        self.send_raw(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def send_raw(self, line: str) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def request_raw(self, method: str, params_json: str | None = None) -> dict[str, Any]:
        """Send a request whose params are given as raw JSON text (e.g. holding ``1e400``)."""
        self._next_id += 1
        params = f',"params":{params_json}' if params_json is not None else ""
        self.send_raw(f'{{"jsonrpc":"2.0","id":{self._next_id},"method":"{method}"{params}}}')
        assert self._proc.stdout is not None
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise EOFError("server closed stdout")
            reply: dict[str, Any] = json.loads(line)
            if reply.get("id") == self._next_id:
                return reply

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request_raw(method, None if params is None else json.dumps(params))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> str:
        """Close stdin, wait for exit and return stderr."""
        assert self._proc.stdin is not None
        self._proc.stdin.close()
        _, stderr = self._proc.communicate(timeout=30)
        return stderr

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait()
